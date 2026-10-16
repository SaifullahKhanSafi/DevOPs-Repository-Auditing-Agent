"""Read a disposable bare clone; never check out or execute target code."""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from auditor.errors import AuditError, ToolError

MAX_GIT_OUTPUT = 12 * 1024 * 1024


def normalize_url(value):
    try:
        parsed = urlsplit(value)
        parts = parsed.path.strip("/").removesuffix(".git").split("/")
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "github.com"
            or parsed.query
            or parsed.fragment
            or len(parts) != 2
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)
            or any(part in {".", ".."} for part in parts)
        ):
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise AuditError("Use a public HTTPS URL: https://github.com/owner/repository") from exc
    return "https://github.com/" + "/".join(parts)


def git_env():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
        }
    )
    return env


def run_git(args, timeout=45, cwd=None):
    command = [
        "git",
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "credential.helper=",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "http.followRedirects=false",
        *args,
    ]
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=git_env(),
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
            if result.returncode:
                raise ToolError("Git operation failed; verify URL, public access, Git and network.")
            if output.tell() > MAX_GIT_OUTPUT:
                raise ToolError("Git output exceeds safety limit; narrow the request.")
            output.seek(0)
            return output.read()
    except FileNotFoundError as exc:
        raise AuditError("Git is required; install Git and put it on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError("Git operation timed out.") from exc


class Repository:
    def __init__(self, url, timeout=180):
        self.url = normalize_url(url)
        self.timeout = timeout
        self._temp = None

    def __enter__(self):
        self._temp = tempfile.TemporaryDirectory(prefix="devops-audit-")
        self.path = Path(self._temp.name) / "objects.git"
        try:
            run_git(
                [
                    "clone",
                    "--bare",
                    "--depth=100",
                    "--single-branch",
                    "--no-tags",
                    "--",
                    self.url + ".git",
                    str(self.path),
                ],
                timeout=self.timeout,
            )
            self.commit = self.git(["rev-parse", "HEAD"]).decode().strip()
            return self
        except BaseException:
            self._temp.cleanup()
            raise

    def git(self, args):
        return run_git(["--git-dir=" + str(self.path), *args])

    def __exit__(self, *args):
        self._temp.cleanup()
