"""Score manually reviewed findings; no synthetic or hidden accuracy claims."""

import argparse
import json
from pathlib import Path


def metrics(report, labels):
    findings = report["violations"]
    indices = labels["true_positive_indices"]
    known = labels["known_violation_count"]
    if not isinstance(findings, list) or not isinstance(indices, list):
        raise ValueError("Expected violations and true_positive_indices arrays.")
    if type(known) is not int or known < 0:
        raise ValueError("known_violation_count must be a nonnegative integer.")
    if any(type(i) is not int or i < 0 or i >= len(findings) for i in indices):
        raise ValueError("True positive indices must refer to findings in this report.")
    if len(set(indices)) != len(indices) or len(indices) > known:
        raise ValueError("Each independently known defect can count only once.")
    tp, total = len(indices), len(findings)
    precision = tp / total if total else None
    recall = tp / known if known else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {
        "true_positives": tp,
        "false_positives": total - tp,
        "false_negatives": known - tp,
        "reported": total,
        "known": known,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "note": "Human-reviewed labels; each true positive must match a distinct known defect. Undefined ratios are null.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compute precision/recall from reviewed audit labels"
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = metrics(
            json.loads(args.report.read_text(encoding="utf-8")),
            json.loads(args.labels.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(f"Cannot score report: {exc}")
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
