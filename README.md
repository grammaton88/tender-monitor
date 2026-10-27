# Georgian IT Tender Monitor

Monitors announced IT tenders on the [Georgian State Procurement portal](https://tenders.procurement.gov.ge/public/), analyzes eligible public tender documents with Google Gemini, and emails a Georgian-language report.

**Developed by:** [Mikheil Kakabadze](https://www.linkedin.com/in/mikheil-kakabadze)

## What it does

- Searches configured CPV categories and procurement procedure types.
- Analyzes supported public documents (PDF, DOCX, XLSX, and XLSM) and flags files that need manual review.
- Caches analysis and retries pending work on later runs.
- Sends plain-text and HTML email reports.
- Runs scheduled and manual scans with GitHub Actions.
- Provides a Flask dashboard for filters, workflow runs, usage statistics, and manual runs.
- Serves the dashboard on Vercel; GitHub stores deployed settings and monitor state.

The schedule workflow wakes hourly. The dashboard's configured interval (1-168 hours) determines whether a scheduled scan is due. GitHub may delay scheduled starts; use the dashboard or GitHub Actions for a manual run.

## Deploy to Vercel

### 1. Push the project to GitHub

Push the project files listed in [Project files](#project-files) to the repository's default branch, including `.github/workflows/tender-monitor.yml`. Do not upload `.venv/`, `data/`, `.vercel/`, `.env`, or local state files.

### 2. Import the repository into Vercel

Create a Vercel project from the GitHub repository. The included `vercel.json` configures the Flask function; Vercel installs the Python packages from `requirements.txt`. The Flask dashboard is served by `app.py`, and static CSS and JavaScript are in `public/static/`.

Add these environment variables to the Vercel project. Set them for **Production** (and Preview only if you intend to use Preview deployments):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Long, random Flask session-signing key. Generate a unique value and keep it private. |
| `DASHBOARD_USERNAME` | Username for the app's sign-in form. |
| `DASHBOARD_PASSWORD` | Strong, unique password for the app's sign-in form. |
| `GITHUB_REPOSITORY` | Exact repository slug, such as `owner/repository`. |
| `GITHUB_ACTIONS_TOKEN` | Fine-grained token for the selected repository; permissions below. |

The dashboard uses its own `/login` form and a secure session cookie; it does not use the browser's HTTP Basic Authentication popup. After changing Vercel environment variables, create a new deployment so the function receives the updated values.

### 3. Create the GitHub token

Create a fine-grained personal access token limited to this repository. Grant these **repository permissions**:

| Permission | Access | Used for |
|---|---|---|
| Variables | Read and write | Read and save the dashboard's `MONITOR_CONFIG` Actions variable. |
| Actions | Read and write | Read workflow runs and dispatch a manual workflow run. |
| Contents | Read-only | Read monitor state from the `monitor-state` branch. |
| Secrets | Read and write | Optional dashboard management of GitHub Actions secrets. |
| Metadata | Read-only | Required by GitHub; normally selected automatically. |

`Variables: Read and write` is required separately; `Actions: Read and write` alone is not sufficient to access `MONITOR_CONFIG`. If you do not want to manage secrets in the dashboard, the token can omit Secrets permission and secrets can be maintained directly in GitHub. An organization may need to approve a token before it can access the repository.

Copy the token directly into Vercel's `GITHUB_ACTIONS_TOKEN` field. Store only the token itself-do not include a `Bearer` prefix. Never commit or share it. Revoking or regenerating a token invalidates the previous value; update Vercel and redeploy when replacing it.

### 4. Configure GitHub Actions secrets and workflow permissions

In the repository, open **Settings → Secrets and variables → Actions** and add:

| Actions secret | Required | Purpose |
|---|---:|---|
| `GEMINI_API_KEY` | Yes | Google AI Studio API key for the selected model. |
| `EMAIL_FROM` | Yes | Gmail address used to send reports. |
| `EMAIL_PASSWORD` | Yes | Gmail App Password, not the normal account password. |
| `EMAIL_TO` | No | Optional recipient; can also be configured from the dashboard. |

Create a Gmail App Password after enabling 2-Step Verification. The workflow declares `contents: write` so its built-in GitHub token can persist `state.json` to the `monitor-state` branch. Repository rules must allow the workflow to create or update that branch.

### 5. Start and verify

Open **Actions → IT Tender Monitor → Run workflow** for an initial manual run, or use the dashboard's **გაშვება ახლავე** button. Review the Actions log and confirm that `state.json` is present on the `monitor-state` branch. Keep that branch: it holds progress, cached analyses, and usage history.

The dashboard creates or updates the GitHub Actions variable `MONITOR_CONFIG` when settings are saved. Before that variable exists, the committed, non-secret `monitor-config.json` provides defaults.

## Configuration and data

- `monitor-config.json` contains non-secret default filters and monitor settings. It is required by the workflow as the initial/default configuration and should remain in the repository.
- `MONITOR_CONFIG` is the deployed dashboard configuration stored as a GitHub Actions repository variable. It includes CPV and procedure filters, Gemini model and quotas, analysis limits, enabled state, and schedule interval.
- `state.json` on the `monitor-state` branch stores progress, document statuses, cached analysis, errors, and recorded AI usage. It is not the same as `monitor-config.json`.
- Gemini and email credentials are GitHub Actions secrets. Secrets entered through the dashboard are encrypted with GitHub's repository public key; their existing values are never displayed.
- Vercel Functions have ephemeral filesystems, so deployed settings and state use GitHub rather than local files.

Deleting the `monitor-state` branch or its `state.json` resets history and cached analysis. A subsequent run may analyze tenders again. The `all` or `baseline` initial-scan setting controls first-run behavior.

## Run locally (Windows PowerShell)

Python 3.12 or later is recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python app.py
```

Open `http://127.0.0.1:5000/`. Local dashboard settings are saved in `monitor-config.json`; local dashboard state is stored under `data/`. With no GitHub token configured, the dashboard uses local files. To run the tender monitor locally, set `GEMINI_API_KEY`, `EMAIL_FROM`, `EMAIL_PASSWORD`, and optionally `EMAIL_TO` in the PowerShell environment before running `python monitor.py`.

`.env.example` lists environment-variable names with placeholders only; the application does not load `.env` files automatically. Set real local values in your shell or another private environment manager, and never commit them.

## Tests

Run the full test suite:

```powershell
python -B -m unittest discover -s tests -v
```

The GitHub Actions workflow runs tests before a due scan. If the schedule gate determines the interval has not elapsed, it skips dependency installation, tests, and monitor processing for that scheduled wake-up.

## Troubleshooting

| Symptom | Check |
|---|---|
| Dashboard login page or credentials rejected | Verify `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` in the correct Vercel project and environment; redeploy after changes. |
| GitHub API returns HTTP 403 for `MONITOR_CONFIG` | Verify the active token is selected for the exact repository and has **Variables: Read and write**. Also check Actions: Read and write, Contents: Read, token approval, and that Vercel has the current token. |
| Dashboard cannot manage secrets | Add **Secrets: Read and write** to the fine-grained token, or update secrets directly in GitHub Actions settings. |
| Workflow does not persist state | Check that the workflow's built-in token can write repository contents and that repository rules allow updates to `monitor-state`. |
| Vercel shows failed deployments for the `monitor-state` branch during a run | The monitor pushes progress to `monitor-state` every few seconds, and Vercel tries to build each push. `vercel.json` disables Git deployments for that branch; deploy the updated `vercel.json` from the default branch and, if needed, also set **Settings → Git → Ignored Build Step** accordingly. |
| No email received | Check the Actions run log and verify `EMAIL_FROM`, `EMAIL_PASSWORD`, and `EMAIL_TO`. |
| Gemini HTTP 429 or 503 | Check AI Studio quota/model availability. Temporary failures may be retried; unfinished work remains pending for a later run. |
| A document is flagged for manual review | Open the source attachment on the procurement portal and review it directly. Unsupported, malformed, or oversized content is not assumed to have been analyzed. |

The report is an aid to review, not a legal or procurement determination. Verify important dates, warranty terms, quantities, and confidentiality notices against the official tender documents. Eligible public document content is sent to the configured Gemini model; review Google's current data-use terms before enabling analysis.

## Project files

| Path | Purpose |
|---|---|
| `app.py` | Flask dashboard, in-app login, and GitHub API integration. |
| `monitor.py` | Tender search and monitor entry point. |
| `monitor_settings.py` | Configuration defaults, validation, and workflow environment mapping. |
| `tender_pipeline.py` | Document processing, Gemini requests, caching, reporting, email, and state. |
| `monitor-config.json` | Non-secret defaults used locally and by the workflow before `MONITOR_CONFIG` exists. |
| `.github/workflows/tender-monitor.yml` | Scheduled and manually dispatched GitHub Actions workflow. |
| `templates/` | Dashboard, login, settings, workflow history, and error-page templates. |
| `public/static/` | Dashboard CSS and JavaScript served by Vercel. |
| `tests/` | Unit tests run locally and in GitHub Actions. |
| `requirements.txt` | Python dependencies for the dashboard and monitor. |
| `vercel.json` | Vercel Flask function configuration. |
| `.env.example` | Placeholder-only reference for local environment variables. |
| `.gitignore` | Excludes local environments, credentials, caches, and runtime state. |

Local-only directories such as `.venv/` and `data/` are ignored by Git and should stay on your computer; they do not need to be deleted to keep them out of GitHub.
