# Georgian IT Tender Monitor

Checks announced IT tenders on the [Georgian procurement portal](https://tenders.procurement.gov.ge/public/), analyzes their public documents with Gemini, and emails a daily Georgian report.

## What it does

- Searches the configured IT CPV categories and their result pages.
- Extracts short Georgian keywords for four fields: procurement subject, delivery period, warranty, and explicit references to confidential materials.
- Supports PDF, DOCX, XLSX and XLSM files. Unsupported, oversized, or unreadable files are flagged for manual review.
- Combines eligible documents from a tender into one Gemini analysis request. Results are cached by model, analysis version, and document content, so unchanged results are reused. New or changed content and analysis-rule/model changes may require a new request.
- Retries pending work in later runs. Unchanged files marked as skipped after content was read are not re-parsed; files rejected during download may be checked again.
- Sends a compact, Gmail-width report. The subject includes the date and time in Tbilisi time (UTC+04:00).
- Tracks model usage counters for this scanner, not the account-wide remaining quota.

## GitHub Actions setup

Add the application files, `requirements.txt`, `.gitignore`, `tests/test_monitor.py`, and `.github/workflows/tender-monitor.yml` to your repository's default branch. The workflow runs tests before starting the monitor.

In **Settings > Secrets and variables > Actions**, add these **secrets**:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | API key from your Google AI Studio project |
| `EMAIL_FROM` | Gmail address used to send the report |
| `EMAIL_PASSWORD` | Gmail App Password (not your normal password) |
| `EMAIL_TO` | Report recipient |

Enable 2-Step Verification to create a [Gmail App Password](https://myaccount.google.com/apppasswords). Never put API keys or passwords in source code or commit them to Git.

Add these **variables** as needed. Check the model's current limits in [AI Studio](https://aistudio.google.com/rate-limit?timeRange=last-28-days); do not copy limits from a different model.

| Variable | Recommended/default | Purpose |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Model name available to your API key |
| `MAX_ANALYSES_PER_RUN` | `10` | Maximum Gemini analysis requests per run; increase carefully within quota |
| `MAX_RUN_MINUTES` | `50` | Stop analysis before the workflow timeout; remaining work is saved for a later run |
| `INITIAL_SCAN_MODE` | `all` | `all` analyzes initial tenders; `baseline` records existing document hashes without analyzing them |
| `GEMINI_RPM_LIMIT` | Your model's requests/minute limit | Paces requests; blank or `0` means unknown |
| `GEMINI_TPM_LIMIT` | Your model's input tokens/minute limit | Paces requests; blank or `0` means unknown |
| `GEMINI_RPD_LIMIT` | Your model's requests/day limit | Local daily request cap; blank or `0` means unknown |
| `GEMINI_TPD_LIMIT` | Unset | Optional local daily input-token budget; blank or `0` means unknown |

The model provider may impose other limits regardless of these settings. Gemini free-tier availability and terms can change; verify them before relying on free usage.

### Enable and run

1. Under **Settings > Actions > General**, enable Actions and allow **Read and write permissions**. Branch rules must allow the workflow to update `monitor-state`.
2. Open **Actions > IT Tender Monitor > Run workflow** for a manual run. Otherwise, it runs daily at 06:00 UTC (10:00 Tbilisi time); GitHub may delay scheduled runs.
3. Check the workflow log and email. The `monitor-state` branch stores `state.json`, including tender history and analysis cache. Keep this branch to preserve progress between runs.
4. Run again to confirm unchanged analyses are reused.

No personal access token, external database, or separate server is required. GitHub may disable scheduled workflows in inactive public repositories.

## Understanding the report and errors

- **Per-run analysis budget reached:** work was deferred, not lost. It will be retried on a later run; raise `MAX_ANALYSES_PER_RUN` if appropriate for the model's quota and runtime.
- **Pending/incomplete:** a temporary download, portal, Gemini, quota, or time-limit issue stopped processing. The next run retries it.
- **Manual review/skipped file:** unsupported, malformed, or oversized content could not be analyzed. Review the original attachment on the procurement portal.
- **HTTP 429:** rate or quota limit. Check AI Studio usage and the configured limits.
- **HTTP 503:** temporary Gemini overload; the app retries before deferring work.
- Search, startup, email, and runner failures are visible in the Actions log. If a run ends before email delivery, use the log to identify the cause.

AI output can miss or misinterpret requirements. Verify important details against the original tender documents before acting. Only public tender documents are processed; review Google's [Gemini pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing). Repository state follows the repository's visibility.

## Run locally

Python 3.12 or later is recommended. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
```

For a local monitor run, set the required secrets as environment variables and run `python monitor.py`. Do not commit local credentials or `state.json`.
