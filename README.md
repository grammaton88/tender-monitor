# Georgian IT Tender Monitor

Daily incremental monitor for announced IT tenders on
[the Georgian procurement portal](https://tenders.procurement.gov.ge/public/).
Uses GitHub Actions, Gemini document analysis, Git-backed state, and Gmail SMTP.

## Daily behavior

1. Search every configured IT CPV code with the existing announced-status filter.
   Fetch all search-result pages and deduplicate tenders.
2. Read each active tender's documentation tab with the same portal session.
   Discover both `mode=app` and `mode=que` public attachments.
3. Download documents and compare SHA-256 hashes. Reuse completed analyses for
   unchanged content and the same model; analyze new/changed documents only.
4. Send one daily email containing new tenders, document updates, incomplete work,
   and a compact Gemini usage chart. A no-change report is also sent.
5. Save history to the dedicated `monitor-state` branch, including when processing
   or email delivery fails. Incomplete tenders are retried on subsequent runs,
   including previously found tenders that are no longer announced.

PDF files are submitted directly to Gemini for document understanding. DOCX text
and tables and XLSX/XLSM cell values/formulas are extracted locally. Office drawings,
embedded objects, headers/footers, and spreadsheet formatting are not fully extracted;
review originals. Legacy DOC/XLS, unsupported archives, files over 12 MiB, expanded
office archives over 32 MiB, and extracted text over 150,000 characters are explicitly
flagged for manual review, not silently truncated. The documentation tab's embedded
text is analyzed separately when substantial; scripts/styles are excluded.

Analysis is in Georgian and includes a summary, requirements/findings with
page/section references, and limitations. It is advisory, not a procurement decision.
AI references are model-generated and must be checked against the original.
Confidential documents are not retrieved. Portal notices mentioning confidential
material are flagged; public attachments may not constitute complete requirements.

## GitHub setup

Upload these files to your repository's default branch and enable Actions.
Scheduled workflows must exist on the default branch.

```text
.github/
  workflows/
    tender-monitor.yml
tests/
  test_monitor.py
.gitignore
monitor.py
tender_pipeline.py
requirements.txt
README.md
```

Keep the tests: the workflow runs them before scanning, without real AI calls or
emails. Do not upload `.venv/`, `__pycache__/`, local state or credentials.
The workflow installs dependencies automatically; no server hosting is needed.

### Repository secrets

Under **Settings > Secrets and variables > Actions > Secrets**, configure:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | API key from Google AI Studio |
| `EMAIL_FROM` | Sending Gmail address |
| `EMAIL_PASSWORD` | Gmail App Password, not the normal account password |
| `EMAIL_TO` | Recipient email address |

For Gmail App Passwords, enable Google Account 2-Step Verification and create an
App Password. Never commit secrets or paste API keys into chat. Revoke any exposed
key and configure its replacement here. Enter secret values without surrounding quotes.

### Repository variables

Under **Settings > Secrets and variables > Actions > Variables**, configure:

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_MODEL` | **Required** | Exact model ID available on your project's free tier, supporting PDF input and JSON structured output |
| `INITIAL_SCAN_MODE` | `all` | `all`: analyze currently active tenders; `baseline`: initially record their document hashes without analysis |
| `MAX_ANALYSES_PER_RUN` | `10` | Positive maximum generation attempts per run |
| `GEMINI_RPD_LIMIT` | Unknown | Configured daily generation-attempt ceiling; use your project's actual model limit |
| `GEMINI_RPM_LIMIT` | Unknown | Requests/minute setting; when set, generation calls are conservatively spaced at least 61 seconds apart |
| `GEMINI_TPM_LIMIT` | Unknown | Input tokens/minute setting; preflight rejects any single document above it and spaces calls |
| `GEMINI_TPD_LIMIT` | Unknown | Optional local daily **input-token budget**; not a verified provider total-token quota |

#### First production trial: this project's observed limits

The project's AI Studio screenshot showed the following limits for Gemini 3.8 Flash.
Verify them in your own project before using them; they are not a universal free-tier
allowance and Google may change them.

Create these **repository variables**, with values entered without quotes:

| Variable | First-trial value |
|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `GEMINI_RPM_LIMIT` | `5` |
| `GEMINI_TPM_LIMIT` | `250000` |
| `GEMINI_RPD_LIMIT` | `20` |
| `MAX_ANALYSES_PER_RUN` | `1` |
| `INITIAL_SCAN_MODE` | `all` |

Leave `GEMINI_TPD_LIMIT` unset: the observed 250,000-token limit is **per minute**,
not per day. After verifying the email, analysis and state persistence, increase
`MAX_ANALYSES_PER_RUN` to `10`. One request analyzes one document or substantial
documentation-tab text, not necessarily a whole tender.

Blank or zero quota settings mean **unknown/not enforced locally**, not unlimited.
Negative or invalid numeric settings fail configuration explicitly.
`baseline` still downloads public files to establish their hashes; unchanged baseline
files are not analyzed later. New/changed files are analyzed normally. Failed
baseline downloads cannot establish a version and are retried.

Choose a current model and limits in
[AI Studio](https://aistudio.google.com/rate-limit?timeRange=last-28-days).
No model name or free allowance is hardcoded because availability changes.
Use a project without paid billing enabled if you must avoid paid usage; code cannot
determine your billing tier or guarantee a monetary cap on a billing-enabled project.
Review [Gemini pricing/data-use terms](https://ai.google.dev/gemini-api/docs/pricing)
before submitting documents. Only public procurement content should be sent.

### Persistence permissions

The workflow requests `contents: write`, creates/updates `monitor-state`, and prevents
overlapping monitor jobs. Repository/organization rules must allow this branch update.
State is committed even if a later document or SMTP request fails.

Under **Settings > Actions > General > Workflow permissions**, allow **Read and write
permissions** if permitted by your organization. No personal access token is needed:
GitHub supplies the workflow token automatically. You do not need to create the
`monitor-state` branch, configure `STATE_PATH`, or add a schedule variable manually.

**The state branch has the same visibility as the repository.** It contains public
tender metadata, public document URLs/hashes, AI summaries, usage counters and delivery
markers, but no API keys, email credentials or downloaded files. Use a private
repository if you do not want these reports visible publicly. State history grows
over time; no automatic destructive retention policy is applied.

Do not use Actions cache as the only source of history: cache eviction would lose
deduplication. Do not manually delete state unless you intend to reset processing.
If a state push fails, fix branch permissions and recover runner progress before
rerunning, or duplicate processing/notifications can occur.

### Schedule and first run

The [workflow](.github/workflows/tender-monitor.yml) runs daily at **10:00 Tbilisi
time (06:00 UTC)**, using `0 6 * * *`. Run **Actions > IT Tender Monitor > Run workflow** manually first.
Check successful file downloads, analysis, email and the state-branch push.

GitHub scheduling is best-effort, not an exact 24-hour SLA. Public-repository schedules
can be disabled after 60 days without repository activity. Standard public-repository
Linux runners are free; private repositories have plan-specific allowances.

Daily processing is preferable to 48/72-hour batches: unused Gemini daily quota does
not accumulate. If incoming work consistently exceeds capacity, the backlog grows.
Oversized/unsupported documents need manual action; waiting does not make them smaller.

## What the daily email contains

- **New tenders and documentation updates:** tender number, portal link, buyer,
  category, status, announcement date, displayed estimated value and deadline when
  extracted. Displayed values may have conditions; verify the original tender.
- **Document results:** filenames and links, Georgian AI summaries, findings with
  source page/section references, and limitations. Findings cover technical
  requirements, quantities, eligibility, dates, delivery, payment, guarantees,
  warranty, penalties and risks where present. Results are per document, not a
  guaranteed consolidated legal assessment of the tender.
- **Failures and pending work:** the document name, sanitized error reason,
  pending count and a next-scheduled-scan retry notice. Repeated pending entries
  remain visible without repeating unchanged successful analyses.
- **Gemini usage:** daily generation attempts, configured-budget bars, reported
  input/output/total tokens, unresolved usage, 429 events and month-to-date totals.
- **No-change days:** a short no-new-tenders/documentation-updates message, with
  the usage information.

For example, if Google is overloaded, the report includes:

```text
Document: notice.pdf [pending]
https://tenders.procurement.gov.ge/public/...
Gemini HTTP 503: UNAVAILABLE | This model is currently experiencing high demand.
Pending documents: 1
Pending work will be retried on the next scheduled scan.
```

A Gemini failure does not discard completed results or suppress the normal report.
Successful summaries are not fabricated when the API fails.

### Email usage chart

Example with illustrative configured limits, **not Google's advertised quotas**:

```text
GEMINI USAGE - scanner only (not account-wide remaining quota)
Daily generation attempts: [#####-----] 5/10 (50%) - within configured limit
Daily input-token budget (preflight/reserved): [###-------] 30,000/100,000 (30%)
API-reported today: input 28,000, output 2,000, total 31,000
Unresolved/unreported generation usage today: 0
Rate/quota errors (429) today: 0
Month-to-date: 85 generation attempts, 450,000 reported total tokens
```

The email includes both HTML and plain-text versions. Its ASCII chart works without
external images or tracking services.

- Daily counters use **America/Los_Angeles**, resetting at midnight Pacific, including
  daylight-saving changes. Month-to-date totals are for that calendar month/model.
- Requests are local generation **attempts**, including failures, not authoritative
  provider-billed requests. `countTokens` preflight calls are separate and are not
  included in this count; they may have their own service limits.
- Input/output/total usage comes from Gemini's `usageMetadata`. Total tokens may
  include thinking/cached tokens, so input + output need not equal total.
- Input budget reservations come from `countTokens` and remain reserved on failure.
  Calls without usage metadata are explicitly counted as unresolved/unreported.
- There is **no live account-wide remaining-quota API integration**. Other applications
  sharing the project consume capacity this scanner cannot see. Check AI Studio.
- A 429 records a rate/quota event and stops further AI work for the run. It does not
  prove a daily token limit was exceeded; it may be a per-minute or another limit.
- Errors and unfinished files appear in the daily report and are retried next run.
  Auth/model errors and HTTP 5xx service errors also stop further AI work until the
  next run. Provider error status/messages are included with API-key redaction;
  raw response bodies and detailed error payloads are not logged.
- A Gemini analysis failure does not prevent the daily email: it includes tender
  details, document links, the failure reason, pending count and next-scan retry
  notice. Startup/configuration
  errors, runner termination, and SMTP outages cannot be guaranteed an email report;
  check Actions logs/notifications in those cases.

Completed analysis and notification delivery are tracked independently. Failed SMTP
delivery retries notification without discarding cached analysis. SMTP delivery and
Git commits are not a transaction: a crash after SMTP accepts a message but before
state is saved/pushed can cause a duplicate email. Exact-once delivery is not promised.

## Local development (PowerShell)

Python 3.12+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

$env:GEMINI_API_KEY = "<your-key>"
$env:GEMINI_MODEL = "<available-free-tier-model-id>"
$env:EMAIL_FROM = "<your-gmail>"
$env:EMAIL_PASSWORD = "<app-password>"
$env:EMAIL_TO = "<recipient>"
$env:STATE_PATH = "state.json"
.\.venv\Scripts\python.exe monitor.py
```

Unit/integration tests mock AI and SMTP, so they do not consume quota or send email.
Live public attachment retrieval should also be verified after portal changes.
Search failures are reported as incomplete discovery, not as a successful empty scan.
Invalid state is never silently replaced with an empty history.

### Manual production test

Use **Actions > IT Tender Monitor > Run workflow**. Set `MAX_ANALYSES_PER_RUN=1`
for the first trial. This runs the full scanner, uses repository secrets, sends
the daily email and persists state, even if Gemini analysis fails. Verify the email
and the `monitor-state` branch update; a successful workflow alone does not prove
AI analysis succeeded. No separate local test script or VS Code task is required.

Check the first run in this order:

1. All workflow steps complete, including the state push.
2. The recipient receives the email; check Spam if necessary.
3. The `monitor-state` branch contains `state.json`.
4. Document entries show completed analysis or an explicit pending/error reason.
5. A second manual run reuses unchanged completed analyses and retries pending files.

Manual runs use the same state and API quota as scheduled runs. They scan all
matching tenders, even when the analysis budget is one. Avoid repeated runs during
an outage. The schedule remains enabled during manual testing.

## Troubleshooting

| Symptom | Meaning / next step |
|---|---|
| HTTP 401 | Authentication rejected. Verify a current Gemini API key from the correct project; replace revoked/exposed keys. |
| HTTP 403 or 404 | Check provider error details, project/API restrictions, model ID and access. |
| HTTP 429 | A rate/quota limit was hit; inspect AI Studio. Unused daily allowance does not accumulate across days. |
| HTTP 503 with high-demand message | Google reports temporary model overload. Work remains pending; do not enable billing merely to troubleshoot this error. |
| Usage is zero with unresolved attempts | The request returned no usage metadata; zero reported tokens does not prove zero consumption. |
| No email | Check Actions logs, configured secrets, Gmail App Password, SMTP errors and Spam. |
| State push denied | Fix workflow permissions and branch rules before rerunning to avoid losing deduplication history. |

Live portal downloads have been verified for the sample tenders. Local Gemini tests
reached generation but returned a provider-confirmed high-demand 503; successful AI
analysis, real Gmail delivery and GitHub state pushes still require a successful
production trial.
