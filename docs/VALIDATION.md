# Local verification record

Verified on Windows with Python 3.12.7 and Git 2.51.0 on 2026-10-16 (Asia/Karachi).

- Full offline suite: **36 tests passed** (`python -m unittest discover -s tests -v`).
- Ruff lint and format checks passed.
- Source distribution and wheel builds succeeded using the configured local build tools.
- Wheel installation into a separate directory and CLI `--help` passed outside the source directory.
- Source archive inspection confirmed setup/docs/tests are included and `.env` is excluded.
- Real public GitHub acquisition/tool smoke check passed against `octocat/Hello-World`, commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`: discovery, numbered read, literal search and history. Disposable clone cleanup completed.

The offline suite uses a provider test double; it is not real-model precision/recall evidence. The public-repository smoke check verifies acquisition/tools, not an LLM-generated report.

Pending: configure `GROQ_API_KEY`, run the real agent, generate `sample_report.json` and its trace/provenance, assess detection on independently annotated public cases, publish to the supplied public GitHub repository, and verify hosted CI/fresh-clone execution. No live provider success, hidden-repository score, completed public submission or passing remote CI is claimed.
