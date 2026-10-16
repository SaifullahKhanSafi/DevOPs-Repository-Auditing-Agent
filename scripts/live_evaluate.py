"""Opt-in real-provider checks on locally generated Git fixtures, never hidden answers."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import atomic_write  # noqa: E402
from auditor.errors import AuditError  # noqa: E402
from auditor.llm import ChatClient, Settings, load_env  # noqa: E402
from auditor.loop import AuditAgent  # noqa: E402
from auditor.security import Redactor  # noqa: E402
from tests.helpers import URL, FixtureRepository  # noqa: E402
from tools import InspectionTools  # noqa: E402


def fixture_files(defective):
    trigger = "pull_request_target" if defective else "pull_request"
    permissions = "write-all" if defective else "\n  contents: read"
    checkout = (
        "\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}"
        if defective
        else "\n        with:\n          persist-credentials: false"
    )
    suffix = " || true" if defective else ""
    path = (
        'Path("/home/alice/work/demo/state.json")'
        if defective
        else 'Path(os.getenv("APP_STATE", "state.json"))'
    )
    return {
        "README.md": "# Demo command\n\nA small Python 3.11+ command that writes its own state file. No runtime dependencies.\n\nRun: python app.py\nTest: python -m unittest discover -s tests\nQuality: python -m ruff check . and python -m ruff format --check .\nConfigure APP_STATE to choose a state file. Use pull requests for changes.\n",
        ".gitignore": ".env\n__pycache__/\n*.pyc\n.venv/\n.ruff_cache/\nstate.json\n",
        "app.py": f'{"" if defective else "import os"}\nfrom pathlib import Path\n\n\ndef state_path():\n    return {path}\n\n\ndef main():\n    state_path().write_text("ready", encoding="utf-8")\n\n\nif __name__ == "__main__":\n    main()\n',
        "tests/test_app.py": 'import unittest\n\nfrom app import state_path\n\n\nclass StateTests(unittest.TestCase):\n    def test_state_filename(self):\n        self.assertEqual(state_path().name, "state.json")\n',
        "requirements-dev.txt": "ruff==0.11.13\n",
        "pyproject.toml": '[tool.ruff]\ntarget-version = "py311"\nline-length = 100\n',
        ".github/workflows/ci.yml": f'name: CI\non: [push, {trigger}]\npermissions: {permissions}\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683{checkout}\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with:\n          python-version: "3.12"\n      - run: python -m pip install -r requirements-dev.txt\n      - run: python -m ruff check .\n      - run: python -m ruff format --check .\n      - run: python -m unittest discover -s tests{suffix}\n',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["defective", "healthy"], required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "live_evaluation")
    parser.add_argument(
        "--resume", action="store_true", help="Resume this deterministic fixture checkpoint"
    )
    args = parser.parse_args()
    load_env()
    settings = Settings.from_env()
    redactor = Redactor([settings.api_key])
    saved_dates = {name: os.environ.get(name) for name in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")}
    os.environ.update(
        GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00", GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00"
    )
    try:
        repo = FixtureRepository(fixture_files(args.case == "defective"))
    finally:
        for name, value in saved_dates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    try:
        tools = InspectionTools(repo, redactor)
        resume_events = None
        checkpoint = args.output_dir / (args.case + ".trace.jsonl")
        if args.resume:
            resume_events = [
                json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()
            ]
        agent = None

        def on_event(event):
            if event["event"] == "tool":
                error = event.get("result", {}).get("error")
                print(
                    f"{args.case}: step {event['step']} {event['name']}"
                    + (" - " + error if error else ""),
                    flush=True,
                )
            if agent is not None and (
                not args.resume or any(e.get("event") == "resumed" for e in agent.events)
            ):
                atomic_write(
                    args.output_dir / (args.case + ".trace.jsonl"),
                    "".join(json.dumps(redactor.clean(e)) + "\n" for e in agent.events),
                )

        agent = AuditAgent(
            ChatClient(settings), tools, max_steps=settings.max_steps, event_callback=on_event
        )
        try:
            report = agent.run(URL, resume_events=resume_events)
        except AuditError as exc:
            agent._record({"event": "failed", "error": redactor.text(str(exc))})
            print("Live fixture audit failed: " + redactor.text(str(exc)), file=sys.stderr)
            return 1
        finally:
            atomic_write(
                args.output_dir / (args.case + ".trace.jsonl"),
                "".join(json.dumps(redactor.clean(e)) + "\n" for e in agent.events),
            )
        atomic_write(
            args.output_dir / (args.case + ".report.json"), json.dumps(report, indent=2) + "\n"
        )
        expected = (
            [
                {
                    "id": "ci-failure-suppression",
                    "file": ".github/workflows/ci.yml",
                    "cause": "The unittest shell fallback || true hides test failures.",
                },
                {
                    "id": "privileged-untrusted-pr",
                    "file": ".github/workflows/ci.yml",
                    "cause": "pull_request_target checks out the PR head and executes its code with write-all permissions and persisted credentials.",
                },
                {
                    "id": "machine-specific-state-path",
                    "file": "app.py",
                    "cause": "A hardcoded home directory prevents portable state creation and ignores documented APP_STATE configuration.",
                },
            ]
            if args.case == "defective"
            else []
        )
        metadata = {
            "fixture": "Locally generated Git repository; not a public URL audit or hidden benchmark",
            "report_repository_field": "Placeholder public-shaped identifier used only by this fixture harness",
            "case": args.case,
            "commit": repo.commit,
            "model": settings.model,
            "provider": settings.base_url,
            "known_injected_defects": expected,
            "source_files": fixture_files(args.case == "defective"),
        }
        atomic_write(
            args.output_dir / (args.case + ".provenance.json"),
            json.dumps(metadata, indent=2) + "\n",
        )
        print(f"Completed {args.case}: {len(report['violations'])} findings.")
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
