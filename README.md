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

[myaccoun](h[myaccou](https://myaccou))- Google Accounts](https://aistudio.google.com/rate-limit?timeRange=last-28-days).))velopers](https://ai.google.dev/gemini-api/docs/pricing)))m/apppasswords).)[Sign in - Google Accounts](https://aistudio.google.com/rate-limit?timeRange=last-28-days).)[404 &nbsp;|&nbsp; Page Not Found &nbsp;|&nbsp; Google AI for Developers](https://ai.google.dev/gemini-api/docs/pricing))
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

Keep `tests/test_monitor.py`: the workflow runs these offline tests before scanning.
They do not consume Gemini quota or send real email. No separate live-test script,
VS Code task, paid server or external database is required.
Do not upload virtual environments, Python caches, `.env`, credentials, or local
state files. GitHub creates the persistent state branch automatically.

### Repository secrets

Under **Settings > Secrets and variables > Actions > Secrets**, configure:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Gemini API key from Google AI Studio for the intended project; rotate any key exposed in chat or logs |
| `EMAIL_FROM` | Sending Gmail address |
| `EMAIL_PASSWORD` | Gmail App Password, not the normal account password |
| `EMAIL_TO` | Recipient email address |

For Gmail App Passwords, enable Google Account 2-Step Verification and create an
App Password. Never commit secrets.
Create an App Password at [Google Account App Passwords](https://myaccount.google.com/apppasswords).
Secrets go in **Repository secrets**, not repository variables or source code.

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

For the initial production trial, use these repository variable values:

| Name | First-test value |
|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `GEMINI_RPM_LIMIT` | `5` |
| `GEMINI_TPM_LIMIT` | `250000` |
| `GEMINI_RPD_LIMIT` | `20` |
| `MAX_ANALYSES_PER_RUN` | `1` |
| `INITIAL_SCAN_MODE` | `all` |

These model quotas were displayed for the Tender Monitor project in AI Studio on
October 22, 2026; they are not guaranteed allowances for other projects or future
dates. Verify them against the same project as your API key. Enter values without
quotes. Leave `GEMINI_TPD_LIMIT` unset: the displayed 250,000-token limit is per
minute, not per day. After verifying email and persistence, increase
`MAX_ANALYSES_PER_RUN` to `10` for normal operation.

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

Under **Settings > Actions > General**, enable Actions and, where permitted, select
**Workflow permissions > Read and write permissions**, then save. Organization
policies or branch rules can still prevent writes and must allow `monitor-state`
updates. Do not manually add a personal access token or a `GITHUB_TOKEN` secret:
GitHub supplies the workflow token automatically.

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

The [workflow](.github/workflows/tender-monitor.yml) runs daily at **10:17 Tbilisi
time (06:17 UTC)**. Run **Actions > IT Tender Monitor > Run workflow** manually first.
Check successful file downloads, analysis, email and the state-branch push.

First-run checklist:

1. Add all four repository secrets and the first-test variables above.
2. Run the workflow manually on the default branch.
3. Verify the test, scan, email and state-persistence steps in the Actions log.
4. Confirm the recipient receives a daily report with analysis or an explicit error.
5. Confirm `monitor-state` contains `state.json`; do not delete this history.
6. Run again and verify unchanged completed analyses are reused. Pending files are
   retried; other unprocessed files can consume the next run's analysis allowance.
7. Increase `MAX_ANALYSES_PER_RUN` to `10` once delivery and persistence work.

The first test scans all matching tenders, not only tender 710418. The value `1`
limits generation attempts, not tender discovery or downloads. A green workflow
does not prove Gemini analysis succeeded: handled service failures can still
produce a successful email listing pending documents.

GitHub scheduling is best-effort, not an exact 24-hour SLA. Public-repository schedules
can be disabled after 60 days without repository activity. Standard public-repository
Linux runners are free; private repositories have plan-specific allowances.

Daily processing is preferable to 48/72-hour batches: unused Gemini daily quota does
not accumulate. If incoming work consistently exceeds capacity, the backlog grows.
Oversized/unsupported documents need manual action; waiting does not make them smaller.

## What the recipient receives

- **New tenders and documentation updates:** tender number, buyer, category, status,
  announcement date, displayed value, submission deadline and portal link, where
  extracted from the portal. Conditional values and confidential-material notices
  must be checked against the original.
- **Document results:** filename, public download link, Georgian summary, findings,
  source page/section references and limitations. Findings cover requested products,
  quantities, technical specifications, eligibility, deadlines, delivery, payment,
  guarantees, warranty, penalties and disqualification risks where present.
  Results are per document, not a guaranteed consolidated tender assessment.
- **Failures and pending work:** download/analysis error, affected file, pending
  document count and next-scan retry notice. A failed document does not discard
  completed analyses. Unchanged completed tenders are not repeated in full.
- **Usage:** generation attempts, reported tokens, configured-limit bars, unresolved
  usage, rate/quota errors and month-to-date totals.
- **No changes:** a short daily report and usage information are still sent.

The email has HTML and plain-text alternatives. Its headings are currently English;
AI summaries are requested in Georgian. Documents are linked, not attached.
If Gemini returns `503 UNAVAILABLE` because of high demand, the email includes that
reason and marks the affected document pending instead of claiming analysis succeeded.

## Troubleshooting

| Symptom | Action |
|---|---|
| Gemini HTTP 401/403 | Verify the API key, selected project, API access and restrictions. Rotate exposed keys. |
| Gemini HTTP 404 | Verify the exact model ID and its availability to your project. |
| Gemini HTTP 429 | Check AI Studio limits and shared-project usage. Work remains pending for a later run. |
| Gemini HTTP 503 / high demand | Provider generation is unavailable; work remains pending. Do not assume a quota problem or enable billing solely for this error. |
| No email | Check all email secrets, Gmail App Password, spam folder and Actions logs. |
| State push fails | Check workflow write permissions and rules on `monitor-state`. Avoid rerunning blindly because unsaved history can cause repeats. |
| Completed workflow but no analysis | Read document statuses in the email; handled AI failures do not necessarily fail the job. |

Production readiness requires a real successful analysis, email delivery and state
push. Offline tests do not establish these. Local testing of tender 710418 verified
PDF retrieval and preflight access, but generation returned high-demand HTTP 503;
a complete live analysis was not verified at that point.

## Email usage chart

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
  notice. The interactive smoke test intentionally sends no email. Startup/configuration
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
