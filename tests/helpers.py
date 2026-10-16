"""Offline test fixtures. Never imported by the production CLI."""

import json
import subprocess
import tempfile
from pathlib import Path

from auditor.contracts import CATEGORIES
from auditor.repository import run_git

URL = "https://github.com/example/audit-fixture"


class FixtureRepository:
    def __init__(self, files=None):
        self.temp = tempfile.TemporaryDirectory(prefix="audit-test-")
        self.root = Path(self.temp.name)
        self.path = self.root / ".git"
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        files = files or {
            "README.md": "# Fixture\nRun unittest using Python.\n",
            "app.py": "def greet():\n    return 'hello'\n",
            ".github/workflows/ci.yml": "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python -m unittest discover || true\n",
        }
        for path, content in files.items():
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                dest.write_bytes(content)
            else:
                dest.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "Fixture",
            ],
            check=True,
            capture_output=True,
        )
        self.commit = self.git(["rev-parse", "HEAD"]).decode().strip()

    def git(self, args):
        return run_git(["--git-dir=" + str(self.path), *args])

    def close(self):
        self.temp.cleanup()


def call(call_id, name, **arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def coverage(call_id="discover"):
    return {
        area: f"Inspected {call_id}; this offline test exercises coverage validation only. Execution unavailable."
        for area in CATEGORIES
    }


def finding():
    return {
        "rule_id": "CI-001",
        "category": "github actions / ci",
        "severity": "medium",
        "file": ".github/workflows/ci.yml",
        "line": 7,
        "description": "The CI test step discards test failures.",
        "evidence": "The shell fallback returns success even when unittest fails.",
        "recommendation": "Remove the shell fallback so a nonzero unittest exit fails the job.",
        "support": {"tool_call_id": "read-ci", "quote": "python -m unittest discover || true"},
    }


class ScriptedClient:
    """Test double, not an LLM and never a production fallback."""

    def __init__(self, replies):
        self.replies = iter(replies)
        self.messages = []

    def complete(self, messages, tools):
        self.messages.append(messages)
        return next(self.replies)


def investigation(violations=None):
    return [
        call("discover", "list_files", purpose="Discover the project's actual structure"),
        call("history", "git_log", purpose="Inspect recent changes and history scope"),
        call(
            "search-ci",
            "search_code",
            purpose="Locate test commands and failure handling",
            pattern="unittest",
        ),
        call(
            "read-ci",
            "read_file",
            purpose="Follow the observed CI command to verify its exit handling",
            path=".github/workflows/ci.yml",
        ),
        call(
            "finish",
            "submit_report",
            violations=violations if violations is not None else [finding()],
            coverage=coverage(),
        ),
    ]
