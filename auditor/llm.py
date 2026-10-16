"""Small OpenAI-compatible HTTP adapter; no agent framework or SDK required."""

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from auditor.errors import AuditError, ContextLimitError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_env(path=".env"):
    source = Path(path)
    if not source.is_file():
        return
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name.startswith(("LLM_", "OPENAI_", "GROQ_")):
            os.environ.setdefault(name, value.strip("\"'"))


@dataclass
class Settings:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 60
    max_steps: int = 48

    @classmethod
    def from_env(cls):
        key = (
            os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        )
        model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "")
        if not key or not model:
            raise AuditError("Set GROQ_API_KEY (or LLM_API_KEY / OPENAI_API_KEY) and LLM_MODEL.")
        try:
            settings = cls(
                key,
                model,
                os.getenv(
                    "LLM_BASE_URL",
                    "https://api.groq.com/openai/v1"
                    if os.getenv("GROQ_API_KEY") and not os.getenv("LLM_API_KEY")
                    else cls.base_url,
                ).rstrip("/"),
                float(os.getenv("LLM_TIMEOUT", "60")),
                int(os.getenv("LLM_MAX_STEPS", "48")),
            )
            if not 1 <= settings.timeout <= 300 or not 4 <= settings.max_steps <= 100:
                raise ValueError
            parsed = urlsplit(settings.base_url)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
        except ValueError as exc:
            raise AuditError(
                "Invalid LLM settings: HTTPS URL, timeout 1..300, steps 4..100 required."
            ) from exc
        return settings


class ChatClient:
    def __init__(self, settings):
        self.settings = settings
        self.opener = build_opener(NoRedirect())

    def complete(self, messages, tools):
        body = json.dumps(
            {
                "model": self.settings.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "required",
            }
        ).encode()
        # Settings.from_env validates HTTPS and forbids embedded credentials; redirects are disabled.
        req = Request(  # noqa: S310
            self.settings.base_url + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + self.settings.api_key,
                "Content-Type": "application/json",
                "User-Agent": "DevOpsRepositoryAuditor/1.0",
            },
            method="POST",
        )
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=self.settings.timeout) as response:
                    raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise AuditError("LLM response exceeds size limit.")
                message = json.loads(raw)["choices"][0]["message"]
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    raise ValueError
                return {k: v for k, v in message.items() if k in {"role", "content", "tool_calls"}}
            except HTTPError as exc:
                code = ""
                if exc.code in {400, 429}:
                    try:
                        details = json.loads(exc.read(65536)).get("error", {})
                        code = details.get("code", "")
                        quota_message = str(details.get("message", ""))
                        if exc.code == 429 and "TPM" in quota_message:
                            requested = re.search(r"Requested[ :]+([0-9]+)", quota_message)
                            limit = re.search(r"Limit[ :]+([0-9]+)", quota_message)
                            if (
                                requested
                                and limit
                                and int(requested.group(1)) > int(limit.group(1))
                            ) or attempt == 2:
                                raise ContextLimitError(
                                    "LLM API HTTP 429: provider token-per-minute request budget requires compaction."
                                ) from exc
                    except (ValueError, TypeError, AttributeError):
                        pass
                    if code in {"context_length_exceeded", "request_too_large"}:
                        raise ContextLimitError("Provider request-size limit reached.") from exc
                    if code == "tool_use_failed" and attempt < 2:
                        repaired = messages + [
                            {
                                "role": "user",
                                "content": "The provider rejected the previous generated function call. Return a valid registered tool call with JSON arguments matching its schema. Use bare tool names without prefixes. Required inspection tools must be called before submit_report.",
                            }
                        ]
                        req.data = json.dumps(
                            {
                                "model": self.settings.model,
                                "messages": repaired,
                                "tools": tools,
                                "tool_choice": "required",
                            }
                        ).encode()
                        continue
                if exc.code == 413:
                    raise ContextLimitError("Provider request-size limit reached.") from exc
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    try:
                        retry_after = float(exc.headers.get("Retry-After", 2**attempt))
                    except (TypeError, ValueError, AttributeError):
                        retry_after = 2**attempt
                    time.sleep(max(0, min(60, retry_after)))
                    continue
                raise AuditError(
                    f"LLM API HTTP {exc.code}"
                    + (" (invalid generated tool call)" if code == "tool_use_failed" else "")
                    + "; verify model, credentials, quota and endpoint."
                ) from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise AuditError(
                    "LLM connection failed or timed out after three attempts."
                ) from exc
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise AuditError("LLM returned a malformed Chat Completions response.") from exc
        raise AuditError("LLM request failed.")
