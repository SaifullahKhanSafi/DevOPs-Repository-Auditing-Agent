"""Generate the assignment sample with a REAL configured LLM and public repository."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--resume", action="store_true", help="Resume the existing failed sample trace"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "agent.py"),
            "--repo",
            args.repo,
            "--output",
            str(root / "sample_report.json"),
            "--trace",
            str(root / "docs" / "sample_trace.jsonl"),
        ]
        + (["--resume", str(root / "docs" / "sample_trace.jsonl")] if args.resume else []),
        cwd=root,
        check=False,
    )
    if result.returncode:
        return result.returncode
    events = [
        json.loads(line)
        for line in (root / "docs/sample_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    provenance = {
        "source": "Real public repository inspected by the configured LLM-directed agent",
        "repository": args.repo,
        "commit": events[0]["commit"],
        "model": events[0].get("model"),
        "provider": events[0].get("provider"),
        "completed": events[-1],
        "trace": "docs/sample_trace.jsonl",
        "regenerate": "python scripts/generate_sample.py --repo " + args.repo,
    }
    (root / "docs/sample_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
