"""Validate the exact output contract and tie findings to the observation ledger."""

import json
import re

from auditor.contracts import CATEGORIES
from auditor.errors import ReportError

FIELDS = {
    "rule_id",
    "category",
    "severity",
    "file",
    "line",
    "description",
    "evidence",
    "recommendation",
}


def validate_report(repository, payload, ledger, observed_files):
    if not isinstance(payload, dict) or set(payload) != {"violations", "coverage"}:
        raise ReportError("submit_report requires exactly violations and coverage.")
    coverage = payload["coverage"]
    if not isinstance(coverage, dict) or set(coverage) != set(CATEGORIES):
        raise ReportError("Coverage must address all nine inspection areas.")
    for value in coverage.values():
        if not isinstance(value, str) or len(value.strip()) < 12:
            raise ReportError("Each coverage entry needs an interpretation and observation IDs.")
        if not any(call_id in value for call_id in ledger):
            raise ReportError("Each coverage entry must reference a real observation tool_call_id.")
    violations = payload["violations"]
    if not isinstance(violations, list) or len(violations) > 100:
        raise ReportError("violations must be an array of at most 100 findings.")
    findings, seen = [], set()
    for item in violations:
        if not isinstance(item, dict) or set(item) != FIELDS | {"support"}:
            raise ReportError(
                "Each violation requires exactly the contract fields plus internal support."
            )
        for name in FIELDS - {"file", "line"}:
            if not isinstance(item[name], str) or not 1 <= len(item[name].strip()) <= 6000:
                raise ReportError(f"{name} must be a nonempty string, at most 6000 characters.")
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{1,30}-[0-9]{3}", item["rule_id"]):
            raise ReportError("rule_id must resemble SEC-001 or CI-001.")
        if item["category"] not in CATEGORIES:
            raise ReportError("Use a declared DevOps category.")
        if item["severity"] not in {"critical", "high", "medium", "low"}:
            raise ReportError("Invalid severity.")
        support = item["support"]
        if not isinstance(support, dict) or set(support) != {"tool_call_id", "quote"}:
            raise ReportError("support needs tool_call_id and quote.")
        call_id, quote = support["tool_call_id"], support["quote"]
        if not isinstance(call_id, str) or call_id not in ledger:
            raise ReportError("support must reference a successful observation.")
        if not isinstance(quote, str) or not 3 <= len(quote.strip()) <= 2000:
            raise ReportError("support quote must be a literal excerpt of 3 to 2000 characters.")
        observation = ledger[call_id]
        if quote not in json.dumps(observation, ensure_ascii=False) and not _contains(
            observation, quote
        ):
            raise ReportError("support quote does not occur in the cited observation.")
        path, line = item["file"], item["line"]
        if path is None:
            if line is not None:
                raise ReportError("line must be null when file is null.")
            if observation.get("truncated") or observation.get("skipped"):
                raise ReportError("Incomplete discovery cannot support a repository-level absence.")
        else:
            if not isinstance(path, str) or path not in observed_files:
                raise ReportError("Finding file was not observed by a successful tool.")
            if line is not None and (type(line) is not int or line < 1):
                raise ReportError("line must be a positive integer or null.")
            candidates = []
            if observation.get("path") == path:
                candidates = observation.get("lines", [])
            candidates += [m for m in observation.get("matches", []) if m["path"] == path]
            if not any(
                (line is None or entry["line"] == line) and quote in entry["text"]
                for entry in candidates
            ):
                raise ReportError(
                    "Quote must match the finding's file and line in the cited observation."
                )
        key = (item["rule_id"], path, line)
        if key in seen:
            continue
        seen.add(key)
        result = {
            name: item[name]
            for name in [
                "rule_id",
                "category",
                "severity",
                "file",
                "line",
                "description",
                "evidence",
                "recommendation",
            ]
        }
        if path is not None and quote not in result["evidence"]:
            result["evidence"] += " Observed: " + quote
        findings.append(result)
    return {"repository": repository, "violations": findings}


def _contains(value, quote):
    if isinstance(value, str):
        return quote in value
    if isinstance(value, dict):
        return any(_contains(item, quote) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, quote) for item in value)
    return False
