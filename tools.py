"""Bounded, read-only inspection tools backed by Git blobs, not working-tree files."""

import fnmatch
from pathlib import PurePosixPath

from auditor.errors import ToolError
from auditor.security import Redactor

MAX_BLOB_BYTES = 512 * 1024
MAX_SEARCH_BYTES = 4 * 1024 * 1024


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ToolError(f"{name} must be an integer from {low} to {high}.")
    return value


def safe_path(path):
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or "\x00" in path
        or PurePosixPath(path).is_absolute()
        or any(part in {".", "..", ".git"} for part in path.split("/"))
        or ":" in path
        or any(ord(char) < 32 for char in path)
    ):
        raise ToolError("Use a relative, POSIX repository file path without traversal.")
    return path


class InspectionTools:
    def __init__(self, repository, redactor=None):
        self.repo = repository
        self.redactor = redactor or Redactor()
        self.entries = {}
        self.cache = {}
        raw = repository.git(["ls-tree", "-r", "-l", "-z", "HEAD"])
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, name = record.split(b"\t", 1)
            mode, kind, oid, size = metadata.decode("ascii").split()
            path = name.decode("utf-8", errors="replace")
            self.entries[path] = {
                "mode": mode,
                "type": kind,
                "oid": oid,
                "size": int(size) if size != "-" else None,
            }

    def list_files(self, prefix="", offset=0, limit=300):
        integer(offset, "offset", 0, 1000000)
        integer(limit, "limit", 1, 1000)
        if prefix:
            safe_path(prefix.rstrip("/"))
        paths = sorted(p for p in self.entries if p.startswith(prefix))
        selected = paths[offset : offset + limit]
        end = offset + len(selected)
        return self.redactor.clean(
            {
                "prefix": prefix,
                "files": [
                    {"path": p, "mode": self.entries[p]["mode"], "size": self.entries[p]["size"]}
                    for p in selected
                ],
                "total": len(paths),
                "truncated": end < len(paths),
                "next_offset": end if end < len(paths) else None,
            }
        )

    def _text(self, path):
        safe_path(path)
        entry = self.entries.get(path)
        if entry is None:
            raise ToolError("File is not present in the inspected commit.")
        if entry["mode"] not in {"100644", "100755"} or entry["type"] != "blob":
            raise ToolError("Symlinks and submodules are not followed.")
        if entry["size"] > MAX_BLOB_BYTES:
            raise ToolError("File exceeds the 512 KiB inspection limit.")
        if path not in self.cache:
            data = self.repo.git(["cat-file", "blob", entry["oid"]])
            if b"\0" in data:
                raise ToolError("Binary files cannot be inspected as source text.")
            try:
                value = data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ToolError("File is not UTF-8 text.") from exc
            if sum(len(item) for item in self.cache.values()) + len(value) > 8 * 1024 * 1024:
                self.cache.clear()
            self.cache[path] = self.redactor.text(value)
        return self.redactor.text(self.cache[path])

    def read_file(self, path, start_line=1, max_lines=160):
        integer(start_line, "start_line", 1, 10000000)
        integer(max_lines, "max_lines", 1, 250)
        lines = self._text(path).splitlines()
        selected = lines[start_line - 1 : start_line - 1 + max_lines]
        # Long lines are capped explicitly; never claim full content was observed.
        result = [
            {"line": start_line + n, "text": value[:2000], "truncated": len(value) > 2000}
            for n, value in enumerate(selected)
        ]
        end = start_line - 1 + len(selected)
        return {
            "path": path,
            "lines": result,
            "total_lines": len(lines),
            "truncated": end < len(lines),
            "next_line": end + 1 if end < len(lines) else None,
        }

    def search_code(self, pattern, glob="*", offset=0, limit=60):
        if not isinstance(pattern, str) or not 1 <= len(pattern) <= 200:
            raise ToolError("pattern must be a literal string of 1 to 200 characters.")
        if not isinstance(glob, str) or not 1 <= len(glob) <= 200:
            raise ToolError("glob must be a string of 1 to 200 characters.")
        integer(offset, "offset", 0, 1000000)
        integer(limit, "limit", 1, 100)
        paths = sorted(p for p in self.entries if fnmatch.fnmatchcase(p, glob))
        matches, skipped = [], []
        scanned_bytes = 0
        index = offset
        while index < len(paths):
            path = paths[index]
            size = self.entries[path]["size"] or 0
            if scanned_bytes + size > MAX_SEARCH_BYTES or index - offset >= 800:
                break
            index += 1
            scanned_bytes += size
            try:
                content = self._text(path)
            except ToolError as exc:
                skipped.append({"path": path, "reason": str(exc)})
                continue
            file_matches = [
                {"path": path, "line": n, "text": line[:2000], "truncated": len(line) > 2000}
                for n, line in enumerate(content.splitlines(), 1)
                if pattern.casefold() in line.casefold()
            ]
            remaining = limit - len(matches)
            matches.extend(file_matches[:remaining])
            if len(file_matches) > remaining:
                # Repeat this file via read_file to inspect additional matches.
                return {
                    "matches": matches,
                    "truncated": True,
                    "next_offset": index,
                    "overflow_file": path,
                    "skipped": skipped,
                    "note": "More matches in overflow_file; read it with line pagination.",
                }
            if len(matches) >= limit:
                break
        return {
            "matches": matches,
            "truncated": index < len(paths),
            "next_offset": index if index < len(paths) else None,
            "scanned_files": index - offset,
            "total_files": len(paths),
            "skipped": skipped,
        }

    def git_log(self, limit=20, path=None):
        integer(limit, "limit", 1, 100)
        args = ["log", f"-{limit}", "--format=%H %aI %s", "--name-only", "HEAD"]
        if path is not None:
            args += ["--", safe_path(path)]
        output = self.repo.git(args).decode("utf-8", errors="replace")
        shallow = self.repo.git(["rev-parse", "--is-shallow-repository"]).strip() == b"true"
        return {
            "history": self.redactor.text(output),
            "shallow": shallow,
            "limit": limit,
            "scope": "Default branch, at most 100 fetched commits; not all history.",
        }

    def dispatch(self, name, arguments):
        if name not in {"list_files", "read_file", "search_code", "git_log"}:
            raise ToolError("Unknown inspection tool.")
        try:
            return self.redactor.clean(getattr(self, name)(**arguments))
        except TypeError as exc:
            raise ToolError("Invalid tool arguments; follow the declared tool schema.") from exc
