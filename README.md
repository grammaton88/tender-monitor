# IT Tender Monitor (Georgia)

Automated monitor for **IT-related public tenders** on the official Georgian State Procurement Agency website:  
[https://tenders.procurement.gov.ge](https://tenders.procurement.gov.ge)

The script searches only for tenders with status **„გამოცხადებულია“** (Announced) that belong to IT / ICT CPV categories and sends an email notification with the results.

---

## Features

- Filters only **active** tenders (`გამოცხადებულია`)
- Searches multiple IT-related CPV codes (computers, software, networks, telecom, IT services, etc.)
- Sends a summary email with tender details and direct links
- Runs automatically every day via **GitHub Actions**
- Can also be triggered manually

---

## How it works

1. GitHub Actions runs the script on a schedule (or manually).
2. The script logs into the procurement portal (with session) and searches for each IT CPV code with status `გამოცხადებულია`.
3. It collects unique tenders and sends one email containing all results.

---

## Setup

### 1. Repository Secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these three secrets:

| Secret Name       | Description                          | Example                          |
|-------------------|--------------------------------------|----------------------------------|
| `EMAIL_TO`        | Recipient email                      | `kakabadzemisha@gmail.com`       |
| `EMAIL_FROM`      | Gmail address used for sending       | `yourname@gmail.com`             |
| `EMAIL_PASSWORD`  | Gmail App Password (not normal password) | `abcd efgh ijkl mnop`         |

> **How to create a Gmail App Password:**  
> Google Account → Security → 2-Step Verification → App passwords → Generate.

### 2. Files in the repository

tender-monitor/
├── .github/
│   └── workflows/
│       └── tender-monitor.yml    # GitHub Actions workflow
├── monitor.py                    # Main script
├── requirements.txt              # Python dependencies
└── README.md


---

## Schedule

The workflow is configured to run **every day at 10:00 Tbilisi time** (06:00 UTC):

```yaml
- cron: '0 6 * * *'
