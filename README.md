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
```

---

You can change the time in .github/workflows/tender-monitor.yml.
Note: GitHub Actions scheduled jobs run in UTC and may have a delay of several minutes.

Manual Run

Go to the Actions tab in your repository.
Select IT Tender Monitor.
Click Run workflow → Run workflow.

IT CPV Codes monitored
The script currently monitors these categories:

30200000 – Computer equipment & accessories
32400000 – Networks
32500000 – Telecommunication equipment
48100000 – 48900000 – Software packages
48800000 – Information systems & servers
50300000 – Computer equipment repair
51600000 – Computer installation
64200000 – Telecommunication services
72100000 – 72900000 – IT consulting & related services

You can add or remove codes in monitor.py inside the IT_BASECODES dictionary.

pip install -r requirements.txt

# Set environment variables
export EMAIL_TO="kakabadzemisha@gmail.com"
export EMAIL_FROM="yourname@gmail.com"
export EMAIL_PASSWORD="your_app_password"

python monitor.py

---

Notes

The script only returns tenders that are currently in status გამოცხადებულია.
Email is sent only when at least one matching tender is found.
No external database is used (simple and free).
Works completely on the free tier of GitHub Actions.

---
