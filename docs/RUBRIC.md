# Assignment requirements and rubric evidence

Source: Assignment_2_DevOps_Repository_Auditing_Agent_Updated.pdf, three pages. This is a requirements mapping, not a prediction of the instructor's grade. The assignment document supplies the project specification; instructions about submitting through the course channel are actions for the student.

| Assessment | Weight | Implementation and evidence | Verification limit |
| --- | ---: | --- | --- |
| Agent architecture and dynamic tool selection | 20% | `auditor/loop.py`, `llm.py`, `contracts.py`: explicit LLM/function loop, observation return, follow-up calls, recoverable validation; adaptive provider test selects a file based on actual discovery | Real-model trace must be generated with configured Groq credentials |
| Inspection-tool implementation | 15% | `tools.py`: required `list_files`, `read_file`, `search_code`, `git_log`; Git-backed tools tested on real local Git fixtures | Static inspection; no target execution |
| Hidden repository detection / precision and recall | 30% | Nine-area policy in `auditor/prompts.py`; evidence validation; alternative-tool and healthy-repo policies; `scripts/evaluate.py` for reviewed metrics | Unknown hidden repositories/answer keys prevent a defensible score claim; offline provider tests are not a detection benchmark |
| Evidence, severity and recommendations | 15% | `auditor/report.py`: exact observed quote/location support, valid severity, required nonempty recommendations, exact-location deduplication; prompt supplies consequence-based severity guidance | Human review is still needed for semantic accuracy and near-duplicate findings |
| Reliability, error handling, safe execution | 10% | Disposable bare clone, no checkout or target execution, safe paths, bounds/timeouts, redaction, no raw API errors, atomic reports, nonzero fatal exits, recorded limitations | Redaction/prompt defenses are heuristic; clone disk quota should be supplied by the host for hostile targets |
| JSON compliance, tests and documentation | 10% | Strict report fields and types, null locations, empty findings allowed; `docs/report.schema.json`; unittest suite, README, `.env.example`, installable project, CI | Authentic sample requires a real provider run; public CI is unverified until published/run |

## Required deliverables

- `agent.py`: exact `--repo` and `--output` CLI, unattended.
- `tools.py`: all four mandatory tools.
- `auditor/`: provider adapter, manual agent control flow, policy, contracts, report validation, acquisition and redaction.
- `requirements.txt` and `pyproject.toml`: installable Python 3.11+ standard-library runtime; no prohibited frameworks.
- `.env.example`: Groq and provider variable names without credentials. Actual `.env` is ignored.
- `README.md`: installation, Groq setup, architecture, CLI, safety, limits, tests and CI.
- `tests/`: automated tools, agent, provider, CLI and evaluation tests.
- `sample_report.json`: must be created by `scripts/generate_sample.py` using the real agent and configured API key. Do not replace this with a fabricated fixture report.
- Public GitHub repository: `https://github.com/SaifullahKhanSafi/DevOPs-Repository-Auditing-Agent`.

## Scope and precision checks

All nine assignment categories are included in the investigation policy and required trace coverage. Inspections recognize equivalent solutions, and absent optional tools/files alone cannot justify a defect. Remote branch protection is explicitly unknown without evidence. No ML datasets/training/model validation/experiment tracking are introduced. Tests/ruff/build run against this auditor's own code only; target repository code is never run. Findings and traces redact credentials and use one-based locations or null.

## Submission gates

1. Save a valid `GROQ_API_KEY` locally in `.env`; select a tool-capable accessible `LLM_MODEL`.
2. Run all local verification commands from README. The GitHub Linux/Windows matrix is a separate verification step.
3. Generate a real `sample_report.json`, trace and provenance using the command in README. Inspect unsupported claims, severities, remediation and omissions.
4. Exercise the real provider against independently known defective and healthy public repositories. Review and score findings; do not claim test-double results as precision/recall.
5. Publish the source and real sample to the public repository. Exclude `.env`, `.tools`, environments and generated build artifacts.
6. Confirm GitHub CI succeeds, then clone fresh, install dependencies, configure the API and run the exact assignment command successfully.
7. Submit only the public repository URL through the designated course channel.

Implementation and local checks cannot certify hidden-repository recall, instructor marks, remote settings or a successful hosted CI run. Pending gates must remain visible until they are actually completed.
