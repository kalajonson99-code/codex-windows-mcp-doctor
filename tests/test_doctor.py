from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_mcp_doctor.doctor import default_config_path, inspect_config


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.toml"
        self.home = self.root / "home"
        self.home.mkdir()
        self.executables = {"npx", "codex", "python"}

    def scan(self, text=None, env=None, platform="win32", executables=None):
        if text is not None:
            self.config.write_text(text, encoding="utf-8")
        present = self.executables if executables is None else set(executables)
        return inspect_config(self.config, env=env or {}, platform=platform,
                              which=lambda cmd: "fake-path" if cmd in present else None,
                              exists=lambda p: p == self.root / "installed" or p == self.root / "bin" / "tool.exe",
                              home=self.home)

    def codes(self, report):
        return [f.code for f in report.findings]

    def test_missing_file_is_warning(self):
        r = self.scan()
        self.assertEqual(r.status, "warning")
        self.assertIn("CONFIG_MISSING", self.codes(r))

    def test_invalid_toml_is_error(self):
        self.assertIn("CONFIG_INVALID_TOML", self.codes(self.scan("[mcp_servers.x\n")))

    def test_bom_supported(self):
        self.config.write_bytes(b"\xef\xbb\xbf[mcp_servers.good]\ncommand='npx'\nargs=['pkg']\n")
        self.assertEqual(self.scan().status, "ok")

    def test_non_utf8_is_error(self):
        self.config.write_bytes(b"\xff\xfe\x00")
        self.assertIn("CONFIG_INVALID_TOML", self.codes(self.scan()))

    def test_no_servers(self):
        self.assertIn("MCP_NOT_CONFIGURED", self.codes(self.scan("model='gpt'\n")))

    def test_empty_servers(self):
        self.assertIn("MCP_EMPTY", self.codes(self.scan("[mcp_servers]\n")))

    def test_valid_stdio(self):
        r = self.scan("[mcp_servers.echo]\ncommand='npx'\nargs=['-y','sample@1.0.0']\n")
        self.assertEqual(r.status, "ok")
        self.assertIn("STATIC_CHECKS_PASSED", self.codes(r))

    def test_valid_http(self):
        r = self.scan("[mcp_servers.docs]\nurl='https://developers.openai.com/mcp'\n")
        self.assertEqual(r.status, "ok")

    def test_disabled_server_does_not_flag_exe(self):
        r = self.scan("[mcp_servers.off]\nenabled=false\ncommand='missing'\n")
        self.assertEqual(r.status, "ok")
        self.assertEqual(self.codes(r), ["SERVER_DISABLED"])

    def test_invalid_enabled(self):
        self.assertIn("ENABLED_INVALID", self.codes(self.scan("[mcp_servers.s]\nenabled='false'\ncommand='npx'\n")))

    def test_missing_command(self):
        self.assertIn("TRANSPORT_INVALID", self.codes(self.scan("[mcp_servers.a]\nargs=[]\n")))

    def test_both_transports(self):
        self.assertIn("TRANSPORT_INVALID", self.codes(self.scan("[mcp_servers.a]\ncommand='npx'\nurl='https://a.com'\n")))

    def test_executable_not_found(self):
        self.assertIn("EXECUTABLE_NOT_FOUND", self.codes(self.scan("[mcp_servers.a]\ncommand='notinstalled'\nargs=['x']\n")))

    def test_windows_cmd_fallback(self):
        self.assertEqual(self.scan("[mcp_servers.a]\ncommand='npx'\nargs=['foo']\n", executables={"npx.cmd"}).status, "ok")

    def test_absolute_executable_exists(self):
        text = "[mcp_servers.a]\ncommand='" + str(self.root / "installed") + "'\n"
        self.assertEqual(self.scan(text).status, "ok")

    def test_args_validation(self):
        self.assertIn("ARGS_INVALID", self.codes(self.scan("[mcp_servers.a]\ncommand='npx'\nargs=[1]\n")))

    def test_npx_without_package(self):
        self.assertIn("NPX_NO_ARGS", self.codes(self.scan("[mcp_servers.a]\ncommand='npx'\n")))

    def test_playwright_unpinned(self):
        r = self.scan("[mcp_servers.playwright]\ncommand='npx'\nargs=['@playwright/mcp@latest']\n")
        self.assertIn("UNPINNED_PACKAGE", self.codes(r))

    def test_playwright_extension_info(self):
        r = self.scan("[mcp_servers.playwright]\ncommand='npx'\nargs=['@playwright/mcp@1.0.0', '--extension']\n")
        self.assertIn("PLAYWRIGHT_EXTENSION", self.codes(r))

    def test_malformed_http(self):
        self.assertIn("URL_INVALID", self.codes(self.scan("[mcp_servers.a]\nurl='https://:bad'\n")))

    def test_http_remote_warning(self):
        self.assertIn("INSECURE_HTTP", self.codes(self.scan("[mcp_servers.a]\nurl='http://example.com/mcp'\n")))

    def test_http_local_allowed(self):
        self.assertEqual(self.scan("[mcp_servers.a]\nurl='http://127.0.0.1:8931/mcp'\n").status, "ok")

    def test_timeout_invalid(self):
        self.assertIn("TIMEOUT_INVALID", self.codes(self.scan("[mcp_servers.a]\nurl='https://example.com'\ntool_timeout_sec=-1\n")))

    def test_env_missing_count_but_no_name(self):
        secret_var = "TOP_SECRET_PRIVATE_VARIABLE"
        r = self.scan("[mcp_servers.a]\ncommand='npx'\nargs=['pkg']\nenv_vars=['" + secret_var + "']\n")
        self.assertIn("ENV_VAR_MISSING", self.codes(r))
        self.assertNotIn(secret_var, json.dumps(r.to_dict()))

    def test_env_present(self):
        r = self.scan("[mcp_servers.a]\ncommand='npx'\nargs=['pkg']\nenv_vars=['X']\n", env={"X": "value"})
        self.assertEqual(r.status, "ok")

    def test_env_invalid(self):
        r = self.scan("[mcp_servers.a]\ncommand='npx'\nenv={ X=1 }\n")
        self.assertIn("ENV_INVALID", self.codes(r))

    def test_bearer_env_missing(self):
        r = self.scan("[mcp_servers.a]\nurl='https://example.com'\nbearer_token_env_var='SECRET_NAME'\n")
        self.assertIn("TOKEN_ENV_MISSING", self.codes(r))
        self.assertNotIn("SECRET_NAME", json.dumps(r.to_dict()))

    def test_never_echo_inline_passwords_or_urls(self):
        key = "SUPERSECRET_9876543210"
        r = self.scan(f"[mcp_servers.a]\ncommand='npx'\nargs=['{key}']\nenv={{ KEY='{key}' }}\n" +
                      f"[mcp_servers.web]\nurl='http://example.com/?token={key}'\n")
        self.assertNotIn(key, json.dumps(r.to_dict()))

    def test_never_echo_secret_in_server_name(self):
        r = self.scan('[mcp_servers."token=1234567890"]\ncommand="npx"\nargs=["pkg"]\n')
        self.assertNotIn("1234567890", json.dumps(r.to_dict()))

    def test_token_like_server_name_is_redacted(self):
        fake_token = "sk-" + "1234567890abcdefghijklmn"
        r = self.scan(f'[mcp_servers."{fake_token}"]\ncommand="npx"\nargs=["pkg"]\n')
        self.assertNotIn(fake_token, json.dumps(r.to_dict()))

    def test_custom_path_redacted(self):
        r = self.scan("[mcp_servers.good]\ncommand='npx'\nargs=['pkg']\n")
        self.assertEqual(r.config, "<custom path>")
        self.assertNotIn(str(self.root), json.dumps(r.to_dict()))

    def test_codex_home_override(self):
        p = default_config_path({"CODEX_HOME": "/tmp/custom-codex"}, self.home)
        self.assertEqual(p, Path("/tmp/custom-codex/config.toml"))

    def test_no_code_execution_from_command_name(self):
        flag = self.root / "BAD"
        cmd = f"python -c 'open(\\\"{flag}\\\",\\\"w\\\").close()'"
        r = self.scan('[mcp_servers.evil]\ncommand=' + json.dumps(cmd) + '\nargs=[]\n')
        self.assertEqual(r.status, "error")
        self.assertFalse(flag.exists())

    def test_scan_never_launches_commands(self):
        with patch("subprocess.run", side_effect=AssertionError("MUST NOT RUN")):
            self.scan("[mcp_servers.a]\ncommand='npx'\nargs=['pkg']\n")

    def test_cli_json(self):
        self.config.write_text("[mcp_servers.demo]\ncommand='impossible-nonexistent-binary-298'\n", encoding="utf-8")
        cp = subprocess.run([sys.executable, "-m", "codex_mcp_doctor", "--config", str(self.config), "--json"],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 2)
        self.assertEqual(json.loads(cp.stdout)["status"], "error")


if __name__ == "__main__":
    unittest.main()
