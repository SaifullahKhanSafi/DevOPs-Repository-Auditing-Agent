"""Provider protocol, configuration and CLI failure behavior without network/API fees."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from agent import atomic_write, main
from auditor.errors import AuditError, ToolError
from auditor.llm import ChatClient, Settings, load_env
from auditor.repository import Repository, run_git
from tests.helpers import URL, FixtureRepository


class ProviderTests(unittest.TestCase):
    def settings(self):
        return Settings("fixture-api-credential", "fixture-model", "https://api.groq.com/openai/v1")

    def test_groq_configuration_and_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "GROQ_API_KEY=local-test-value\nLLM_MODEL=fixture-model\nLLM_BASE_URL=https://api.groq.com/openai/v1\nPATH=bad\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                load_env(path)
                self.assertNotIn("PATH", os.environ)
                self.assertEqual(Settings.from_env().api_key, "local-test-value")
                os.environ["GROQ_API_KEY"] = "environment-wins"
                load_env(path)
                self.assertEqual(Settings.from_env().api_key, "environment-wins")

    def test_invalid_or_missing_settings(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(AuditError):
            Settings.from_env()
        for field, value in (
            ("LLM_BASE_URL", "http://api.groq.com/openai/v1"),
            ("LLM_TIMEOUT", "nan"),
            ("LLM_MAX_STEPS", "2"),
            ("LLM_BASE_URL", "https://u:p@host/v1"),
        ):
            env = {"GROQ_API_KEY": "fixture", "LLM_MODEL": "model", field: value}
            with patch.dict(os.environ, env, clear=True), self.assertRaises(AuditError):
                Settings.from_env()

    def test_http_tool_call_protocol(self):
        client = ChatClient(self.settings())
        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "one"}]}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"choices": [{"message": message}]}).encode()
        client.opener = Mock()
        client.opener.open.return_value = response
        self.assertEqual(client.complete([], []), message)
        req = client.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(json.loads(req.data)["tool_choice"], "required")
        self.assertEqual(req.get_header("User-agent"), "DevOpsRepositoryAuditor/1.0")

    def test_retry_then_failure_without_provider_body(self):
        client = ChatClient(self.settings())
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError(
            "https://api.groq.com", 429, "sensitive-body", {}, None
        )
        with (
            patch("auditor.llm.time.sleep"),
            self.assertRaisesRegex(AuditError, "HTTP 429") as error,
        ):
            client.complete([], [])
        self.assertNotIn("sensitive-body", str(error.exception))
        self.assertEqual(client.opener.open.call_count, 3)

    def test_auth_failure_not_retried(self):
        client = ChatClient(self.settings())
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError("url", 401, "secret", {}, None)
        with self.assertRaisesRegex(AuditError, "401"):
            client.complete([], [])
        self.assertEqual(client.opener.open.call_count, 1)

    def test_malformed_response_and_timeout(self):
        client = ChatClient(self.settings())
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"choices":[]}'
        client.opener = Mock()
        client.opener.open.return_value = response
        with self.assertRaisesRegex(AuditError, "malformed"):
            client.complete([], [])
        client.opener.open.side_effect = URLError("test socket failure")
        with patch("auditor.llm.time.sleep"), self.assertRaisesRegex(AuditError, "three attempts"):
            client.complete([], [])

    def test_git_timeout_and_missing_binary(self):
        import subprocess

        with patch(
            "auditor.repository.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 1)
        ):
            with self.assertRaisesRegex(ToolError, "timed out"):
                run_git(["version"])
        with patch("auditor.repository.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(AuditError, "Git is required"):
                run_git(["version"])

    def test_clone_failure_cleans_temp_directory(self):
        repo = Repository(URL)
        with patch("auditor.repository.run_git", side_effect=ToolError("unavailable")):
            with self.assertRaises(ToolError):
                repo.__enter__()
        self.assertFalse(Path(repo._temp.name).exists())

    def test_cli_success_writes_report_and_trace(self):
        from tests.helpers import ScriptedClient, investigation

        fixture = FixtureRepository()
        self.addCleanup(fixture.close)
        context = Mock()
        context.__enter__ = Mock(return_value=fixture)
        context.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            with (
                patch("agent.load_env"),
                patch("agent.Settings.from_env", return_value=self.settings()),
                patch("agent.Repository", return_value=context),
                patch("agent.ChatClient", return_value=ScriptedClient(investigation())),
                redirect_stderr(io.StringIO()),
            ):
                code = main(["--repo", URL, "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(output.read_text())["violations"]), 1)
            self.assertIn('"event": "completed"', output.with_suffix(".trace.jsonl").read_text())

    def test_cli_fatal_keeps_existing_report_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            atomic_write(output, "previous completed report")
            error = io.StringIO()
            with redirect_stderr(error):
                code = main(["--repo", "file:///invalid", "--output", str(output)])
            self.assertEqual(code, 1)
            self.assertIn("Audit failed", error.getvalue())
            self.assertEqual(output.read_text(), "previous completed report")

    def test_invalid_generated_tool_call_is_retried(self):
        client = ChatClient(self.settings())
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": []}}]}
        ).encode()
        error = HTTPError(
            "url", 400, "bad tool", {}, io.BytesIO(b'{"error":{"code":"tool_use_failed"}}')
        )
        client.opener = Mock()
        client.opener.open.side_effect = [error, response]
        self.assertEqual(client.complete([], [])["role"], "assistant")
        self.assertEqual(client.opener.open.call_count, 2)

    def test_tpm_request_over_limit_requests_compaction(self):
        from auditor.errors import ContextLimitError

        client = ChatClient(self.settings())
        body = (
            b'{"error":{"code":"rate_limit_exceeded","message":"TPM Limit 8000, Requested 9000"}}'
        )
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError("url", 429, "limit", {}, io.BytesIO(body))
        with self.assertRaises(ContextLimitError):
            client.complete([], [])
