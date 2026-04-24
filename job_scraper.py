"""
╔══════════════════════════════════════════════════════╗
║   🚀 Alaa's AI Job Hunter — Growwithyouu Startup     ║
║   Step 1: Scrape → Score → Save to Google Sheets     ║
╚══════════════════════════════════════════════════════╝

SETUP (one time only):
    1. pip install -r requirements.txt
    2. Add your ANTHROPIC_API_KEY below
    3. Add your google_creds.json (see SETUP_GUIDE.md)

RUN:
    python job_scraper.py
"""

import anthropic
import gspread
import json
import time
from datetime import datetime
from google.oauth2.service_account import Credentials
from jobspy import scrape_jobs

# ══════════════════════════════════════════════
#  ✏️  EDIT THESE TWO LINES BEFORE RUNNING
# ══════════════════════════════════════════════

ANTHROPIC_API_KEY = "sk-ant-YOUR_KEY_HERE"   # https://console.anthropic.com
GOOGLE_CREDS_FILE = "google_creds.json"       # downloaded from Google Cloud

# ══════════════════════════════════════════════
#  SEARCH CONFIG
# ══════════════════════════════════════════════

SPREADSHEET_NAME = "Alaa Job Hunt 2026"

SEARCH_CONFIG = {
    "search_terms": [
        "ML Engineer student",
        "Data Science intern",
        "AI Engineer student",
        "Machine Learning intern",
        "Generative AI intern",
        "Data Scientist student",
        "Python developer student",
        "MLOps intern",
    ],
    "location": "Israel",
    "results_wanted": 15,
    "hours_old": 72,
    "sites": ["linkedin", "indeed", "glassdoor"],
}

CV_PROFILE = """
Name: Alaa Miari
Title: AI Systems Engineer, Co-founder of Growwithyouu startup
Education: 3rd-year B.Sc. Data Science & Computer Science, University of Haifa (GPA 85)
Expected graduation: 2027

Skills:
- Programming: Python, Java, SQL, MATLAB, C, JavaScript
- ML/AI: TensorFlow, Keras, PyTorch, Scikit-Learn, Transformers, RAG
- Generative AI: Prompt Engineering, LLM Fine-Tuning, Embeddings, RAG
- Cloud/MLOps: AWS (EC2, S3, Lambda, CodeBuild, CodePipeline), CI/CD, CloudWatch, GitHub Actions
- Data: Pandas, NumPy, Data Cleaning, Feature Engineering
- Tools: Git, Linux, Jupyter, VSCode

Experience:
- Co-founder & AI Engineer at Growwithyouu — built Crypto-Intel (live AI SaaS platform)
- Teaching Assistant, AI course — University of Haifa (2026)
- Mentorship under CTO — Daisy Company (2025-present)
- Volunteer Program Presenter — Data Science info sessions (2024-present)

Projects:
- Crypto-Intel: live AI crypto intelligence SaaS (crypto-intel.online)
- Cold-Start Recommendation Research (short paper)
- Global Map in Software Engineering (system design)

Certifications: AWS Cloud Technical Essentials, SQL for Data Science (UC Davis),
IBM Deep Learning, IBM Generative AI LLM, DevOps & AI on AWS, Google MLOps

Languages: Arabic (native), Hebrew (fluent), English (advanced)
Location: Haifa, Israel
"""

SHEET_HEADERS = [
    "Date Found", "Job Title", "Company", "Location", "Site",
    "Match Score", "Match Reason", "Key Missing Skills",
    "Apply Priority", "Job URL", "Description Snippet", "Status"
]


def connect_sheets():
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds  = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    try:
        sheet = client.open(SPREADSHEET_NAME).sheet1
        print(f"Connected to existing sheet: '{SPREADSHEET_NAME}'")
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SPREADSHEET_NAME)
        sheet = spreadsheet.sheet1
        sheet.append_row(SHEET_HEADERS)
        sheet.format("A1:L1", {
            "backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.35},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
        })
        spreadsheet.share(None, perm_type="anyone", role="writer")
        print(f"Created new sheet: '{SPREADSHEET_NAME}'")
        print(f"Open: https://docs.google.com/spreadsheets/d/{spreadsheet.id}")
    return sheet


