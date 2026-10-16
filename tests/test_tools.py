"""Tests for actual Git-object tools and read-only safety boundaries."""

import json
import unittest

from auditor.errors import AuditError, ToolError
from auditor.repository import normalize_url
from auditor.security import Redactor
from tests.helpers import FixtureRepository
from tools import InspectionTools


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.repo = FixtureRepository()
        self.addCleanup(self.repo.close)
        self.tools = InspectionTools(self.repo)

    def test_list_pagination_and_prefix(self):
        page = self.tools.list_files(limit=1)
        self.assertTrue(page["truncated"])
        self.assertEqual(page["next_offset"], 1)
        scoped = self.tools.list_files(prefix=".github/")
        self.assertEqual(len(scoped["files"]), 1)
        self.assertFalse(scoped["truncated"])

    def test_numbered_read_and_followup(self):
        result = self.tools.read_file("app.py", max_lines=1)
        self.assertEqual(result["lines"][0]["line"], 1)
        self.assertEqual(result["next_line"], 2)
        self.assertIn("hello", self.tools.read_file("app.py", start_line=2)["lines"][0]["text"])

    def test_literal_search_casefold_and_glob(self):
        self.assertEqual(len(self.tools.search_code("UNITTEST", glob="*.yml")["matches"]), 1)
        self.assertEqual(self.tools.search_code(".*")["matches"], [])

    def test_history_and_repository_unchanged(self):
        before = self.repo.git(["status", "--porcelain"])
        self.assertIn("Fixture", self.tools.git_log()["history"])
        self.tools.read_file("app.py")
        self.tools.search_code("hello")
        self.assertEqual(before, self.repo.git(["status", "--porcelain"]))

    def test_reject_traversal_and_invalid_args(self):
        for path in ("../x", "/etc/passwd", "C:/x", ".git/config", "app.py\\..\\x", "./app.py"):
            with self.subTest(path=path), self.assertRaises(ToolError):
                self.tools.read_file(path)
        for arguments in ({"limit": True}, {"offset": -1}, {"limit": 1001}):
            with self.assertRaises(ToolError):
                self.tools.list_files(**arguments)
        with self.assertRaises(ToolError):
            self.tools.dispatch("run_shell", {})
        with self.assertRaises(ToolError):
            self.tools.dispatch("read_file", {"nonsense": 1})

    def test_missing_file_is_recoverable(self):
        with self.assertRaises(ToolError):
            self.tools.read_file("missing.py")

    def test_reject_binary_large_and_symlink(self):
        repo = FixtureRepository({"binary": b"abc\x00def", "large": b"x" * (512 * 1024 + 1)})
        self.addCleanup(repo.close)
        tools = InspectionTools(repo)
        for path in ("binary", "large"):
            with self.assertRaises(ToolError):
                tools.read_file(path)
        tools.entries["binary"]["mode"] = "120000"
        with self.assertRaisesRegex(ToolError, "Symlinks"):
            tools.read_file("binary")
        result = tools.search_code("abc")
        self.assertEqual(len(result["skipped"]), 2)

    def test_search_match_overflow_is_explicit(self):
        repo = FixtureRepository({"many.txt": "test\ntest\ntest\n"})
        self.addCleanup(repo.close)
        result = InspectionTools(repo).search_code("test", limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["overflow_file"], "many.txt")

    def test_url_allowlist(self):
        self.assertEqual(
            normalize_url("https://github.com/owner/repo.git/"), "https://github.com/owner/repo"
        )
        for url in (
            "file:///tmp/repo",
            "https://github.com.evil/a/b",
            "https://u:p@github.com/a/b",
            "https://github.com/a/b?x=1",
            "https://github.com/a/b/tree/main",
            "https://github.com/../b",
            "--upload-pack=evil",
        ):
            with self.subTest(url=url), self.assertRaises(AuditError):
                normalize_url(url)

    def test_secret_never_returned_by_tools(self):
        secret = "test_credential_not_a_real_key_12345"  # noqa: S105 - synthetic fixture
        repo = FixtureRepository({"config.py": f'API_KEY = "{secret}"\nprint("hello")\n'})
        self.addCleanup(repo.close)
        tools = InspectionTools(repo)
        result = tools.read_file("config.py")
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("[REDACTED]", json.dumps(result))
        self.assertEqual(result["lines"][1]["line"], 2)
        self.assertEqual(tools.search_code(secret)["matches"], [])

    def test_redactor_private_key_preserves_line_numbers(self):
        value = "-----BEGIN PRIVATE KEY-----\nnot-real-key\n-----END PRIVATE KEY-----\nafter\n"
        redacted = Redactor().text(value)
        self.assertNotIn("not-real-key", redacted)
        self.assertEqual(redacted.splitlines().index("after"), 3)

    def test_environment_reference_is_not_redacted(self):
        value = "API_KEY = os.getenv('API_KEY')"
        self.assertEqual(Redactor().text(value), value)

    def test_short_secret_does_not_corrupt_other_words(self):
        redactor = Redactor()
        result = redactor.text("password = 'x'\nmax_lines = 10\nx\n")
        self.assertIn("max_lines", result)
        self.assertNotIn("'x'", result)
        self.assertIn("[REDACTED]", result)

    def test_empty_credential_does_not_consume_next_line(self):
        source = "GROQ_API_KEY=\nLLM_BASE_URL=https://api.groq.com/openai/v1\n"
        self.assertEqual(Redactor().text(source), source)

    def test_unquoted_boolean_and_null_settings_remain_typed(self):
        source = "persist-credentials: false\nsecrets: null\n"
        redactor = Redactor()
        self.assertEqual(redactor.text(source), source)
        self.assertEqual(
            redactor.text('{"truncated": false, "file": null}'),
            '{"truncated": false, "file": null}',
        )
