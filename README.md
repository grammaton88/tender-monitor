# Georgian IT Tender Monitor

An automated monitor for announced information-technology tenders on the [Georgian State Procurement portal](https://tenders.procurement.gov.ge/public/). It searches configured CPV categories, reviews available public tender documents with Google Gemini, and sends a daily report by email.

**Author:** [Mikheil Kakabadze](https://www.linkedin.com/in/mikheil-kakabadze)

## At a glance

- **Schedule:** daily at 06:00 UTC (10:00 Tbilisi time), plus manual runs from GitHub Actions.
- **Runtime:** GitHub Actions with Python 3.12; no always-on server or external database.
- **AI output:** concise Georgian keywords for the procurement subject, delivery period, warranty, and explicit references to confidential materials.
- **Documents:** PDF, DOCX, XLSX, and XLSM. Unsupported, malformed, or oversized files are reported for manual review.
- **State:** saved as `state.json` on the `monitor-state` branch so progress and analysis cache survive between runs.

## How it works

1. `monitor.py` searches announced tenders in the configured IT CPV categories and paginates through the portal results.
2. For each tender, the monitor discovers public documentation and downloads available attachments.
3. Eligible documents for a tender are sent together in one Gemini analysis request. The prompt asks for short, factual values only; it does not ask Gemini for a long narrative or a general tender assessment.
4. Results are cached using the model, analysis version, and document content. The app can reuse a matching cached result rather than make another Gemini generation request. If the model, extraction rules, or document content changes, a new analysis may be required.
5. Pending work is saved and retried on a later run. Per-run request and time limits defer remaining work rather than intentionally discard it.
6. The report is sent as both plain text and HTML. Its subject includes the current Tbilisi date and time (UTC+04:00).

The monitor currently searches the IT CPV base codes defined in `monitor.py`. Edit that list if the scope of monitored procurement categories needs to change. You can also limit results to a procurement procedure type by setting `APP_TYPE` to one of the supported codes such as `NAT`, `SPA`, `CON`, or `GEO` (or `0`/`ALL` to disable the extra filter).

## Prerequisites

- A GitHub repository containing this project and GitHub Actions enabled.
- A Google AI Studio project and Gemini API key with access to the selected model.
- A Gmail account for delivery, with 2-Step Verification enabled and a Gmail App Password created.
- Repository permission for the workflow to write the `monitor-state` branch.

Gemini model availability, quotas, pricing, and data-use terms can change. Check the current [AI Studio rate limits](https://aistudio.google.com/rate-limit?timeRange=last-28-days) and [Gemini API pricing and terms](https://ai.google.dev/gemini-api/docs/pricing) before selecting a model or relying on free-tier capacity.

## GitHub Actions configuration

Add the project files, `requirements.txt`, `.gitignore`, `tests/test_monitor.py`, and `.github/workflows/tender-monitor.yml` to the repository's default branch. The workflow installs dependencies and runs the tests before starting the monitor.

Go to **Settings > Secrets and variables > Actions**. Store credentials as **secrets**:

| Secret | Required | Description |
|---|---:|---|
| `GEMINI_API_KEY` | Yes | Gemini API key from your Google AI Studio project |
| `EMAIL_FROM` | Yes | Gmail address used to send the report |
| `EMAIL_PASSWORD` | Yes | Gmail App Password; do not use your normal Gmail password |
| `EMAIL_TO` | Yes | Report recipient address |

Create a [Gmail App Password](https://myaccount.google.com/apppasswords) after enabling 2-Step Verification. Never place credentials in source code, README files, workflow logs, or committed state.

Set these **Actions variables** under **Settings > Secrets and variables > Actions > Variables**. The values below match the current repository configuration shown in the project setup screenshot. Confirm Gemini limits in AI Studio before changing them; quotas can vary by model and project.

| Variable | Current value | Details |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Model identifier available to your API key. The app does not choose a model automatically. |
| `GEMINI_RPD_LIMIT` | `400` | Configured Gemini requests-per-day limit used by the monitor's local safety check. |
| `GEMINI_RPM_LIMIT` | `8` | Configured requests-per-minute limit; the monitor uses it to pace calls. |
| `GEMINI_TPM_LIMIT` | `200000` | Configured input-tokens-per-minute limit; also used when pacing calls. |
| `INITIAL_SCAN_MODE` | `all` | Analyze existing tenders on the first initialization. `baseline` instead records initial document hashes without analyzing unchanged existing documents. |
| `MAX_ANALYSES_PER_RUN` | `30` | Maximum Gemini generation requests per run. Remaining tenders are deferred and retried in later runs. |
| `MAX_RUN_MINUTES` | `50` (workflow default) | Analysis time budget. This variable is optional; if unset, the workflow supplies `50`. The workflow timeout is 90 minutes. |
| `GEMINI_TPD_LIMIT` | Unset | Optional local daily input-token budget. Leave unset unless you want an additional daily cap. |

Blank or `0` for a quota variable means **unknown / not locally configured**, not unlimited. These are local pacing and safety settings; Google independently enforces account and model quotas and may reject requests. Keep configured values aligned with the limits currently shown for your model in [AI Studio](https://aistudio.google.com/rate-limit?timeRange=last-28-days). The monitor's usage counters cover only its recorded requests and tokens, not all project usage. Daily quota accounting follows Pacific Time.

## First-time setup and operation

1. In **Settings > Actions > General**, enable Actions and set workflow permissions to **Read and write permissions**. Make sure repository rules permit the workflow to create or update `monitor-state`.
2. Add the required secrets and configure the Actions variables above. The listed values are the current setup; update them in GitHub if you change the model or its quota limits.
3. Open **Actions > IT Tender Monitor** and select **Run workflow** to start a manual run.
4. Review the Actions log and the email. Confirm the workflow has created or updated `state.json` on `monitor-state`.
5. Keep the `monitor-state` branch. It contains the saved progress required for analysis reuse and pending retries.

The workflow runs automatically each day at 06:00 UTC. Scheduled runs may start late because GitHub does not guarantee exact start times. GitHub may disable scheduled workflows in inactive public repositories. No personal access token is required by the included workflow.

### State and reset behavior

The `monitor-state` branch holds the state file, which includes tender metadata, document statuses, cached AI analyses, and this monitor's usage records. The workflow saves progress even when processing or email delivery fails, when a state file was created.

Deleting the `monitor-state` branch or its `state.json` resets history and cache. The next run behaves like a first run and may analyze tenders again. `INITIAL_SCAN_MODE=baseline` also changes first-run handling; it is not a general cache-reset switch.

## Documents, limits, and retries

- A single downloaded attachment is limited to 12 MiB. Office documents are also checked for expanded archive size and extracted-text limits.
- A combined Gemini request is kept within configured byte and text safety limits. If a tender's eligible documents cannot fit, affected material is flagged for manual review rather than silently assumed to be analyzed.
- Gemini API requests use retries for temporary overload/server responses. Persistent network, quota, or time-budget failures leave work pending for a later run.
- Content that was read and marked skipped is not parsed repeatedly when its hash is unchanged. A file rejected before its contents can be hashed (for example, an HTML/session response or download-size rejection) may be checked again on a later run.
- If the analysis budget is reached, subsequent tenders are deferred. Increase `MAX_ANALYSES_PER_RUN` only when the model quota and total run time allow it.

## Reading the email and troubleshooting

| Email/log message | Meaning and next step |
|---|---|
| `Per-run analysis budget reached` | The run reached `MAX_ANALYSES_PER_RUN`. Remaining work is retained for a later run; increase the limit if appropriate. |
| Pending or incomplete analysis | A temporary portal, download, API, quota, or time-limit issue prevented completion. Inspect the Actions log; pending tenders are retried. |
| Manual-review/skipped-file note | A document could not safely be parsed or included. Open the original attachment on the procurement portal and review it directly. |
| HTTP 429 | A rate or quota limit was reached. Check AI Studio usage and confirm the configured limits match the selected model. |
| HTTP 503 | Gemini may be temporarily overloaded. The monitor retries selected temporary server errors and defers work if the failure persists. |
| Search/CPV error | Tender discovery for one or more categories may be incomplete. Check the workflow log; the email indicates that discovery was not complete. |
| Email not received | Check workflow completion and SMTP errors in the Actions log, and verify `EMAIL_FROM`, `EMAIL_TO`, and the Gmail App Password. |

The daily email is not a guarantee that every tender or every attachment was analyzed. Check the processing status and error summary, and use the Actions log for technical details.

## Privacy and responsible use

The monitor downloads public tender documents and submits eligible document content to the configured Gemini model. Review Google's current data-use terms and your organization's requirements before enabling AI analysis. The GitHub repository's visibility and access permissions also apply to the `monitor-state` branch.

AI extraction may omit or misinterpret information. Treat report values as an aid to review, not as a legal or procurement determination. Verify important requirements-including deadlines, warranty terms, quantities, and confidentiality notices-against the official tender and source documents.

## Run locally

Python 3.12 or later is recommended. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
```

To run the monitor locally, configure `GEMINI_API_KEY`, `GEMINI_MODEL`, `EMAIL_FROM`, `EMAIL_PASSWORD`, and `EMAIL_TO` in your process environment, then run:

```powershell
python monitor.py
```

Optional quota and run settings can be supplied as environment variables. By default, local state is written to `state.json`; set `STATE_PATH` to use a different location. Do not commit credentials or runtime state.

## Project files

| Path | Purpose |
|---|---|
| `monitor.py` | Portal search, IT CPV categories, and application entry point |
| `tender_pipeline.py` | Document handling, Gemini requests, caching, reporting, email, and saved state |
| `tests/test_monitor.py` | Automated unit tests; the workflow runs these before monitoring |
| `requirements.txt` | Python dependencies |
| `.github/workflows/tender-monitor.yml` | Scheduled and manual GitHub Actions workflow |

---

Maintained by [Mikheil Kakabadze](https://www.linkedin.com/in/mikheil-kakabadze).
