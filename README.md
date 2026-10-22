# Georgian IT Tender Monitor

Daily monitoring of announced IT tenders on the
[Georgian procurement portal](https://tenders.procurement.gov.ge/public/).
Runs through GitHub Actions, analyzes public documentation with Gemini, and emails
a professional Georgian report.

## Features

- Searches all configured IT CPV categories and result pages.
- Emails numbered tenders, totals, individual links, document findings and errors.
- Supports PDF, DOCX and XLSX/XLSM; flags unsupported or oversized files.
- Analyzes only new/changed content for the selected model and retries pending work.
- Includes scanner usage counters and quota bars, not account-wide remaining quota.
- Saves history on the `monitor-state` branch.

## GitHub setup

Upload the source files, `requirements.txt`, `.gitignore`, `tests/test_monitor.py`
and `.github/workflows/tender-monitor.yml` to the default branch. Keep the tests:
the workflow runs them without real AI calls or emails.

Open **Settings > Secrets and variables > Actions**.

### Secrets

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | Gemini API key from your project |
| `EMAIL_FROM` | Sending Gmail address |
| `EMAIL_PASSWORD` | Gmail App Password, not your normal password |
| `EMAIL_TO` | Recipient email address |

Enable Google Account 2-Step Verification to create an
[App Password](https://myaccount.google.com/apppasswords).
Never commit credentials; revoke exposed keys.

### Variables

| Name | Recommended value |
|---|---|
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` |
| `MAX_ANALYSES_PER_RUN` | `1` for testing; `10` after verification |
| `INITIAL_SCAN_MODE` | `all` |
| `GEMINI_RPM_LIMIT` | Your model's requests/minute limit |
| `GEMINI_TPM_LIMIT` | Your model's input tokens/minute limit |
| `GEMINI_RPD_LIMIT` | Your model's requests/day limit |

Verify free-tier availability and limits in
[AI Studio](https://aistudio.google.com/rate-limit?timeRange=last-28-days).
Do not reuse another model's limits. Blank/zero limits mean unknown, not unlimited.
Leave `GEMINI_TPD_LIMIT` unset unless you want a local daily input-token budget.
Daily usage resets at midnight Pacific time; unused quota does not accumulate.

`INITIAL_SCAN_MODE=baseline` records initial document hashes without analysis.
Switching models can require fresh analysis because the cache is model-specific.

### Permissions and first run

1. Enable Actions and permit **Read and write permissions** under
   **Settings > Actions > General**. Branch rules must allow updates to `monitor-state`.
2. Select **Actions > IT Tender Monitor > Run workflow**.
3. Verify the email, document results and `monitor-state/state.json` branch update.
4. Run again to verify completed unchanged analyses are reused.

No personal access token, external database or separate server is required.
The schedule is **10:00 Tbilisi time (06:00 UTC)** daily, subject to GitHub delays.
Public-repository schedules may be disabled after 60 days without activity.

## Errors, cost and privacy

- Gemini failures appear in the daily email with pending status and retry information.
  A green workflow does not prove analysis succeeded.
- `Per-run analysis budget reached` means queued work; increase the configured budget
  within your quota. Unsupported/oversized documents need manual review.
- HTTP 429 means a rate/quota limit; HTTP 503 can indicate temporary overload.
- SMTP outages, startup errors or runner termination may prevent email delivery.
  Check Actions logs. Failed searches are reported as incomplete discovery.
- Standard public-repository Linux runners are free; private repositories have
  allowances. Gemini free capacity is limited and may change. For strictly free
  usage, use a project without paid billing enabled.
- State has the repository's visibility and includes public metadata, AI results,
  links and usage history. Do not delete it unless intentionally resetting history.
- Only public documents are processed. Review Gemini's
  [pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing).
  AI summaries and source references require human verification.
- State and email delivery are not transactional; rare duplicate emails are possible.

## Local tests

Python 3.12+:

```powershell
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
```
