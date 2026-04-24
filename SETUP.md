# 🚀 Alaa's Job Hunter — Complete Setup Guide

## What you have in this folder

```
job_hunter/
├── job_scraper.py     ← Phase 1: scans jobs + scores with AI + saves to Google Sheets
├── web_app.py         ← Phase 2: browser dashboard to view & manage jobs
├── start.sh           ← one-click launcher (Mac/Linux)
├── requirements.txt   ← Python packages list
├── SETUP.md           ← this file
└── google_creds.json  ← YOU create this (Step 3 below)
```

---

## Step 1 — Open Terminal in this folder

**Mac:**
1. Open this folder in Finder
2. Right-click inside the folder → "New Terminal at Folder"
   (or drag the folder onto Terminal in your Dock)

---

## Step 2 — Get your Anthropic API Key (free)

1. Go to → https://console.anthropic.com
2. Sign up / log in
3. Click **API Keys** in the left menu → **Create Key**
4. Copy the key (starts with `sk-ant-...`)
5. Open `job_scraper.py` in TextEdit or VSCode
6. Find line 15:
   ```python
   ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_API_KEY_HERE"
   ```
7. Replace `YOUR_ANTHROPIC_API_KEY_HERE` with your key

---

## Step 3 — Set up Google Sheets (one time, ~5 minutes)

### 3a — Create Google Cloud project
1. Go to → https://console.cloud.google.com
2. Click the project dropdown at the top → **New Project**
3. Name: `job-hunter` → click **Create**

### 3b — Enable APIs
1. In the left menu → **APIs & Services** → **Library**
2. Search `Google Sheets API` → click it → click **Enable**
3. Go back to Library → search `Google Drive API` → click **Enable**

### 3c — Create Service Account
1. Left menu → **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **Service Account**
3. Name: `job-hunter-bot` → click **Create and Continue** → **Done**

### 3d — Download the JSON key
1. Click on the `job-hunter-bot` service account you just created
2. Click the **Keys** tab
3. Click **Add Key** → **Create new key** → **JSON** → **Create**
4. A file downloads automatically
5. **Rename it to `google_creds.json`**
6. **Move it into this `job_hunter` folder**

---

## Step 4 — Run it!

### Option A: One-click (easiest)
In Terminal, in this folder:
```bash
bash start.sh
```
Follow the prompts.

### Option B: Manual

**Phase 1 — Scan & fill Google Sheet:**
```bash
pip install -r requirements.txt
python3 job_scraper.py
```

**Phase 2 — Open web dashboard:**
```bash
python3 web_app.py
```
Then open your browser at: **http://localhost:5000**

---

## What your Google Sheet looks like

| Column | Meaning |
|---|---|
| Date Found | When job was found |
| Job Title | Role name |
| Company | Company |
| Location | City / Remote |
| Site | linkedin / indeed / glassdoor |
| **Match Score** | 0–100 (Claude AI score) |
| Match Reason | Why it's a good or bad match for YOU |
| Key Missing Skills | What you'd need to learn |
| **Apply Priority** | HIGH / MEDIUM / LOW |
| Job URL | Click to open the job |
| Description | First 300 characters |
| **Status** | You fill this: Applied / Interviewing / Offer / Rejected |

---

## Customize your search

Open `job_scraper.py` and edit `SEARCH_CONFIG`:

```python
"search_terms": [
    "ML Engineer student",
    "Data Science intern",
    # Add anything here ↓
    "NLP engineer Israel",
    "AI startup Israel",
],
"hours_old": 72,    # Change to 168 for 1 week of jobs
```

---

## Got an error?

Paste the error message into Claude and it will fix it immediately.

---

**Built by Alaa Miari · Growwithyouu 🚀**