def scrape_all_jobs():
    all_jobs  = []
    seen_urls = set()
    for term in SEARCH_CONFIG["search_terms"]:
        print(f"  Searching: '{term}'...")
        try:
            jobs = scrape_jobs(
                site_name=SEARCH_CONFIG["sites"],
                search_term=term,
                location=SEARCH_CONFIG["location"],
                results_wanted=SEARCH_CONFIG["results_wanted"],
                hours_old=SEARCH_CONFIG["hours_old"],
                country_indeed="Israel",
                linkedin_fetch_description=True,
            )
            new = 0
            for _, job in jobs.iterrows():
                url = str(job.get("job_url", ""))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_jobs.append(job)
                    new += 1
            print(f"    -> {new} new jobs")
            time.sleep(2)
        except Exception as e:
            print(f"    Error: {e}")
    print(f"\nTotal unique jobs: {len(all_jobs)}")
    return all_jobs


def score_job(job, claude_client):
    title    = str(job.get("title",       "Unknown"))
    company  = str(job.get("company",     "Unknown"))
    location = str(job.get("location",    "Unknown"))
    desc     = str(job.get("description", "No description"))[:3000]

    prompt = f"""You are a career advisor. Score how well this job matches the candidate.

CANDIDATE:
{CV_PROFILE}

JOB:
Title: {title}
Company: {company}
Location: {location}
Description: {desc}

Reply ONLY with JSON, no extra text:
{{
  "score": <integer 0-100>,
  "match_reason": "<2 sentences>",
  "missing_skills": "<skills candidate lacks, or None>",
  "priority": "<HIGH | MEDIUM | LOW>"
}}"""

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        print(f"  Scoring error: {e}")
        return {"score": 0, "match_reason": "Could not score", "missing_skills": "N/A", "priority": "LOW"}


def run():
    print("\n" + "="*50)
    print("  Alaa's AI Job Hunter - Growwithyouu")
    print("="*50)

    print("\nConnecting to Google Sheets...")
    sheet = connect_sheets()

    print("\nScraping LinkedIn, Indeed, Glassdoor...")
    jobs = scrape_all_jobs()
    if not jobs:
        print("No jobs found. Try increasing hours_old.")
        return

    print(f"\nScoring {len(jobs)} jobs with Claude AI...")
    claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    rows   = []

    for i, job in enumerate(jobs, 1):
        title   = str(job.get("title",   "Unknown"))
        company = str(job.get("company", "Unknown"))
        print(f"  [{i}/{len(jobs)}] {title} @ {company}")
        result = score_job(job, claude)
        desc   = str(job.get("description", ""))[:300].replace("\n", " ")
        rows.append([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            title, company,
            str(job.get("location", "")),
            str(job.get("site",     "")),
            result["score"],
            result["match_reason"],
            result["missing_skills"],
            result["priority"],
            str(job.get("job_url", "")),
            desc,
            "Not Applied",
        ])
        time.sleep(0.5)

    rows.sort(key=lambda r: r[5], reverse=True)

    print(f"\nSaving {len(rows)} jobs to Google Sheets...")
    sheet.append_rows(rows, value_input_option="USER_ENTERED")

    high   = sum(1 for r in rows if r[8] == "HIGH")
    medium = sum(1 for r in rows if r[8] == "MEDIUM")
    low    = sum(1 for r in rows if r[8] == "LOW")

    print("\n" + "="*50)
    print("  DONE!")
    print(f"  HIGH priority   : {high}")
    print(f"  MEDIUM priority : {medium}")
    print(f"  LOW priority    : {low}")
    print(f"\n  Go to Google Sheets and find: '{SPREADSHEET_NAME}'")
    print("="*50 + "\n")

if __name__ == "__main__":
    run()
