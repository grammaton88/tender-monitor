# Georgian IT Tender Monitor

An automated monitor for announced information-technology tenders on the [Georgian State Procurement portal](https://tenders.procurement.gov.ge/public/). It searches configured CPV categories and procedure types, reviews available public tender documents with Google Gemini, and sends a report by email.

**Author:** [Mikheil Kakabadze](https://www.linkedin.com/in/mikheil-kakabadze)

## At a glance

- **Schedule:** GitHub Actions checks hourly; the dashboard selects a 1-168-hour interval (including 24 hours / 1 day, 48 hours / 2 days, and 72 hours / 3 days), plus manual runs.
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

The monitor currently searches IT CPV base codes and procurement procedure types selected in `monitor-config.json`. The dashboard edits this configuration; the workflow uses the same values when it starts.

### Local dashboard (JSON-based, no database)

A Georgian-language dashboard is included in `app.py`. The filter page lists every IT CPV category from `monitor.py` with its full Georgian name and a searchable checkbox, and lists the procurement procedure names with their portal IDs. `monitor-config.json` provides the non-secret local defaults; `data/state.json` holds the dashboard display state. Run locally with:

```bash
python app.py
```

Then open `http://localhost:5000` in a browser. The interface uses a restrained navy-and-white palette and adapts to mobile screens. Locally, settings are written to `monitor-config.json`. In deployment, settings are saved as the GitHub Actions repository variable `MONITOR_CONFIG`; the next scheduled or manually dispatched workflow reads that variable. This avoids committing settings or redeploying the UI on each save.

The UI supports CPV and procedure filters, email recipient, sender, Gmail app password, Gemini API key, model and quota limits, per-run analysis/time limits, first-scan mode, monitoring enablement, and automatic frequency in hours. Frequent presets are 24 hours (1 day), 48 hours (2 days), and 72 hours (3 days); supported values are 1-168 hours. Secrets entered in the UI are encrypted with GitHub's repository public key and written directly to GitHub Actions Secrets; existing secret values are never read back or displayed. The GitHub token needs **Actions: Read and write** and **Contents: Read** permissions for this repository. The left sidebar shows daily request/token totals, links to recent workflow runs and their GitHub logs, and provides a **გაშვება ახლავე** action that dispatches the workflow on the repository's default branch. Manual dispatch bypasses the selected schedule interval, but monitoring still needs to be enabled.

The GitHub Actions cron wakes hourly; a lightweight gate checks the saved state and skips dependency installation, tests, and scanning when the interval is not due. The monitor runs once the selected hour interval has elapsed. GitHub may delay scheduled starts, so this is an approximate interval, not an exact timer. Manual workflow dispatch runs immediately.

The dashboard shows daily request, input-token, output-token, total-token, and quota-error counts, with a manual refresh control. It refreshes every minute from the monitor state stored on the `monitor-state` branch. During a workflow, state and AI usage are published to that branch at most every 30 seconds, so dashboard statistics can reflect in-progress work; GitHub API and dashboard refresh intervals still introduce a short delay. Statistics cover only API usage recorded by this monitor and use the Pacific-time quota day. The workflow-runs page refreshes run status every 30 seconds, shows the active GitHub job step when available, and includes a manual refresh and GitHub permission checks. Manual workflow dispatch is blocked when the dashboard detects a queued or running monitor workflow.

Every page includes a bottom-right back-to-top control and a right-aligned footer. The workflow-runs page uses live GitHub API checks to show whether the repository, workflow, configuration, secrets, and monitor state are accessible. GitHub API credentials remain server-side and are not included in browser responses.

### Vercel deployment

The repository is configured for Vercel's Python/Flask runtime. Flask serves dynamic dashboard routes as a Vercel Function; CSS and JavaScript assets are in `public/static/` so Vercel can serve them as static assets. Dashboard settings and monitor state must use GitHub storage because Vercel Functions have ephemeral filesystems.

1. Push the repository to GitHub and import it into Vercel as a project. Vercel detects `app.py` as the Flask entrypoint, installs `requirements.txt`, and uses `vercel.json` to configure the function's maximum duration.
2. Add these environment variables in the Vercel project settings for the Production environment (and Preview if desired):
   - `GITHUB_REPOSITORY` — repository slug, for example `owner/repository`.
   - `GITHUB_ACTIONS_TOKEN` — fine-grained repository token with Actions read/write, Contents read, and repository metadata read permissions.
   - `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` — HTTP Basic Authentication credentials for the dashboard.
   - `SECRET_KEY` — a long, random value used to sign Flask sessions.
3. Deploy or redeploy the project after setting the variables.
4. In GitHub repository settings, allow Actions to write repository contents so the workflow can persist state to `monitor-state`. Add `GEMINI_API_KEY`, `EMAIL_FROM`, `EMAIL_PASSWORD`, and optionally `EMAIL_TO` as GitHub Actions Secrets.
5. Open the deployed dashboard and save settings. Manual launches are available from the dashboard or from **Actions > IT Tender Monitor > Run workflow**.

Do not deploy `.venv/`, `__pycache__/`, or local `data/state.json`. The `.gitignore` excludes local environments, Vercel metadata, caches, credentials, and local monitor state. The Vercel Hobby plan is subject to its monthly usage allowances and personal/non-commercial use terms; check the current [Hobby plan limits](https://vercel.com/docs/plans/hobby) and [Flask deployment guide](https://vercel.com/docs/frameworks/backend/flask).

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
| `EMAIL_TO` | No | Optional recipient secret; it can be securely updated in the dashboard. |

Create a [Gmail App Password](https://myaccount.google.com/apppasswords) after enabling 2-Step Verification. Never place credentials in source code, README files, workflow logs, or committed state. Secrets can be managed either from this authenticated dashboard or directly in GitHub Actions Secrets.

Non-secret runtime settings are managed in the dashboard and saved in the Actions variable `MONITOR_CONFIG`, rather than separate Actions variables. This includes CPV/procedure filters, Gemini model/quotas and processing limits. A quota value of `0` means no local cap is configured; Google still enforces its own limits. Check [AI Studio rate limits](https://aistudio.google.com/rate-limit?timeRange=last-28-days) before changing them. Usage counters cover only requests recorded by this monitor and follow Pacific Time.

## First-time setup and operation

1. In **Settings > Actions > General**, enable Actions and set workflow permissions to **Read and write permissions**. Make sure repository rules permit the workflow to create or update `monitor-state`.
2. Add `GEMINI_API_KEY`, `EMAIL_FROM`, `EMAIL_PASSWORD`, and optionally `EMAIL_TO` as Actions Secrets. Configure the Vercel environment variables as described above.
3. Open **Actions > IT Tender Monitor** and select **Run workflow** to start a manual run.
4. Review the Actions log and the email. Confirm the workflow has created or updated `state.json` on `monitor-state`.
5. Keep the `monitor-state` branch. It contains the saved progress required for analysis reuse and pending retries.

The workflow wakes hourly and only performs a scheduled run when the interval chosen in the dashboard has elapsed. Scheduled runs may start late because GitHub does not guarantee exact start times. GitHub may disable scheduled workflows in inactive public repositories.

### State and reset behavior

The `monitor-state` branch holds the state file, which includes tender metadata, document statuses, cached AI analyses, and this monitor's usage records. The workflow saves progress even when processing or email delivery fails, when a state file was created.

Deleting the `monitor-state` branch or its `state.json` resets history and cache. The next run behaves like a first run and may analyze tenders again. The dashboard's initial-scan setting (`all` or `baseline`) controls first-run handling; it is not a general cache-reset switch.

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

To run the monitor locally, set the secret environment variables `GEMINI_API_KEY`, `EMAIL_FROM`, `EMAIL_PASSWORD`, and `EMAIL_TO`. Configure non-secret options in `monitor-config.json`, then run:

```powershell
python monitor.py
```

By default, local state is written to `state.json`; set `STATE_PATH` to use a different location. Do not commit credentials or runtime state.

## Project files

| Path | Purpose |
|---|---|
| `monitor.py` | Portal search, IT CPV categories, and application entry point |
| `monitor-config.json` | Local default configuration; deployed settings are stored in GitHub Actions variable `MONITOR_CONFIG` |
| `monitor_settings.py` | Configuration validation and workflow environment mapping |
| `app.py` | Authenticated Flask dashboard and GitHub configuration/secret management |
| `templates/` | Dashboard, settings, run history, and error page templates |
| `public/static/` | CSS and JavaScript files served as Vercel static assets |
| `tender_pipeline.py` | Document handling, Gemini requests, caching, reporting, email, and saved state |
| `tests/` | Automated dashboard and monitor unit tests; the workflow runs these before monitoring |
| `requirements.txt` | Python dependencies |
| `vercel.json` | Vercel Function configuration |
| `.github/workflows/tender-monitor.yml` | Scheduled and manual GitHub Actions workflow |
| `.env.example` | Names of local environment variables; contains placeholders only |
| `.gitignore` | Excludes local environments, credentials, runtime state, and Vercel metadata |

---

Maintained by [Mikheil Kakabadze](https://www.linkedin.com/in/mikheil-kakabadze).
