"""Redact repository secrets before tools return data to the LLM or trace."""

import re


class Redactor:
    def __init__(self, secrets=()):
        self.secrets = {value for value in secrets if value and len(value) >= 4}

    def text(self, value):
        patterns = [
            r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,})\b",
            r"(?i)(?:https?://)[^\s/@:]+:[^\s/@]+@",
            r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, value):
                self.secrets.add(match.group())
        assignment = re.compile(
            r"""(?ix)(?:["']?)(?:[A-Z0-9_]*(?:api[_-]?key|secret|password|passwd|token|credential)[A-Z0-9_]*)(?:["']?)[ \t]*[:=][ \t]*(?:["']([^"'\r\n]+)["']|([^\s,;\r\n]+))"""
        )
        for match in assignment.finditer(value):
            candidate = match.group(1) or match.group(2)
            if match.group(2) and candidate.lower() in {"true", "false", "null", "none"}:
                continue
            if candidate and not candidate.startswith(
                ("${", "os.", "environ", "getenv", "process.env", "{{", "[REDACTED]")
            ):
                self.secrets.add(candidate)
        for secret in sorted(self.secrets, key=len, reverse=True):
            replacement = "[REDACTED]" + "\n" * secret.count("\n")
            if len(secret) < 8:
                value = re.sub(
                    r"(?<![A-Za-z0-9_])" + re.escape(secret) + r"(?![A-Za-z0-9_])",
                    lambda match, replacement=replacement: replacement,
                    value,
                )
            else:
                value = value.replace(secret, replacement)
        return value

    def clean(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if isinstance(value, dict):
            return {self.text(str(key)): self.clean(item) for key, item in value.items()}
        return value
