# Verification record

Verified on 2026-10-16 (Asia/Karachi). Local environment: Windows, Python 3.12.7, Git 2.51.0.

| Check | Observed result |
| --- | --- |
| Offline regression suite | **48 tests passed**; real Git fixtures, adaptive provider doubles, evidence/JSON validation, redaction, API errors, context recovery, resume and trace protection |
| Ruff lint/format | Passed |
| Public repository tools | Real GitHub acquisition, discovery, read, search and history succeeded without target execution |
| Authentic live Groq sample | Completed against `octocat/Hello-World`, commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`, using `openai/gpt-oss-120b`; **0 violations** |
| Hosted CI | Six Linux/Windows Python 3.11/3.12/3.13 jobs passed, including tests, lint/format, package build and installed CLI |
| Hosted live audit | Completed successfully with the encrypted repository secret; downloaded artifact independently verified to contain the exact report contract, a completed trace, and 0 violations |
| Fresh public clone | Cloned into a new directory, installed into a clean virtual environment, then ran installed CLI from outside the source directory |
| Credential publication check | Staged source and sample checked for the configured API key; `.env` and `.tools/` excluded |

Evidence: [sample report](../sample_report.json), [full public sample trace](sample_trace.jsonl), [sample provenance](sample_provenance.json), [hosted verification](hosted_validation.json), [CI run](https://github.com/SaifullahKhanSafi/DevOPs-Repository-Auditing-Agent/actions/runs/38869613081), [hosted live audit](https://github.com/SaifullahKhanSafi/DevOPs-Repository-Auditing-Agent/actions/runs/38869615277). Exact commits are recorded in the provenance/hosted evidence. The latest commit's CI status is visible on the repository's Actions page.

Live fixture evaluation, when included under `live_evaluation/`, uses independently declared **local synthetic** defects and real provider calls. Its placeholder repository field is not a public-repository audit. Offline provider doubles are not accuracy evidence. No hidden-repository scores, unseen answer keys, or instructor marks are claimed.

The source and authentic sample are published at [the submission repository](https://github.com/SaifullahKhanSafi/DevOPs-Repository-Auditing-Agent). The student must submit that public URL through the designated course channel.

## Remaining accuracy verification

The real-provider known-defect fixture did not produce a completed validated report. Groq returned request-size/rate limits despite bounded context recovery; earlier attempts also exposed citation/protocol issues addressed by regression tests. The most recent Qwen attempt ended with `Provider request-size limit persists after context compaction.` No precision, recall or F1 score is claimed for these incomplete runs. The successful public sample and hosted live audit establish end-to-end operation on a small repository, not detection performance on larger or hidden repositories. This is an unresolved validation limitation, not a passed accuracy gate.
