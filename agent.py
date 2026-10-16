"""Assignment CLI: python agent.py --repo URL --output report.json."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from auditor.errors import AuditError
from auditor.llm import ChatClient, Settings, load_env
from auditor.loop import AuditAgent
from auditor.repository import Repository, normalize_url
from auditor.security import Redactor
from tools import InspectionTools


def atomic_write(path, text):
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, prefix=".audit-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LLM-directed, read-only public GitHub DevOps audit"
    )
    parser.add_argument("--repo", required=True, help="https://github.com/owner/repository")
    parser.add_argument(
        "--output", required=True, type=Path, help="Completed JSON report destination"
    )
    parser.add_argument(
        "--trace", type=Path, help="JSONL trace (default: output with .trace.jsonl suffix)"
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="Resume a failed trace after revalidating its commit and observations",
    )
    args = parser.parse_args(argv)
    agent = None
    redactor = Redactor()
    trace = args.trace or args.output.with_suffix(".trace.jsonl")
    try:
        if trace.resolve() == args.output.resolve():
            raise AuditError("Report and trace paths must differ.")
        repo_url = normalize_url(args.repo)
        load_env()
        settings = Settings.from_env()
        redactor = Redactor([settings.api_key])
        with Repository(repo_url) as repo:
            tools = InspectionTools(repo, redactor)
            agent = AuditAgent(
                ChatClient(settings),
                tools,
                max_steps=settings.max_steps,
                event_callback=lambda event: print(
                    f"Audit step {event['step']}: {event['name']}", file=sys.stderr, flush=True
                )
                if event.get("event") == "tool"
                else None,
            )
            resume_events = None
            if args.resume:
                if args.resume.stat().st_size > 20 * 1024 * 1024:
                    raise AuditError("Resume trace exceeds 20 MiB.")
                resume_events = [
                    json.loads(line)
                    for line in args.resume.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            report = agent.run(repo_url, resume_events=resume_events)
            # Write trace first: a completed report always has its audit trail available.
            atomic_write(
                trace,
                "".join(
                    json.dumps(redactor.clean(event), ensure_ascii=False) + "\n"
                    for event in agent.events
                ),
            )
            atomic_write(
                args.output,
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            )
        print(
            f"Audit completed: {len(report['violations'])} violations; report and trace saved.",
            file=sys.stderr,
        )
        return 0
    except (AuditError, OSError, UnicodeError, ValueError) as exc:
        # Never print upstream exception messages that could contain credentials or source text.
        message = (
            str(exc)
            if isinstance(exc, AuditError)
            else "Cannot read/write an audit file or parse configuration."
        )
        print("Audit failed: " + redactor.text(message), file=sys.stderr)
        if agent is not None and trace.resolve() != args.output.resolve():
            try:
                events = agent.events + [{"event": "failed", "error": redactor.text(message)}]
                atomic_write(
                    trace,
                    "".join(
                        json.dumps(redactor.clean(e), ensure_ascii=False) + "\n" for e in events
                    ),
                )
            except OSError:
                pass
        return 1
    except KeyboardInterrupt:
        print("Audit interrupted; no completed report written.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
