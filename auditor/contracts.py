"""Tool contracts shared by the provider and the explicit dispatch loop."""

CATEGORIES = [
    "repository hygiene",
    "dependency management",
    "code quality",
    "testing",
    "github actions / ci",
    "security",
    "configuration",
    "collaboration",
    "build and release",
]


def function(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def tool_schemas():
    purpose = {
        "purpose": {
            "type": "string",
            "description": "Brief investigation objective based on prior observations; no private chain of thought.",
        }
    }
    string = {"type": "string"}

    def integer(low, high, default):
        return {"type": "integer", "minimum": low, "maximum": high, "default": default}

    schemas = [
        function(
            "list_files",
            "List tracked files; paginate until complete before claiming absence. Prefix is literal, not a glob.",
            {
                **purpose,
                "prefix": {"type": "string", "default": ""},
                "offset": integer(0, 1000000, 0),
                "limit": integer(1, 1000, 300),
            },
            ["purpose"],
        ),
        function(
            "read_file",
            "Read numbered, redacted UTF-8 lines of a tracked regular file. Paginate with next_line.",
            {
                **purpose,
                "path": string,
                "start_line": integer(1, 10000000, 1),
                "max_lines": integer(1, 250, 160),
            },
            ["purpose", "path"],
        ),
        function(
            "search_code",
            "Case-insensitive LITERAL search over redacted text. Glob scopes paths. Offsets paginate files; skipped/overflow files mean incomplete evidence.",
            {
                **purpose,
                "pattern": {"type": "string", "minLength": 1, "maxLength": 200},
                "glob": {"type": "string", "default": "*", "minLength": 1, "maxLength": 200},
                "offset": integer(0, 1000000, 0),
                "limit": integer(1, 100, 60),
            },
            ["purpose", "pattern"],
        ),
        function(
            "git_log",
            "Observe bounded default-branch history and changed paths, with a shallow-history warning.",
            {**purpose, "limit": integer(1, 100, 20), "path": string},
            ["purpose"],
        ),
    ]
    schemas.append(
        function(
            "record_notes",
            "Save concise factual audit notes, candidate findings with quotes/observation IDs, and open questions for long investigations. Notes are not new evidence or private reasoning.",
            {"notes": {"type": "string", "maxLength": 4500}},
            ["notes"],
        )
    )
    violation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rule_id": string,
            "category": {"type": "string", "enum": CATEGORIES},
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            "file": {"type": ["string", "null"]},
            "line": {"type": ["integer", "null"], "minimum": 1},
            "description": string,
            "evidence": string,
            "recommendation": string,
            "support": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tool_call_id": string,
                    "quote": {"type": "string", "minLength": 3, "maxLength": 2000},
                },
                "required": ["tool_call_id", "quote"],
            },
        },
        "required": [
            "rule_id",
            "category",
            "severity",
            "file",
            "line",
            "description",
            "evidence",
            "recommendation",
            "support",
        ],
    }
    schemas.append(
        function(
            "submit_report",
            "Finish only after interpreting all observations and investigating alternatives. Support must exactly quote a prior successful tool result. Coverage records all nine areas, including unavailable checks, with observation IDs. Internal support and coverage are removed from final JSON.",
            {
                "violations": {"type": "array", "items": violation},
                "coverage": {
                    "type": "object",
                    "properties": {
                        c: {
                            "type": "string",
                            "minLength": 12,
                            "description": "Interpret observed facts or mark unavailable/not applicable. Cite printed observation IDs where relevant; clearly explain unavailable/not-applicable areas.",
                        }
                        for c in CATEGORIES
                    },
                    "required": CATEGORIES,
                    "additionalProperties": False,
                },
            },
            ["violations", "coverage"],
        )
    )
    return schemas
