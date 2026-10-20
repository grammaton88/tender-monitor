# IT Tender Monitor (Georgia)

Automated monitor for **IT-related public tenders** on the official Georgian State Procurement Agency portal:

**https://tenders.procurement.gov.ge**

The script searches only for tenders with status **„გამოცხადებულია“** (Announced) and matching IT/CPV codes, then sends an email notification with the results.

---

## Features

- Filters tenders by status: **გამოცხადებულია** only
- Searches multiple IT-related CPV / base codes (computers, software, networks, telecom, IT services, etc.)
- Sends a clean Georgian-language email with all found tenders
- Runs automatically every day via **GitHub Actions**
- Can also be triggered manually

---

## How it works

1. GitHub Actions runs the Python script on a schedule (cron).
2. The script logs into the procurement portal (session + cookies).
3. It searches for each IT base code with status = announced.
4. Collects unique tenders.
5. Sends one email containing all results to the configured address.

---

## Setup

### 1. Clone / Fork this repository

### 2. Add GitHub Secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add the following secrets:

| Secret Name       | Description                              | Example                     |
|-------------------|------------------------------------------|-----------------------------|
| `EMAIL_TO`        | Recipient email                          | `kakabadzemisha@gmail.com`  |
| `EMAIL_FROM`      | Gmail address used to send               | `your.email@gmail.com`      |
| `EMAIL_PASSWORD`  | Gmail App Password (not normal password) | `abcd efgh ijkl mnop`       |

> **How to create Gmail App Password:**  
> Google Account → Security → 2-Step Verification → App passwords → Generate.

### 3. Enable GitHub Actions

Make sure Actions are enabled for the repository.

---

## Schedule

The workflow runs automatically according to the cron expression in:

`.github/workflows/tender-monitor.yml`

Current default (example):

```yaml
- cron: '0 6 * * *'   # 10:00 Tbilisi time (06:00 UTC)
```

**Important:** GitHub Actions cron uses **UTC** only.  
Tbilisi is UTC+4, so subtract 4 hours when setting the time.

| Desired time (Tbilisi) | Cron (UTC)     |
|------------------------|----------------|
| 09:00                  | `0 5 * * *`    |
| 10:00                  | `0 6 * * *`    |
| 12:00                  | `0 8 * * *`    |
| 18:00                  | `0 14 * * *`   |
| 21:00                  | `0 17 * * *`   |

You can also trigger the workflow manually:

**Actions** → **IT Tender Monitor** → **Run workflow**

---

## Project Structure

```
tender-monitor/
├── .github/
│   └── workflows/
│       └── tender-monitor.yml   # GitHub Actions workflow
├── monitor.py                   # Main script
├── requirements.txt             # Python dependencies
└── README.md
```

---

## Requirements

- Python 3.12+
- `requests`
- `beautifulsoup4`

(Installed automatically by the GitHub Actions workflow)

---

## Local Testing

```bash
pip install -r requirements.txt

# Set environment variables
export EMAIL_TO="kakabadzemisha@gmail.com"
export EMAIL_FROM="your.email@gmail.com"
export EMAIL_PASSWORD="your_app_password"

python monitor.py
```

---

## Notes

- The script only looks for tenders with status **გამოცხადებულია**.
- IT codes are hardcoded in `monitor.py` (CPV categories related to computers, software, networks, telecom, IT services, etc.).
- GitHub scheduled workflows can sometimes be delayed by a few minutes.
- The procurement website requires a valid session (cookies). The script handles this automatically.
- No external database is used - every run sends the current list of active IT tenders.

## License

MIT
```
