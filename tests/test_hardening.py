"""Edge cases found in a ten-pass risk audit. Uses fixtures, not user credentials."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_mcp_doctor.doctor import MAX_CONFIG_BYTES, inspect_config


class HardeningTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.conf = self.base / "config.toml"
        self.home = self.base / "user"
        self.home.mkdir()

    def scan(self, body: str, **kwargs):
        self.conf.write_text(body, encoding="utf-8")
        kwargs.setdefault("env", {})
        kwargs.setdefault("home", self.home)
        kwargs.setdefault("which", lambda x: "/usr/bin/" + x if x in ("npx", "node", "python", "npx.cmd") else None)
        return inspect_config(self.conf, **kwargs)

    @staticmethod
    def codes(r):
        return [f.code for f in r.findings]

    def assert_codes(self, body, contains=(), not_contains=(), **kwargs):
        codes = self.codes(self.scan(body, **kwargs))
        for code in contains:
            self.assertIn(code, codes)
        for code in not_contains:
            self.assertNotIn(code, codes)

    # A. Official schema, including remote executor support.
    def test_env_vars_mixed_valid(self):
        self.assert_codes('''[mcp_servers.a]
command = 'python'
args = ['-m','some_package']
env_vars = ['LOCAL', {name='ANOTHER',source='local'}]
''', not_contains=['ENV_VARS_INVALID'], env={'LOCAL': 'ok', 'ANOTHER': 'ok'})

    def test_remote_env_vars_are_not_looked_up_locally(self):
        self.assert_codes('''[mcp_servers.a]
experimental_environment='remote'
command='remote-tool'
env_vars=[{name='SECRET',source='remote'}]
''', contains=['REMOTE_COMMAND_NOT_VERIFIED'],
                          not_contains=['EXECUTABLE_NOT_FOUND', 'ENV_VAR_MISSING','ENV_VARS_INVALID'])

    def test_remote_env_var_without_remote_environment_is_error(self):
        self.assert_codes('''[mcp_servers.a]
command='python'
env_vars=[{name='XYZ',source='remote'}]
''', contains=['REMOTE_VAR_NO_EXECUTOR'])

    def test_remote_http_not_supported(self):
        self.assert_codes('''[mcp_servers.a]
url='https://example.com/mcp'
experimental_environment='remote'
''', contains=['REMOTE_HTTP_UNSUPPORTED'])

    def test_env_vars_bad_object_is_not_crash(self):
        self.assert_codes('''[mcp_servers.a]
command='python'
env_vars=[{name=1,source='local'},{source='local'},{name='x',source='unknown'}]
''', contains=['ENV_VARS_INVALID'])

    def test_cwd_nonexistent_is_error(self):
        self.assert_codes('''[mcp_servers.a]
command='python'
cwd='/definitely-no-such-place-7618360'
''', contains=['CWD_NOT_FOUND'])

    def test_cwd_missing_variable_warning(self):
        self.assert_codes('''[mcp_servers.a]
command='python'
cwd='${DOES_NOT_EXIST}/project'
''', contains=['CWD_ENV_UNRESOLVED'])

    def test_relative_executable_with_cwd(self):
        executable = self.base / 'launcher'
        executable.write_text('not run')
        body = f'''[mcp_servers.a]
command='./launcher'
cwd='{self.base.as_posix()}'
'''
        self.assert_codes(body, not_contains=['EXECUTABLE_NOT_FOUND','CWD_NOT_FOUND'])

    def test_directory_in_command_position_not_executable(self):
        self.assert_codes(f'''[mcp_servers.a]
command='{self.base.as_posix()}'
''', contains=['EXECUTABLE_NOT_FOUND'])

    def test_python_script_on_windows_needs_interpreter(self):
        self.assert_codes('''[mcp_servers.a]
command='./run.py'
''', contains=['SCRIPT_LAUNCHER'], platform='win32')

    # B. Actual URI mistakes people make.
    def test_http_local_ipv6_is_allowed(self):
        self.assert_codes("[mcp_servers.a]\nurl='http://[::1]:3000/mcp'\n", not_contains=['INSECURE_HTTP','URL_INVALID'])

    def test_http_localhost_trailing_dot_allowed(self):
        self.assert_codes("[mcp_servers.a]\nurl='http://localhost.:3000/mcp'\n", not_contains=['INSECURE_HTTP'])

    def test_http_loopback_subnet_is_allowed(self):
        self.assert_codes("[mcp_servers.a]\nurl='http://127.2.3.4:3000/mcp'\n", not_contains=['INSECURE_HTTP'])

    def test_userinfo_url_is_invalid_without_echo(self):
        secret = 'try_to_hide_THIS_PASSWORD_7626'
        r = self.scan(f"[mcp_servers.a]\nurl='https://admin:{secret}@example.com/mcp'\n")
        self.assertIn('URL_INVALID', self.codes(r))
        self.assertNotIn(secret, json.dumps(r.to_dict()))

    def test_bad_port_rejected(self):
        for url in ['http://localhost:65536/mcp', 'http://localhost:0/mcp', 'http://localhost:bad/mcp']:
            with self.subTest(url=url):
                self.assert_codes(f"[mcp_servers.a]\nurl='{url}'\n", contains=['URL_INVALID'])

    def test_fragment_rejected(self):
        self.assert_codes("[mcp_servers.a]\nurl='https://example.org/mcp#ignore'\n", contains=['URL_INVALID'])

    def test_url_query_generic_info_not_echoing(self):
        r = self.scan("[mcp_servers.a]\nurl='https://example.org/mcp?token=abc123456789'\n")
        self.assertIn('HTTP_URL_QUERY', self.codes(r))
        self.assertNotIn('abc123456789', json.dumps(r.to_dict()))

    # C. Timing, policy, and scope.
    def test_zero_negative_infinite_float_timeout(self):
        for val in ('0', '-1', 'inf', 'true', "'nan'"):
            with self.subTest(val=val):
                self.assert_codes(f"[mcp_servers.a]\ncommand='python'\nstartup_timeout_sec={val}\n",
                                  contains=['TIMEOUT_INVALID'])

    def test_timeout_alias_both_warning(self):
        self.assert_codes("[mcp_servers.a]\ncommand='python'\nstartup_timeout_ms=9000\nstartup_timeout_sec=9\n",
                          contains=['STARTUP_TIMEOUT_DUPLICATE'])

    def test_overlapping_tool_lists(self):
        self.assert_codes("[mcp_servers.a]\ncommand='python'\nenabled_tools=['read','write']\ndisabled_tools=['write']\n",
                          contains=['TOOLS_FILTER_CONFLICT'])

    def test_invalid_header_type(self):
        self.assert_codes("[mcp_servers.a]\nurl='https://example.com'\nhttp_headers={token=12}\n",
                          contains=['HEADERS_INVALID'])

    def test_http_header_env_missing(self):
        self.assert_codes("[mcp_servers.a]\nurl='https://example.com'\nenv_http_headers={Authorization='TOKEN_NOT_SET'}\n",
                          contains=['HEADER_ENV_MISSING'])

    def test_stdio_bearer_token_is_suspicious(self):
        self.assert_codes("[mcp_servers.a]\ncommand='python'\nbearer_token_env_var='API_KEY'\n",
                          contains=['TOKEN_ENV_ON_STDIO'])

    def test_http_stdio_env_warns(self):
        self.assert_codes("[mcp_servers.a]\nurl='https://example.org'\nenv={ABC='literal'}\n",
                          contains=['STDIO_ENV_ON_HTTP'])

    def test_invalid_enabled_skips_invalid_runtime_guess(self):
        self.assert_codes("[mcp_servers.a]\nenabled='nope'\ncommand='not-there'\n",
                          contains=['ENABLED_INVALID'], not_contains=['EXECUTABLE_NOT_FOUND'])

    # D. Operational safety and defaults.
    def test_byte_limit_rejects_oversized_input(self):
        self.conf.write_bytes(b'#' * (MAX_CONFIG_BYTES + 1))
        r = inspect_config(self.conf, env={}, home=self.home)
        self.assertIn('CONFIG_TOO_LARGE', self.codes(r))

    def test_absent_file_and_unreadable_directory(self):
        self.assertIn('CONFIG_MISSING', self.codes(inspect_config(self.base / 'missing', env={}, home=self.home)))
        self.assertIn('CONFIG_UNREADABLE', self.codes(inspect_config(self.base, env={}, home=self.home)))

    def test_server_name_never_appears_by_default(self):
        secret = 'UnusualClientPrivateLabel'
        r = self.scan(f'[mcp_servers.{secret}]\ncommand="not-found-exec"\n')
        self.assertNotIn(secret, json.dumps(r.to_dict()))
        self.assertIn('mcp:#1', json.dumps(r.to_dict()))

    def test_safe_name_opt_in(self):
        r = self.scan('[mcp_servers.playwright]\ncommand="not-found-exec"\n', show_names=True)
        self.assertIn('mcp:playwright', json.dumps(r.to_dict()))

    def test_keylike_name_hidden_even_with_opt_in(self):
        r = self.scan('[mcp_servers.mySecretToken]\ncommand="python"\n', show_names=True)
        self.assertNotIn('mySecretToken', json.dumps(r.to_dict()))

    def test_strict_cli_warning_exit_codes(self):
        self.conf.write_text('[mcp_servers.a]\nurl="http://example.org"\n')
        cp = subprocess.run([sys.executable, '-m', 'codex_mcp_doctor', '--config', str(self.conf), '--json', '--strict'],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 1)
        self.assertEqual(json.loads(cp.stdout)['status'], 'warning')

    def test_project_cli_is_a_single_layer(self):
        root = self.base / 'actual_project'
        (root / '.codex').mkdir(parents=True)
        (root / '.codex' / 'config.toml').write_text('[mcp_servers.project]\nurl="https://example.org/mcp"\n')
        cp = subprocess.run([sys.executable, '-m', 'codex_mcp_doctor', '--project', str(root), '--json'],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0)
        result = json.loads(cp.stdout)
        self.assertEqual(result['servers_seen'], 1)
        self.assertNotIn(str(root), cp.stdout)

    def test_mutually_exclusive_config_options(self):
        cp = subprocess.run([sys.executable, '-m', 'codex_mcp_doctor', '--config', 'a', '--project', 'b'],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 2)

    def test_dangerous_content_is_data_not_code(self):
        danger = self.base / 'would_be_written'
        secret = "SECRET_LIKELY_VALUE_1234567890"
        body = f'''[mcp_servers."{secret}"]
command="python"
args=["-c", "open('{danger}','w').write('uh-oh')", "{secret}"]
env={{A="{secret}"}}
'''
        with patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            r = self.scan(body)
        self.assertFalse(danger.exists())
        self.assertNotIn(secret, json.dumps(r.to_dict()))
        self.assertNotIn(str(danger), json.dumps(r.to_dict()))

    def test_empty_missing_credential_is_not_printed(self):
        r = self.scan('[mcp_servers.any]\ncommand="python"\nenv_vars=["SENSITIVE_SECRET_NAME"]\n')
        self.assertIn('ENV_VAR_MISSING', self.codes(r))
        self.assertNotIn('SENSITIVE_SECRET_NAME', json.dumps(r.to_dict()))

    def test_names_with_ansi_control_hidden(self):
        self.assert_codes('[mcp_servers."\u001b[31m"]\ncommand="python"\n',
                          contains=['CONFIG_INVALID_TOML'])

    def test_duplicate_inline_tables_caught(self):
        self.assert_codes('[mcp_servers.a]\ncommand="python"\ncommand="npx"\n',
                          contains=['CONFIG_INVALID_TOML'])

    def test_windows_cmd_fallback_testable_without_windows_machine(self):
        r = self.scan("[mcp_servers.a]\ncommand='npx'\nargs=['x']\n", platform='win32',
                      which=lambda value: 'C:/fake/npx.cmd' if value == 'npx.cmd' else None)
        self.assertNotIn('EXECUTABLE_NOT_FOUND', self.codes(r))


if __name__ == '__main__':
    unittest.main()

class AdditionalWinCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / 'config.toml'

    def check(self, config, **kwargs):
        self.file.write_text(config)
        kwargs.setdefault('platform', 'win32')
        kwargs.setdefault('env', {})
        kwargs.setdefault('which', lambda name: None)
        return [f.code for f in inspect_config(self.file, **kwargs).findings]

    def test_custom_path_not_a_hard_failure(self):
        c = "[mcp_servers.m]\ncommand='my_tool'\nenv={ PATH='C:\\\\MyTools' }\n"
        codes = self.check(c)
        self.assertIn('CUSTOM_PATH_UNVERIFIED', codes)
        self.assertNotIn('EXECUTABLE_NOT_FOUND', codes)

    def test_relative_command_requires_cwd(self):
        c = "[mcp_servers.m]\ncommand='./bin/server.cmd'\n"
        codes = self.check(c)
        self.assertIn('RELATIVE_COMMAND_UNVERIFIED', codes)
        self.assertNotIn('EXECUTABLE_NOT_FOUND', codes)

    def test_case_insensitive_windows_variable(self):
        c = "[mcp_servers.m]\ncommand='C:/bin/tool.exe'\nenv_vars=['API_KEY']\n"
        codes = self.check(c, env={'api_key': 'ok'})
        self.assertNotIn('ENV_VAR_MISSING', codes)

    def test_missing_source_in_env_object_rejected(self):
        c = "[mcp_servers.m]\ncommand='C:/bin/tool.exe'\nenv_vars=[{name='A'}]\n"
        self.assertIn('ENV_VARS_INVALID', self.check(c))

    def test_case_insensitive_expansion_windows_percent(self):
        from codex_mcp_doctor.doctor import _expand_path
        path, missing = _expand_path('%userprofile%/tool.exe', {'USERPROFILE':'C:/Users/Test'}, Path('/foo'))
        self.assertFalse(missing)
        self.assertIn('Users/Test', str(path))

    def test_custom_path_not_hidden_on_absolute_missing_binary(self):
        codes = self.check("[mcp_servers.m]\ncommand='/path/nowhere/run'\nenv={PATH='X'}\n")
        self.assertIn('EXECUTABLE_NOT_FOUND', codes)

class ResourceLimitTests(unittest.TestCase):
    def test_server_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / 'config.toml'
            f.write_text(''.join(f'[mcp_servers.s{i}]\ncommand="python"\n' for i in range(513)))
            result = inspect_config(f, env={})
            self.assertEqual(result.servers_seen, 513)
            self.assertEqual([v.code for v in result.findings], ['MCP_TOO_MANY'])

    def test_eight_problem_types_in_one_mixed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / 'config.toml'
            f.write_text('''[mcp_servers.a]
command='does-not-exist-1972'
args=[1]
enabled_tools=['read']
disabled_tools=['read']
startup_timeout_sec=0
env_vars=['MISSING']
[mcp_servers.b]
url='http://remote.example/mcp?auth=sensitive_value'
[mcp_servers.c]
enabled=false
command='missing-other'
''')
            result = inspect_config(f, env={}, which=lambda _:None)
            actual = {v.code for v in result.findings}
            self.assertTrue({'EXECUTABLE_NOT_FOUND', 'ARGS_INVALID', 'TOOLS_FILTER_CONFLICT',
                             'TIMEOUT_INVALID', 'ENV_VAR_MISSING', 'INSECURE_HTTP',
                             'HTTP_URL_QUERY', 'SERVER_DISABLED'}.issubset(actual))
            self.assertNotIn('sensitive_value', json.dumps(result.to_dict()))
