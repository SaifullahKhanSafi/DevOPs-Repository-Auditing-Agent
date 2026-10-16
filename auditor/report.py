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
            raise ReportError("Each coverage entry needs a concise interpretation.")
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
        if item["category"] not in CATEGORIES:
            raise ReportError("Use a declared DevOps category.")
        if item["severity"] not in {"critical", "high", "medium", "low"}:
            raise ReportError("Invalid severity.")
        support = item["support"]
        if not isinstance(support, dict) or set(support) != {"tool_call_id", "quote"}:
            raise ReportError("support needs tool_call_id and quote.")
        call_id, quote = support["tool_call_id"], support["quote"]
        if not isinstance(call_id, str) or not call_id:
            raise ReportError("support requires an observation reference string.")
        if not isinstance(quote, str) or not 3 <= len(quote.strip()) <= 2000:
            raise ReportError("support quote must be a literal excerpt of 3 to 2000 characters.")
        path, line = item["file"], item["line"]
        if path is None and re.search(
            r"(?i)(?:missing|absent|lack|no\b).*(?:\.gitignore|licen[cs]e)", item["description"]
        ):
            raise ReportError(
                "An absent optional .gitignore or LICENSE alone is not a demonstrated DevOps defect. Cite a concrete affected tracked artifact/project requirement, or remove the unsupported finding."
            )
        if path is None:
            if line is not None:
                raise ReportError("line must be null when file is null.")
            observation = ledger.get(call_id)
            if not observation or not isinstance(observation.get("files"), list):
                raise ReportError(
                    "A repository-level absence requires an actual complete file-discovery observation."
                )
            if observation.get("truncated") or observation.get("skipped"):
                raise ReportError("Incomplete discovery cannot support a repository-level absence.")
            if quote not in json.dumps(observation, ensure_ascii=False) and not _contains(
                observation, quote
            ):
                raise ReportError(
                    "Repository-level support quote does not occur in the cited discovery."
                )
        else:
            if not isinstance(path, str) or path not in observed_files:
                raise ReportError("Finding file was not observed by a successful tool.")
            if line is not None and (type(line) is not int or line < 1):
                raise ReportError("line must be a positive integer or null.")
            # Resolve citation spelling against actual observed source, never model claims.
            # A vendor-ID typo cannot invalidate otherwise exact file/line/excerpt evidence.
            if not any(
                _source_matches(observation, path, line, quote) for observation in ledger.values()
            ):
                raise ReportError(
                    f"Finding {item['rule_id']} has no exact observed quote at its file/line. Quote a short decoded substring from ONE source line without JSON escapes or line-number prefixes."
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


def _source_matches(observation, path, line, quote):
    candidates = list(observation.get("lines", [])) if observation.get("path") == path else []
    candidates += [entry for entry in observation.get("matches", []) if entry["path"] == path]
    return any(
        (line is None or entry["line"] == line) and quote in entry["text"] for entry in candidates
    )
