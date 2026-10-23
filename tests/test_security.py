"""Adversarial tests for privacy, parser failure modes, and release preflight."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from codex_mcp_doctor.doctor import inspect_config
from tools.security_preflight import archive_issues, source_issues


class UnsafeConfigRegression(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.path = Path(self.t.name) / 'config.toml'

    def check(self, data, **kwargs):
        self.path.write_text(data, encoding='utf-8')
        kwargs.setdefault('env', {})
        kwargs.setdefault('which', lambda _name: '/usr/bin/example')
        return inspect_config(self.path, **kwargs)

    def test_deep_toml_arr_returns_redacted_parse_error(self):
        payload = '[' * 950 + '"x"' + ']' * 950
        report = self.check('[mcp_servers.a]\ncommand="python"\nargs=' + payload)
        self.assertIn('CONFIG_INVALID_TOML', [finding.code for finding in report.findings])

    def test_very_large_timeout_is_safe(self):
        report = self.check('[mcp_servers.a]\ncommand="python"\nstartup_timeout_sec=' + '9' * 1000)
        self.assertIn('TIMEOUT_INVALID', [finding.code for finding in report.findings])

    def test_invalid_executable_path_does_not_dump_raw_config(self):
        fake_sensitive_path = '/very/long/' + 'private' * 800
        report = self.check('[mcp_servers.a]\ncommand="' + fake_sensitive_path + '"\n')
        self.assertNotIn(fake_sensitive_path, json.dumps(report.to_dict()))
        self.assertIn('EXECUTABLE_UNVERIFIED', [finding.code for finding in report.findings])

    def test_path_discovery_permission_exception_is_redacted(self):
        def blocked(_):
            raise PermissionError('DO_NOT_PUBLISH_THIS_PATH')
        report = self.check('[mcp_servers.a]\ncommand="some-command"\n', which=blocked)
        self.assertIn('EXECUTABLE_UNVERIFIED', [finding.code for finding in report.findings])
        self.assertNotIn('DO_NOT_PUBLISH_THIS_PATH', json.dumps(report.to_dict()))

    def test_workdir_permission_exception_is_redacted(self):
        def blocked(_):
            raise PermissionError('DO_NOT_PUBLISH_THIS_DIRECTORY')
        report = self.check('[mcp_servers.a]\ncommand="python"\ncwd="/private/folder"\n', is_dir=blocked)
        self.assertIn('CWD_UNVERIFIED', [finding.code for finding in report.findings])
        self.assertNotIn('DO_NOT_PUBLISH_THIS_DIRECTORY', json.dumps(report.to_dict()))

    def test_cli_does_not_output_token_in_path_error(self):
        secret = 'SENSITIVE_TOKEN_X_' + 'q' * 5000
        self.path.write_text('[mcp_servers.a]\ncommand="/tmp/' + secret + '"\n')
        run = subprocess.run([sys.executable, '-m', 'codex_mcp_doctor', '--json', '--config', str(self.path)],
                             capture_output=True, text=True, timeout=12)
        self.assertNotIn(secret, run.stdout + run.stderr)
        self.assertNotIn('Traceback', run.stdout + run.stderr)


class ReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)

    def zip(self, name, files):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as z:
            for file_name, data in files.items():
                z.writestr(file_name, data)
        return path

    def test_rejects_openai_key_without_echoing_value(self):
        fake_secret = 'sk-proj-' + 's' * 42
        path = self.zip('broken.zip', {'src/module.py': 'TOKEN="' + fake_secret + '"'})
        self.assertIn('SUSPECT_CREDENTIAL', archive_issues(path))

    def test_rejects_private_key_material(self):
        fake_private = '-----BEGIN ' + 'PRIVATE KEY-----\nnot-real\n'
        path = self.zip('keys.zip', {'src/module.py': fake_private})
        self.assertIn('SUSPECT_CREDENTIAL', archive_issues(path))

    def test_rejects_sensitive_paths_and_traversal(self):
        path = self.zip('bad.zip', {'source/../../secrets.txt': 'nothing', 'foo/.env': 'secret',
                                    'foo/config.toml': 'key=abc', 'foo/credentials.pem': 'key'})
        self.assertEqual(4, archive_issues(path).count('DISALLOWED_ARCHIVE_NAME'))

    def test_rejects_binary_files(self):
        path = self.zip('executable.zip', {'thing.exe': b'\x00\x90', 'stuff/module.py': b'\x00\x90'})
        issues = archive_issues(path)
        self.assertIn('DISALLOWED_ARCHIVE_NAME', issues)
        self.assertIn('BINARY_CONTENT', issues)

    def test_rejects_tar_symlinks(self):
        path = self.root / 'invalid.tar.gz'
        with tarfile.open(path, 'w:gz') as fp:
            link = tarfile.TarInfo('anything/link.py')
            link.type = tarfile.SYMTYPE
            link.linkname = '/private/key'
            fp.addfile(link)
        self.assertIn('DISALLOWED_ARCHIVE_ENTRY', archive_issues(path))

    def test_rejects_oversized_archive(self):
        path = self.zip('huge.zip', {'foo/file.txt': 'x' * (2 * 1024 * 1024 + 1)})
        self.assertIn('ARCHIVE_RESOURCE_LIMIT', archive_issues(path))

    def test_source_check_detects_unexpected_secret_file(self):
        for f in ('CHANGELOG.md', 'CONTRIBUTING.md', 'LICENSE', 'MANIFEST.in', 'README.md',
                  'README.zh-CN.md', 'SECURITY.md', 'pyproject.toml', '.gitignore'):
            (self.root / f).write_text('safe text')
        src = self.root / 'src' / 'codex_mcp_doctor'
        src.mkdir(parents=True)
        (src / 'config.toml').write_text('private thing')
        self.assertIn('DISALLOWED_SOURCE_NAME', source_issues(self.root))


if __name__ == '__main__':
    unittest.main()
