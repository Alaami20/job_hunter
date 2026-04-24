# 🚀 Alaa's AI Job Hunter — Complete Setup Guide

## What this does
- Searches LinkedIn, Indeed & Glassdoor for jobs matching your CV
- Claude AI scores every job 0–100 against your skills
- Results saved automatically to Google Sheets (sorted best match first)
- Web dashboard at http://localhost:5000 to track your applications

---

## STEP 1 — Open Terminal on your Mac
Press **Cmd + Space**, type **Terminal**, press Enter.

---

## STEP 2 — Go to the job_hunter folder
```bash
cd ~/Desktop/job_hunter
```

---

## STEP 3 — Install all packages
```bash
pip install -r requirements.txt
```
Wait for it to finish (1–2 minutes).

---

## STEP 4 — Get your Anthropic API Key (free)

1. Go to: https://console.anthropic.com
2. Sign up or log in
3. Click **API Keys** in the left menu
4. Click **Create Key** → copy it
5. Open `job_scraper.py` in any text editor
6. Find this line (line 24):
   ```python
   ANTHROPIC_API_KEY = "sk-ant-YOUR_KEY_HERE"
   ```
7. Replace `sk-ant-YOUR_KEY_HERE` with your actual key

---

## STEP 5 — Set up Google Sheets (5 minutes, one time)

### 5a. Create a Google Cloud Project
1. Go to: https://console.cloud.google.com
2. Click the project dropdown at top → **New Project**
3. Name it: `job-hunter` → click **Create**

### 5b. Enable two APIs
1. Go to: **APIs & Services → Library**
2. Search **"Google Sheets API"** → click it → click **Enable**
3. Search **"Google Drive API"** → click it → click **Enable**

### 5c. Create a Service Account
1. Go to: **APIs & Services → Credentials**
2. Click **+ Create Credentials → Service Account**
3. Name: `job-hunter-bot` → click **Done**
4. Click on `job-hunter-bot` in the list
5. Go to the **Keys** tab
6. Click **Add Key → Create new key → JSON → Create**
7. A file downloads automatically — **rename it to `google_creds.json`**
8. **Move `google_creds.json` into your `job_hunter` folder** (same folder as this file)

---

## STEP 6 — Run the scraper!
```bash
python job_scraper.py
```

This will:
1. Scrape LinkedIn, Indeed & Glassdoor (takes 3–5 min)
2. Score every job with Claude AI
3. Save everything to a new Google Sheet called **"Alaa Job Hunt 2026"**
4. Print a summary in your terminal

---

## STEP 7 — Open the Web Dashboard
In a new terminal tab:
```bash
cd ~/Desktop/job_hunter
python web_app.py
```
Then open your browser and go to: **http://localhost:5000**

You'll see all your jobs as cards — filter by priority, click Apply, update status.

---

## Your Google Sheet columns

| Column | Meaning |
|---|---|
| Date Found | When job was scraped |
| Job Title | Role name |
| Company | Company |
| Location | City/Remote |
| Site | linkedin / indeed / glassdoor |
| **Match Score** | 0–100 scored by Claude AI |
| Match Reason | Why it's a good/bad match |
| Key Missing Skills | What to learn |
| **Apply Priority** | HIGH / MEDIUM / LOW |
| Job URL | Direct link to apply |
| Description | First 300 chars |
| **Status** | Update this yourself |

---

## Run again anytime
```bash
python job_scraper.py
```
New jobs are added, duplicates are skipped automatically.

---

## Customize your searches
Open `job_scraper.py` and edit the `SEARCH_CONFIG` section:
```python
"search_terms": [
    "ML Engineer student",
    "Data Science intern",
    # add your own here!
],
"hours_old": 72,   # change to 168 for 1 week of results
```

---

## Common errors and fixes

**"No module named jobspy"**
```bash
pip install python-jobspy
```

**"google_creds.json not found"**
Make sure the file is inside the `job_hunter` folder (same folder as job_scraper.py)

**"Spreadsheet not found"**
Run `job_scraper.py` first — it creates the sheet automatically.

**"Invalid API key"**
Double-check you pasted the full key starting with `sk-ant-` in job_scraper.py

---

Built by Alaa Miari · Growwithyouu Startup 🚀
