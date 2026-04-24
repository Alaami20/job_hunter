"""
Alaa's AI Job Hunter — Student & Junior Edition
Run:  python3 app.py
Open: http://localhost:8080

NEW in this version:
  • Student / Junior / Intern jobs ONLY — senior roles auto-scored 0
  • Auto-Apply engine: HIGH-match jobs are applied to automatically
    (cover letter generated + email sent if recruiter address is found)
  • CV attached to every application email as plain-text
  • Auto-apply toggle in Settings
  • "Auto-Applied" status + live counter in sidebar
"""
import os, json, sqlite3, smtplib, threading, time, re, tempfile
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app    = Flask(__name__)
HERE   = os.path.dirname(os.path.abspath(__file__))
DB     = os.path.join(HERE, "jobs.db")
CFG    = os.path.join(HERE, "config.json")

SCAN = {"running": False, "progress": "", "done": 0, "total": 0,
        "log": [], "phase": "idle", "auto_applied": 0}

# ─── config ──────────────────────────────────────────────────────────────────
def read_cfg():
    try:
        with open(CFG) as f: return json.load(f)
    except: return {}

def write_cfg(data):
    c = read_cfg(); c.update(data)
    with open(CFG, "w") as f: json.dump(c, f, indent=2)

# ─── database ─────────────────────────────────────────────────────────────────
def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_found TEXT, title TEXT, company TEXT, location TEXT, site TEXT,
            score INTEGER DEFAULT 0, match_reason TEXT, missing_skills TEXT,
            priority TEXT DEFAULT 'LOW', job_url TEXT UNIQUE, description TEXT,
            status TEXT DEFAULT 'Not Applied', cover_letter TEXT, applied_at TEXT,
            recruiter_email TEXT);
        CREATE TABLE IF NOT EXISTS cv(
            id INTEGER PRIMARY KEY,
            raw TEXT, filename TEXT, saved_at TEXT, analysis TEXT);
    """)
    # Add recruiter_email column if upgrading from older DB
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN recruiter_email TEXT")
        c.commit()
    except: pass
    c.commit(); c.close()

def get_db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

# ─── cv parsing ───────────────────────────────────────────────────────────────
def parse_file(path, name):
    ext = name.lower().rsplit(".", 1)[-1]
    try:
        if ext == "pdf":
            try:
                import pdfminer.high_level
                return pdfminer.high_level.extract_text(path)
            except:
                import PyPDF2
                with open(path, "rb") as f:
                    return "\n".join(p.extract_text() or "" for p in PyPDF2.PdfReader(f).pages)
        elif ext == "docx":
            from docx import Document
            return "\n".join(p.text for p in Document(path).paragraphs)
        else:
            with open(path, encoding="utf-8", errors="ignore") as f: return f.read()
    except Exception as e:
        return f"Error parsing file: {e}"

# ─── openai helpers ───────────────────────────────────────────────────────────
def ai_analyze_cv(text, key):
    prompt = f"""Analyze this CV carefully. Return ONLY valid JSON with these exact keys:
{{
  "name": "full name",
  "title": "specific job title based on their strongest skill e.g. AI Systems Engineer | ML Student",
  "education": "degree, university, graduation year",
  "gpa": "GPA value only or empty string",
  "skills": ["list every technical skill mentioned: programming languages, frameworks, tools, platforms, ML models, cloud services"],
  "experience": ["EVERY role mentioned anywhere in the CV including: jobs, internships, startups founded, TA roles, mentorships, volunteer — format: Role @ Company (year)"],
  "languages": ["spoken languages"],
  "certifications": ["every certification listed"],
  "job_types": ["specific job title intern Israel", "specific job title intern Israel", ...],
  "summary": "2-sentence summary highlighting their strongest skills and startup experience"
}}

CRITICAL RULES for job_types:
- Generate exactly 12 SPECIFIC job title search terms based on their ACTUAL skills in the CV
- Format each as: "[Specific Role] intern Israel" or "[Specific Role] student Israel" or "[Specific Role] junior Israel"
- Examples of GOOD terms: "Machine Learning Engineer intern Israel", "NLP Engineer intern Israel", "Deep Learning intern Israel", "LLM Engineer student Israel", "MLOps Engineer intern Israel", "AWS Cloud intern Israel", "AI Research intern Israel", "Computer Vision intern Israel", "Data Science intern Israel", "Python Backend intern Israel", "Recommendation Systems intern Israel", "Junior AI Developer Israel"
- BAD terms: "intern", "student", "junior", "entry level" alone without a role title
- Base the terms on what skills/technologies actually appear in their CV
- ALWAYS include "student" or "intern" or "junior" in each term

CRITICAL RULES for experience:
- Read the ENTIRE CV including summary/objective sections
- If candidate mentions founding or co-founding a startup ANYWHERE → add "Co-Founder & AI Engineer @ [startup name] (year)"
- Include Teaching Assistant, mentorship, volunteer roles

CV TEXT:
{text[:4000]}"""
    try:
        r = OpenAI(api_key=key).chat.completions.create(
            model="gpt-4o-mini", max_tokens=900,
            messages=[{"role":"user","content":prompt}])
        raw = re.sub(r"```json|```", "", r.choices[0].message.content).strip()
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e), "name":"", "title":"", "education":"", "gpa":"",
                "skills":[], "experience":[], "languages":[], "certifications":[],
                "job_types":[], "summary":""}

def ai_score_job(title, company, loc, desc, cv_text, key):
    prompt = f"""Score this job for a student/junior candidate. Reply ONLY with JSON:
{{"score":<0-100>,"match_reason":"<2 sentences>","missing_skills":"<or None>","priority":"<HIGH|MEDIUM|LOW>"}}

STRICT STUDENT/JUNIOR RULES — apply these FIRST before anything else:
1. If the job title or description says "Senior", "Lead", "Principal", "Staff", "Manager", "Director", "Head of", "VP" → set score=0, priority=LOW immediately.
2. If job explicitly requires 3+ years of experience AND is not labeled intern/student/junior → set score=0.
3. ONLY score HIGH if: job is labeled intern, student, junior, entry-level, or graduate — OR description says "students welcome" / "no experience required" / "0-2 years".
4. If location is outside Israel (not Tel Aviv, Haifa, Jerusalem, Herzliya, Raanana, Petah Tikva, Beer Sheva, Netanya, Rehovot, remote) → score=0.

CANDIDATE PROFILE (3rd-year BSc Data Science & CS, University of Haifa, GPA 85):
- Co-founder of Growwithyouu startup, built Crypto-Intel (live AI SaaS) — counts as real experience
- Core skills: Python, Machine Learning, Deep Learning, TensorFlow, PyTorch, RAG, LLMs, Generative AI, AWS (EC2/S3/Lambda), MLOps, CI/CD, SQL, NLP, FastAPI, Git, Docker basics
- Teaching Assistant for AI course at University of Haifa (2026)
- Mentorship under CTO at Daisy Company
- Certifications: AWS Cloud, IBM Deep Learning, IBM Generative AI, Google MLOps

CV:
{cv_text[:2500]}

JOB: {title} at {company}, {loc}
{desc[:2000]}"""
    try:
        r = OpenAI(api_key=key).chat.completions.create(
            model="gpt-4o-mini", max_tokens=300,
            messages=[{"role":"user","content":prompt}])
        raw = re.sub(r"```json|```", "", r.choices[0].message.content).strip()
        return json.loads(raw)
    except Exception as e:
        return {"score":0,"match_reason":f"Error: {e}","missing_skills":"N/A","priority":"LOW"}

def ai_cover_letter(title, company, desc, cv_text, email, key):
    prompt = f"""Write a short professional cover letter for a student/intern application (3 paragraphs, max 200 words).
Start with "Dear Hiring Manager," — use real skills from the CV.
Emphasize: student status at University of Haifa, startup co-founder experience (Growwithyouu / Crypto-Intel), eagerness to learn.
End with the sender's email: {email}

CV: {cv_text[:2500]}
JOB: {title} at {company}
{desc[:1000]}

Write ONLY the letter body, nothing else."""
    try:
        r = OpenAI(api_key=key).chat.completions.create(
            model="gpt-4o-mini", max_tokens=450,
            messages=[{"role":"user","content":prompt}])
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Error generating letter: {e}"

# ─── email extraction ─────────────────────────────────────────────────────────
def extract_recruiter_email(text):
    """Try to find a recruiter/HR email in the job description."""
    if not text:
        return None
    # standard email regex
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    # Filter out generic/noreply addresses
    skip = {"noreply", "no-reply", "donotreply", "jobs@", "careers@", "apply@",
            "notifications@", "info@", "support@", "hello@"}
    for em in emails:
        if not any(s in em.lower() for s in skip):
            return em
    # If only generic ones exist, return the first one anyway
    return emails[0] if emails else None

# ─── gmail ────────────────────────────────────────────────────────────────────
def send_gmail(to, subject, body, from_addr, app_pw, cv_text=None, cv_filename=None):
    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = to
        msg.attach(MIMEText(body, "plain"))

        # Attach CV as text file if provided
        if cv_text and cv_filename:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(cv_text.encode("utf-8"))
            encoders.encode_base64(part)
            safe_name = re.sub(r"[^\w\.\-]", "_", cv_filename)
            if not safe_name.endswith(".txt"):
                safe_name = safe_name.rsplit(".", 1)[0] + ".txt"
            part.add_header("Content-Disposition", f'attachment; filename="{safe_name}"')
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(from_addr, app_pw)
            s.sendmail(from_addr, to, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)

# ─── scan agent ───────────────────────────────────────────────────────────────
def add_log(msg, level="info"):
    entry = {"t": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level}
    SCAN["log"].append(entry)
    SCAN["progress"] = msg
    print(f"[{entry['t']}] {msg}")

ISRAEL_KEYWORDS = [
    "israel", "tel aviv", "haifa", "jerusalem", "herzliya", "raanana",
    "petah tikva", "beer sheva", "netanya", "rehovot", "rishon", "remote"
]

SENIOR_KEYWORDS = [
    "senior", "lead ", "principal", "staff engineer", "manager", "director",
    "head of", "vp ", "vice president", "chief"
]

def is_israel_job(row):
    loc = str(row.get("location", "")).lower()
    if not loc or loc in ("", "nan", "none"):
        return True
    return any(k in loc for k in ISRAEL_KEYWORDS)

def is_senior_role(title, desc):
    """Return True if this is clearly a senior/lead role not suitable for students."""
    text = (title + " " + (desc or "")[:500]).lower()
    return any(k in text for k in SENIOR_KEYWORDS)

def run_scan_thread(cv_text, cv_filename, key, terms_str, location, hours_old, min_score, auto_apply, from_email, app_pw):
    from jobspy import scrape_jobs
    SCAN.update({"running":True,"log":[],"done":0,"total":0,"phase":"searching","auto_applied":0})
    min_score = int(min_score)
    auto_apply = bool(auto_apply)

    c = get_db()
    existing_urls = {r["job_url"] for r in c.execute("SELECT job_url FROM jobs").fetchall()}
    c.close()

    terms = [t.strip() for t in terms_str.split(",") if t.strip()]
    collected, seen = [], set()

    add_log(f"Agent started — {len(terms)} search terms · Student/Junior only · Auto-Apply: {'ON' if auto_apply else 'OFF'}")

    for term in terms:
        add_log(f"Searching: '{term}'…")
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=term,
                location=location,
                results_wanted=20,
                hours_old=int(hours_old),
                country_indeed="Israel",
                linkedin_fetch_description=True,
            )
            new = 0
            filtered_out = 0
            senior_out = 0
            for _, row in df.iterrows():
                url = str(row.get("job_url", ""))
                if not url or url in seen or url in existing_urls:
                    continue
                if not is_israel_job(row):
                    filtered_out += 1
                    continue
                # Pre-filter obvious senior roles (saves AI tokens)
                title_raw = str(row.get("title", ""))
                desc_raw  = str(row.get("description", ""))
                if is_senior_role(title_raw, desc_raw):
                    senior_out += 1
                    continue
                seen.add(url)
                collected.append(row)
                new += 1
            msg = f"  → {new} student/junior jobs"
            if filtered_out: msg += f" ({filtered_out} non-Israel skipped)"
            if senior_out:   msg += f" ({senior_out} senior roles skipped)"
            add_log(msg, "ok")
            time.sleep(2)
        except Exception as e:
            add_log(f"  Error: {e}", "err")

    SCAN["phase"] = "scoring"
    SCAN["total"] = len(collected)
    add_log(f"Scoring {len(collected)} jobs with AI (student/junior filter active)…")

    saved = 0
    high_jobs = []   # collect HIGH jobs for auto-apply

    for i, row in enumerate(collected):
        title   = str(row.get("title",    "Unknown"))
        company = str(row.get("company",  "Unknown"))
        loc     = str(row.get("location", ""))
        desc    = str(row.get("description", ""))
        url     = str(row.get("job_url",  ""))
        site    = str(row.get("site",     ""))

        add_log(f"[{i+1}/{len(collected)}] {title} @ {company}")
        result = ai_score_job(title, company, loc, desc, cv_text, key)
        SCAN["done"] = i + 1

        if result["score"] < min_score:
            add_log(f"  Skip — score {result['score']} < {min_score}")
            continue

        # Extract recruiter email from description
        recruiter_email = extract_recruiter_email(desc)

        c = get_db()
        job_id = None
        try:
            c.execute("""INSERT OR IGNORE INTO jobs
                (date_found,title,company,location,site,score,match_reason,
                 missing_skills,priority,job_url,description,status,recruiter_email)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now().strftime("%Y-%m-%d %H:%M"),
                 title, company, loc, site,
                 result["score"], result["match_reason"],
                 result["missing_skills"], result["priority"],
                 url, desc[:500], "Not Applied", recruiter_email))
            c.commit()
            job_id = c.execute("SELECT id FROM jobs WHERE job_url=?", (url,)).fetchone()
            if job_id: job_id = job_id[0]
            saved += 1
        except: pass
        finally: c.close()

        if result["priority"] == "HIGH" and job_id:
            high_jobs.append({
                "id": job_id, "title": title, "company": company,
                "desc": desc, "recruiter_email": recruiter_email, "score": result["score"]
            })
            add_log(f"  ★ HIGH match ({result['score']}/100) — queued for auto-apply", "ok")
        time.sleep(0.3)

    add_log(f"Done! {saved} jobs saved. {len(high_jobs)} HIGH-match jobs found.", "ok")

    # ── AUTO-APPLY PHASE ──────────────────────────────────────────────────────
    if auto_apply and high_jobs and from_email and app_pw:
        SCAN["phase"] = "applying"
        add_log(f"Auto-Apply: processing {len(high_jobs)} HIGH-match jobs…", "ok")

        for job in high_jobs:
            jid     = job["id"]
            title   = job["title"]
            company = job["company"]
            desc    = job["desc"]
            to_addr = job["recruiter_email"]

            add_log(f"  Generating cover letter for {title} @ {company}…")
            cl = ai_cover_letter(title, company, desc, cv_text, from_email, key)

            # Save cover letter to DB
            c = get_db()
            c.execute("UPDATE jobs SET cover_letter=? WHERE id=?", (cl, jid))
            c.commit(); c.close()

            if to_addr:
                add_log(f"  Sending application to {to_addr}…")
                subject = f"Application: {title} at {company} — Alaa Miari (Student, University of Haifa)"
                ok, err = send_gmail(to_addr, subject, cl, from_email, app_pw,
                                     cv_text=cv_text, cv_filename=cv_filename or "Alaa_Miari_CV.txt")
                if ok:
                    c = get_db()
                    c.execute("UPDATE jobs SET status='Auto-Applied', applied_at=?, recruiter_email=? WHERE id=?",
                              (datetime.now().isoformat(), to_addr, jid))
                    c.commit(); c.close()
                    SCAN["auto_applied"] += 1
                    add_log(f"  ✓ Application sent to {to_addr}", "ok")
                else:
                    add_log(f"  ✗ Email failed: {err}", "err")
                    # Still mark cover letter ready
                    c = get_db()
                    c.execute("UPDATE jobs SET status='Ready to Apply' WHERE id=?", (jid,))
                    c.commit(); c.close()
            else:
                # No email found — mark as ready so user can apply with 1 click
                c = get_db()
                c.execute("UPDATE jobs SET status='Ready to Apply' WHERE id=?", (jid,))
                c.commit(); c.close()
                add_log(f"  ⚡ Cover letter ready — no email found, visit job URL to apply", "info")
            time.sleep(1)

        add_log(f"Auto-Apply complete! {SCAN['auto_applied']} sent, "
                f"{len(high_jobs)-SCAN['auto_applied']} marked Ready to Apply.", "ok")
    elif auto_apply and not (from_email and app_pw):
        add_log("Auto-Apply is ON but Gmail not configured — skipped.", "err")

    SCAN["phase"] = "done"
    SCAN["running"] = False

# ═════════════════════════════════════════════════════════════════════════════
# HTML — single page app
# ═════════════════════════════════════════════════════════════════════════════
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Hunter — Alaa Miari</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root{
  --bg:#020817;--s1:#0b0e14;--s2:#111722;--s3:#161d2a;
  --bd:#1e293b;--bd2:#263347;
  --accent:#1dedba;--a2:#06b6d4;--aglow:rgba(29,237,186,.12);
  --green:#1dedba;--gdim:rgba(29,237,186,.1);
  --yellow:#fbbf24;--ydim:rgba(251,191,36,.08);
  --red:#f87171;--purple:#a78bfa;
  --text:#e2e8f0;--t2:#7ab8c4;--t3:#3d6070;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);
  font-size:14px;line-height:1.5;min-height:100vh}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:4px}

.shell{display:flex;height:100vh;overflow:hidden}
aside{width:215px;min-width:215px;background:var(--s1);border-right:1px solid var(--bd);
  display:flex;flex-direction:column;padding:1rem .75rem;overflow-y:auto}
.main{flex:1;overflow-y:auto;overflow-x:hidden}

.logo{display:flex;align-items:center;gap:10px;padding:.6rem .75rem;
  background:linear-gradient(135deg,rgba(29,237,186,.08),rgba(6,182,212,.05));
  border-radius:12px;border:1px solid rgba(29,237,186,.2);margin-bottom:1.25rem}
.logo-ico{width:32px;height:32px;background:linear-gradient(135deg,#0891b2,#1dedba);
  border-radius:8px;display:grid;place-items:center;font-size:.95rem;flex-shrink:0}
.logo-name{font-size:.8rem;font-weight:700;line-height:1.2}
.logo-sub{font-size:.62rem;color:var(--t3)}

.ns{font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:var(--t3);
  font-weight:600;padding:.4rem .6rem;margin-top:.5rem}
.ni{display:flex;align-items:center;gap:8px;padding:.5rem .65rem;border-radius:8px;
  cursor:pointer;color:var(--t2);font-size:.8rem;font-weight:500;transition:.12s;
  border:1px solid transparent;margin-bottom:1px;text-decoration:none;user-select:none}
.ni:hover{background:var(--s2);color:var(--text)}
.ni.on{background:var(--aglow);color:var(--accent);border-color:rgba(29,237,186,.2)}
.ni .ic{width:16px;text-align:center;font-size:.85rem;flex-shrink:0}
.nb{margin-left:auto;background:var(--accent);color:#fff;font-size:.58rem;
  font-weight:700;padding:1px 6px;border-radius:10px;min-width:16px;text-align:center}
.nb.g{background:var(--green)}
.nb.y{background:var(--yellow);color:#000}
.nb.p{background:var(--a2)}
.nb.v{background:var(--purple)}

.sf{margin-top:auto;padding-top:.75rem;border-top:1px solid var(--bd)}
.agent-pill{display:flex;align-items:center;gap:7px;padding:.45rem .65rem;
  background:var(--s2);border-radius:8px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--t3);flex-shrink:0}
.dot.idle{background:var(--t3)}
.dot.scanning{background:var(--yellow);box-shadow:0 0 7px var(--yellow);animation:blink .7s infinite}
.dot.applying{background:var(--purple);box-shadow:0 0 7px var(--purple);animation:blink .7s infinite}
.dot.done{background:#1dedba;box-shadow:0 0 7px #1dedba}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}

.pg{display:none;padding:2rem;max-width:1200px}
.pg.on{display:block}

.ph h1{font-size:1.3rem;font-weight:800;letter-spacing:-.02em;margin-bottom:.2rem}
.ph p{font-size:.8rem;color:var(--t2);margin-bottom:1.5rem}

.card{background:var(--s1);border:1px solid var(--bd);border-radius:14px;padding:1.25rem}
.card-sm{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:1rem}

.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:.65rem;margin-bottom:1.25rem}
.stat{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:.9rem 1rem}
.stat .n{font-size:1.8rem;font-weight:800;line-height:1;letter-spacing:-.03em}
.stat .l{font-size:.68rem;color:var(--t3);margin-top:3px;text-transform:uppercase;letter-spacing:.04em}
.stat.g .n{color:var(--green)}
.stat.y .n{color:var(--yellow)}
.stat.p .n{color:var(--a2)}
.stat.v .n{color:var(--purple)}

.tb{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin-bottom:1.1rem}
.tb input,.tb select{padding:.45rem .8rem;background:var(--s1);border:1px solid var(--bd);
  border-radius:8px;color:var(--text);font-size:.78rem;outline:none;transition:.12s}
.tb input:focus,.tb select:focus{border-color:var(--accent);box-shadow:0 0 0 2px var(--aglow)}
.tb input{width:200px}
.tb select option{background:var(--s2)}

.btn{display:inline-flex;align-items:center;gap:5px;padding:.5rem 1.1rem;border-radius:9px;
  font-size:.78rem;font-weight:600;cursor:pointer;border:none;transition:.15s;font-family:inherit}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-p{background:linear-gradient(135deg,#0891b2,#1dedba);color:#020817;
  box-shadow:0 2px 12px rgba(29,237,186,.25);font-weight:700}
.btn-p:hover:not(:disabled){filter:brightness(1.1);transform:translateY(-1px);box-shadow:0 6px 20px rgba(29,237,186,.35)}
.btn-g{background:var(--s2);color:var(--t2);border:1px solid var(--bd)}
.btn-g:hover{color:var(--text);border-color:var(--bd2)}
.btn-green{background:var(--gdim);color:var(--green);border:1px solid rgba(34,211,160,.25)}
.btn-green:hover{background:rgba(34,211,160,.18)}
.btn-purple{background:rgba(167,139,250,.1);color:var(--purple);border:1px solid rgba(167,139,250,.25)}
.btn-purple:hover{background:rgba(167,139,250,.18)}
.sm{padding:.32rem .75rem;font-size:.72rem;border-radius:7px}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:.85rem}
.jc{background:var(--s1);border:1px solid var(--bd);border-radius:14px;
  padding:1.1rem;transition:.15s;position:relative}
.jc::after{content:'';position:absolute;left:0;top:12px;bottom:12px;
  width:3px;border-radius:0 3px 3px 0}
.jc.HIGH::after{background:var(--green)}
.jc.MEDIUM::after{background:var(--yellow)}
.jc:hover{border-color:var(--bd2);transform:translateY(-2px);
  box-shadow:0 8px 28px rgba(0,0,0,.4)}
.jrow{display:flex;justify-content:space-between;align-items:flex-start;
  gap:8px;margin-bottom:5px}
.jt{font-size:.88rem;font-weight:600;line-height:1.35;flex:1}
.sc{font-size:.7rem;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}
.sc.h{background:rgba(29,237,186,.1);color:#1dedba;border:1px solid rgba(29,237,186,.25)}
.sc.m{background:var(--ydim);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
.sc.l{background:rgba(90,90,122,.1);color:var(--t3);border:1px solid var(--bd)}
.jmeta{font-size:.73rem;color:var(--t3);margin-bottom:8px;display:flex;gap:5px;flex-wrap:wrap}
.jmeta span{background:var(--s2);padding:1px 7px;border-radius:5px;border:1px solid var(--bd)}
.jreason{font-size:.74rem;line-height:1.6;color:var(--t2);background:var(--s2);
  padding:7px 9px;border-radius:8px;margin-bottom:7px}
.jmiss{font-size:.7rem;color:var(--yellow);background:var(--ydim);
  padding:4px 8px;border-radius:6px;margin-bottom:8px}
.jfoot{display:flex;align-items:center;justify-content:space-between;gap:5px}
.jsite{font-size:.62rem;text-transform:uppercase;letter-spacing:.07em;
  color:var(--t3);background:var(--s2);padding:2px 7px;border-radius:5px}
.jauto{font-size:.62rem;font-weight:700;padding:2px 8px;border-radius:5px;
  background:rgba(167,139,250,.12);color:var(--purple);border:1px solid rgba(167,139,250,.25)}
.jready{font-size:.62rem;font-weight:700;padding:2px 8px;border-radius:5px;
  background:rgba(251,191,36,.08);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
.jact{display:flex;gap:4px;align-items:center}
.ssel{padding:3px 7px;background:var(--s2);border:1px solid var(--bd);
  border-radius:6px;color:var(--t2);font-size:.7rem;cursor:pointer;outline:none;font-family:inherit}
.alink{background:linear-gradient(135deg,#0891b2,#1dedba);
  color:#fff;padding:3px 10px;border-radius:6px;font-size:.7rem;
  text-decoration:none;font-weight:600}
.clbtn{background:rgba(29,237,186,.1);color:#1dedba;padding:3px 9px;
  border-radius:6px;font-size:.7rem;cursor:pointer;border:none;font-weight:600;
  font-family:inherit;transition:.12s}
.clbtn:hover{background:rgba(34,211,160,.2)}

/* auto-apply banner */
.auto-banner{background:linear-gradient(135deg,rgba(167,139,250,.08),rgba(29,237,186,.06));
  border:1px solid rgba(167,139,250,.2);border-radius:12px;padding:.8rem 1.1rem;
  margin-bottom:1.25rem;display:flex;align-items:center;gap:10px;font-size:.8rem}
.auto-banner .icon{font-size:1.2rem}
.auto-banner strong{color:var(--purple)}

/* cv */
.drop{border:2px dashed var(--bd2);border-radius:14px;padding:2.5rem 2rem;
  text-align:center;cursor:pointer;transition:.2s;background:var(--s1)}
.drop:hover,.drop.drag{border-color:var(--accent);background:var(--aglow)}
.drop .big{font-size:2.5rem;display:block;margin-bottom:.65rem}
.drop h3{font-size:.92rem;font-weight:600;margin-bottom:.3rem}
.drop p{font-size:.76rem;color:var(--t3)}
.cvsummary{background:var(--s2);border-left:3px solid #1dedba;
  border-radius:0 10px 10px 0;padding:.75rem 1rem;font-size:.8rem;
  line-height:1.7;color:var(--t2);margin-bottom:1rem}
.cvgrid{display:grid;grid-template-columns:1fr 1fr;gap:.85rem;margin-top:.85rem}
.cvcard{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:1rem}
.cvcard h4{font-size:.65rem;text-transform:uppercase;letter-spacing:.07em;
  color:var(--t3);font-weight:600;margin-bottom:.6rem}
.cvcard.full{grid-column:1/-1}
.tags{display:flex;flex-wrap:wrap;gap:4px}
.tag{font-size:.7rem;padding:2px 9px;border-radius:20px;border:1px solid var(--bd2);
  color:var(--t2);background:var(--s2)}
.tag.s{border-color:rgba(124,106,247,.3);color:var(--a2);background:var(--aglow)}
.tag.j{border-color:rgba(34,211,160,.3);color:var(--green);background:var(--gdim)}
.tag.l{border-color:rgba(251,191,36,.3);color:var(--yellow);background:var(--ydim)}
.exprow{font-size:.76rem;color:var(--t2);padding:4px 0;
  border-bottom:1px solid var(--bd);line-height:1.4}
.exprow:last-child{border:none}

/* scan */
.scanlay{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem;align-items:start}
.fg{margin-bottom:.85rem}
.fg label{display:block;font-size:.67rem;color:var(--t3);font-weight:600;
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.fg input,.fg textarea,.fg select{
  width:100%;padding:.58rem .8rem;background:var(--s2);border:1px solid var(--bd);
  border-radius:8px;color:var(--text);font-size:.8rem;font-family:inherit;outline:none;transition:.12s}
.fg input:focus,.fg textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--aglow)}
.fg textarea{resize:vertical;min-height:85px}
.fg select option{background:var(--s2)}
.fg .hint{font-size:.67rem;color:var(--t3);margin-top:3px}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}

/* toggle switch */
.tog-row{display:flex;align-items:center;justify-content:space-between;
  padding:.6rem .8rem;background:var(--s2);border-radius:8px;border:1px solid var(--bd);margin-bottom:.85rem}
.tog-row .tl{font-size:.78rem;font-weight:600}
.tog-row .ts{font-size:.67rem;color:var(--t3);margin-top:1px}
.tog{position:relative;width:40px;height:22px;flex-shrink:0}
.tog input{opacity:0;width:0;height:0;position:absolute}
.togslide{position:absolute;inset:0;background:var(--bd2);border-radius:22px;cursor:pointer;transition:.2s}
.togslide:before{content:'';position:absolute;height:16px;width:16px;left:3px;bottom:3px;
  background:var(--t3);border-radius:50%;transition:.2s}
.tog input:checked+.togslide{background:linear-gradient(135deg,#0891b2,#1dedba)}
.tog input:checked+.togslide:before{transform:translateX(18px);background:#fff}

.logbox{background:var(--s2);border:1px solid var(--bd);border-radius:12px;
  padding:.85rem;max-height:340px;overflow-y:auto;font-family:'SF Mono',monospace}
.ll{font-size:.71rem;padding:1px 0;line-height:1.6;color:var(--t3)}
.ll.ok{color:var(--green)}
.ll.err{color:var(--red)}
.ll.info{color:var(--t2)}
.ll.apply{color:var(--purple)}

.ptrack{background:var(--s3);border-radius:20px;height:4px;overflow:hidden;margin:.6rem 0}
.pfill{height:100%;background:linear-gradient(90deg,#0891b2,#1dedba);
  border-radius:20px;transition:width .4s;width:0%}
.pfill.applying{background:linear-gradient(90deg,#7c3aed,#a78bfa)}
.phase-tag{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:20px;font-size:.7rem;font-weight:600;margin-bottom:.6rem}
.phase-tag.searching{background:var(--ydim);color:var(--yellow)}
.phase-tag.scoring{background:var(--aglow);color:var(--a2)}
.phase-tag.applying{background:rgba(167,139,250,.1);color:var(--purple)}
.phase-tag.done{background:var(--gdim);color:var(--green)}

/* settings */
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:.9rem;max-width:760px}
.scard{background:var(--s1);border:1px solid var(--bd);border-radius:14px;padding:1.2rem}
.scard h3{font-size:.85rem;font-weight:600;margin-bottom:.2rem}
.scard p{font-size:.74rem;color:var(--t3);margin-bottom:.85rem;line-height:1.5}
.scard.full{grid-column:1/-1}

/* setup */
.setup{max-width:500px;margin:2.5rem auto}
.setup-hero{text-align:center;margin-bottom:1.75rem}
.setup-hero .icon{font-size:3rem;display:block;margin-bottom:.65rem}
.setup-hero h1{font-size:1.4rem;font-weight:800;letter-spacing:-.03em;margin-bottom:.3rem}
.setup-hero p{font-size:.8rem;color:var(--t2);line-height:1.6}
.sbox{background:var(--s1);border:1px solid var(--bd);border-radius:16px;padding:1.65rem}
.step{display:flex;gap:.75rem;margin-bottom:1.2rem;padding-bottom:1.2rem;border-bottom:1px solid var(--bd)}
.step:last-of-type{border:none;margin-bottom:0;padding-bottom:0}
.snum{width:24px;height:24px;border-radius:50%;
  background:linear-gradient(135deg,#0891b2,#1dedba);
  color:#fff;font-size:.68rem;font-weight:700;display:grid;place-items:center;flex-shrink:0;margin-top:2px}
.sbody h4{font-size:.83rem;font-weight:600;margin-bottom:.2rem}
.sbody p{font-size:.74rem;color:var(--t3);margin-bottom:.55rem;line-height:1.5}

/* modal */
.mbg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);
  z-index:200;place-items:center;backdrop-filter:blur(4px)}
.mbg.open{display:grid}
.modal{background:var(--s1);border:1px solid var(--bd2);border-radius:16px;
  padding:1.4rem;width:min(560px,94vw);max-height:82vh;display:flex;
  flex-direction:column;box-shadow:0 24px 80px rgba(0,0,0,.6)}
.mh h3{font-size:.95rem;font-weight:700;margin-bottom:.15rem}
.mh p{font-size:.76rem;color:var(--t3);margin-bottom:.85rem}
.min{width:100%;padding:.55rem .8rem;background:var(--s2);border:1px solid var(--bd);
  border-radius:8px;color:var(--text);font-size:.8rem;font-family:inherit;
  outline:none;margin-bottom:.65rem;transition:.12s}
.min:focus{border-color:var(--accent)}
.modal textarea{flex:1;background:var(--s2);border:1px solid var(--bd);border-radius:9px;
  color:var(--text);font-size:.77rem;font-family:inherit;padding:.8rem;resize:none;
  min-height:230px;outline:none;line-height:1.7}
.modal textarea:focus{border-color:var(--accent)}
.mfoot{display:flex;gap:.55rem;justify-content:flex-end;margin-top:.75rem}

/* toasts */
.tray{position:fixed;bottom:1.25rem;right:1.25rem;z-index:999;
  display:flex;flex-direction:column;gap:.45rem;pointer-events:none}
.toast{background:var(--s1);border:1px solid var(--bd2);border-radius:9px;
  padding:.65rem .9rem;font-size:.78rem;display:flex;align-items:center;gap:7px;
  box-shadow:0 8px 28px rgba(0,0,0,.5);animation:sin .25s ease;min-width:230px}
.toast.success{border-color:rgba(34,211,160,.35);color:var(--green)}
.toast.error{border-color:rgba(248,113,113,.35);color:var(--red)}
.toast.info{border-color:rgba(124,106,247,.35);color:var(--a2)}
.toast.apply{border-color:rgba(167,139,250,.35);color:var(--purple)}
@keyframes sin{from{transform:translateX(40px);opacity:0}to{transform:none;opacity:1}}

/* spinner */
.sov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);
  z-index:300;place-items:center;flex-direction:column;gap:.85rem;
  backdrop-filter:blur(3px)}
.sov.open{display:grid}
.spin{width:40px;height:40px;border:3px solid var(--s3);
  border-top-color:var(--accent);border-radius:50%;animation:rot .7s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
.sov p{font-size:.82rem;color:var(--t2);margin-top:.25rem}

/* empty */
.empty{padding:3.5rem 1.5rem;text-align:center;color:var(--t3)}
.empty .ei{font-size:2.8rem;display:block;margin-bottom:.75rem}
.empty h3{font-size:.9rem;font-weight:600;margin-bottom:.3rem;color:var(--t2)}
.empty p{font-size:.78rem;line-height:1.6}

.div{height:1px;background:var(--bd);margin:1.1rem 0}
.sl{font-size:.67rem;text-transform:uppercase;letter-spacing:.08em;color:var(--t3);
  font-weight:600;margin-bottom:.65rem}
</style>
</head>
<body>
<div class="shell">

<!-- SIDEBAR -->
<aside>
  <div class="logo">
    <div class="logo-ico">⚡</div>
    <div><div class="logo-name">Job Hunter</div><div class="logo-sub">Student Edition</div></div>
  </div>

  <div class="ns">Main</div>
  <a class="ni on" id="n-dashboard" href="#" onclick="go(event,'dashboard')">
    <span class="ic">📊</span>Dashboard<span class="nb" id="nb-t">0</span></a>
  <a class="ni" id="n-cv" href="#" onclick="go(event,'cv')">
    <span class="ic">📄</span>My CV</a>
  <a class="ni" id="n-scan" href="#" onclick="go(event,'scan')">
    <span class="ic">🤖</span>Run Agent</a>

  <div class="ns">Pipeline</div>
  <a class="ni" href="#" onclick="go(event,'dashboard');flt('priority','HIGH')">
    <span class="ic">🟢</span>High Match<span class="nb g" id="nb-h">0</span></a>
  <a class="ni" href="#" onclick="go(event,'dashboard');flt('status','Auto-Applied')">
    <span class="ic">🤖</span>Auto-Applied<span class="nb v" id="nb-aa">0</span></a>
  <a class="ni" href="#" onclick="go(event,'dashboard');flt('status','Ready to Apply')">
    <span class="ic">⚡</span>Ready<span class="nb y" id="nb-r">0</span></a>
  <a class="ni" href="#" onclick="go(event,'dashboard');flt('status','Applied')">
    <span class="ic">📨</span>Applied<span class="nb y" id="nb-a">0</span></a>
  <a class="ni" href="#" onclick="go(event,'dashboard');flt('status','Interviewing')">
    <span class="ic">🎯</span>Interviews<span class="nb p" id="nb-i">0</span></a>

  <div class="ns">System</div>
  <a class="ni" id="n-settings" href="#" onclick="go(event,'settings')">
    <span class="ic">⚙️</span>Settings</a>

  <div class="sf">
    <div class="agent-pill">
      <div class="dot idle" id="agDot"></div>
      <span id="agTxt" style="font-size:.7rem;color:var(--t3)">Idle</span>
    </div>
  </div>
</aside>

<!-- MAIN -->
<div class="main">

<!-- SETUP PAGE -->
<div class="pg on" id="pg-setup">
<div class="setup">
  <div class="setup-hero">
    <span class="icon">🚀</span>
    <h1>Welcome, Alaa!</h1>
    <p>Your AI job agent finds <strong>student & junior</strong> jobs in Israel,<br>scores them, and <strong>auto-applies</strong> to HIGH matches for you.</p>
  </div>
  <div class="sbox">
    <div class="step">
      <div class="snum">1</div>
      <div class="sbody">
        <h4>OpenAI API Key</h4>
        <p>Get it at <strong>platform.openai.com → API Keys</strong></p>
        <input class="min" type="password" id="s-key" placeholder="sk-..." style="margin:0">
      </div>
    </div>
    <div class="step">
      <div class="snum">2</div>
      <div class="sbody">
        <h4>Gmail (used to send applications automatically)</h4>
        <input class="min" type="email" id="s-email" value="alaamiari@growwithyouu.com" style="margin:0 0 .5rem">
        <p style="margin:0">App Password: Google Account → Security → 2-Step → App Passwords</p>
        <input class="min" type="password" id="s-pw" placeholder="xxxx xxxx xxxx xxxx" style="margin:.5rem 0 0">
      </div>
    </div>
    <div class="step">
      <div class="snum">3</div>
      <div class="sbody">
        <h4>Job Location</h4>
        <input class="min" type="text" id="s-loc" value="Israel" style="margin:0">
      </div>
    </div>
    <button class="btn btn-p" onclick="doSetup()" style="width:100%;justify-content:center;padding:.7rem;margin-top:1rem;font-size:.85rem">
      Save & Launch →
    </button>
  </div>
</div>
</div>

<!-- DASHBOARD PAGE -->
<div class="pg" id="pg-dashboard">
<div class="ph">
  <h1>Dashboard</h1>
  <p>Student &amp; Junior jobs only — HIGH matches are auto-applied by the agent</p>
</div>
<div id="autoBanner" style="display:none" class="auto-banner">
  <span class="icon">🤖</span>
  <div><strong id="bannerText">Agent auto-applied to jobs</strong><br>
  <span style="font-size:.72rem;color:var(--t3)">Check Auto-Applied in the sidebar · Jobs marked "Ready to Apply" have cover letters ready but need a recruiter email</span></div>
</div>
<div class="stats">
  <div class="stat">  <div class="n" id="st-total">0</div><div class="l">Total</div></div>
  <div class="stat g"><div class="n" id="st-high">0</div><div class="l">High Match</div></div>
  <div class="stat y"><div class="n" id="st-med">0</div><div class="l">Medium</div></div>
  <div class="stat v"><div class="n" id="st-aa">0</div><div class="l">Auto-Applied</div></div>
  <div class="stat p"><div class="n" id="st-app">0</div><div class="l">Applied</div></div>
  <div class="stat">  <div class="n" id="st-int">0</div><div class="l">Interviews</div></div>
</div>
<div class="tb">
  <input id="sq" placeholder="Search title or company…" oninput="renderJobs()">
  <select id="sp" onchange="renderJobs()"><option value="">All Priorities</option>
    <option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
  <select id="ss" onchange="renderJobs()"><option value="">All Statuses</option>
    <option>Not Applied</option><option>Auto-Applied</option><option>Ready to Apply</option>
    <option>Applied</option><option>Interviewing</option><option>Offer</option><option>Rejected</option></select>
  <select id="si" onchange="renderJobs()"><option value="">All Sites</option>
    <option>linkedin</option><option>indeed</option></select>
  <button class="btn btn-p sm" onclick="go(null,'scan')">⚡ Run Agent</button>
  <button class="btn btn-g sm" onclick="loadJobs()">↻</button>
</div>
<div class="grid" id="jgrid"></div>
</div>

<!-- CV PAGE -->
<div class="pg" id="pg-cv">
<div class="ph">
  <h1>My CV</h1>
  <p>Upload your CV — AI reads it, generates student/junior search terms, and attaches it to every application</p>
</div>
<div class="drop" id="cvDrop"
  onclick="document.getElementById('cvFile').click()"
  ondragover="event.preventDefault();this.classList.add('drag')"
  ondragleave="this.classList.remove('drag')"
  ondrop="dropCv(event)">
  <span class="big">📄</span>
  <h3 id="cvTitle">Drop your CV here or click to upload</h3>
  <p>PDF, DOCX, or TXT — stored locally · attached to every auto-apply email</p>
  <input type="file" id="cvFile" accept=".pdf,.docx,.txt" style="display:none" onchange="uploadCv(this)">
</div>
<div id="cvResult" style="display:none">
  <div class="div"></div>
  <div class="sl">AI Analysis</div>
  <div class="cvsummary" id="cvSum"></div>
  <div class="cvgrid" id="cvGrid"></div>
</div>
</div>

<!-- SCAN PAGE -->
<div class="pg" id="pg-scan">
<div class="ph">
  <h1>Run AI Agent</h1>
  <p>Searches LinkedIn &amp; Indeed → filters to Student/Junior/Intern only → scores → auto-applies to HIGH matches</p>
</div>
<div class="scanlay">
  <div class="card">
    <div class="sl">Search Settings</div>

    <div class="tog-row">
      <div>
        <div class="tl">🤖 Auto-Apply to HIGH Matches</div>
        <div class="ts">Agent sends cover letter + CV automatically when score ≥ 70</div>
      </div>
      <label class="tog"><input type="checkbox" id="sc-auto" checked><span class="togslide"></span></label>
    </div>

    <div class="fg">
      <label>Search Terms <span style="font-weight:400;text-transform:none">(comma separated · student/junior/intern only)</span></label>
      <textarea id="sc-terms" rows="7" placeholder="Machine Learning intern Israel, Deep Learning student Israel…"></textarea>
    </div>
    <div class="row2">
      <div class="fg"><label>Location</label><input id="sc-loc" type="text" value="Israel"></div>
      <div class="fg"><label>Posted Within (hours)</label><input id="sc-hrs" type="number" value="72"></div>
    </div>
    <div class="fg"><label>Min Score to Save (0–100)</label><input id="sc-min" type="number" value="40" min="0" max="100"></div>
    <button class="btn btn-p" id="scanBtn" onclick="startScan()" style="width:100%;justify-content:center;padding:.65rem">
      ⚡ Start Agent
    </button>
  </div>
  <div class="card" style="min-height:380px;display:flex;flex-direction:column">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.6rem">
      <div class="sl" style="margin:0">Live Log</div>
      <div id="phaseTag" style="display:none"></div>
    </div>
    <div class="ptrack"><div class="pfill" id="pbar"></div></div>
    <div style="font-size:.7rem;color:var(--t3);margin-bottom:.6rem" id="pmsg">Ready</div>
    <div class="logbox" id="logbox" style="flex:1">
      <div class="ll">Agent ready. Press Start Agent to begin scanning for student/junior jobs.</div>
    </div>
    <div id="autoResult" style="display:none;margin-top:.75rem;padding:.65rem .85rem;
      background:rgba(167,139,250,.08);border:1px solid rgba(167,139,250,.2);border-radius:9px;
      font-size:.75rem;color:var(--purple)"></div>
  </div>
</div>
</div>

<!-- SETTINGS PAGE -->
<div class="pg" id="pg-settings">
<div class="ph">
  <h1>Settings</h1>
  <p>API key, Gmail, auto-apply, and search defaults</p>
</div>
<div class="sgrid">
  <div class="scard">
    <h3>🔑 OpenAI API Key</h3>
    <p>Used for job scoring and cover letter generation.</p>
    <div class="fg"><input type="password" id="c-key" placeholder="sk-…"></div>
    <button class="btn btn-g sm" onclick="saveCfg('api_key','c-key')">Save</button>
  </div>
  <div class="scard">
    <h3>📧 Gmail</h3>
    <p>Used to send application emails automatically. Your CV is attached to every email.</p>
    <div class="fg"><label>Email</label><input type="email" id="c-email"></div>
    <div class="fg"><label>App Password</label>
      <input type="password" id="c-pw">
      <div class="hint">Google Account → Security → 2-Step → App Passwords</div>
    </div>
    <button class="btn btn-g sm" onclick="saveGmail()">Save Gmail</button>
  </div>
  <div class="scard full">
    <h3>🤖 Auto-Apply</h3>
    <p>When enabled, the agent automatically generates a cover letter and emails it (with your CV attached) to every HIGH-match job where a recruiter email is found in the job description. Jobs without a recruiter email are marked "Ready to Apply" — cover letter is pre-written, just add the email and send.</p>
    <div class="tog-row" style="max-width:400px">
      <div>
        <div class="tl">Auto-Apply to HIGH matches</div>
        <div class="ts">Requires Gmail to be configured above</div>
      </div>
      <label class="tog"><input type="checkbox" id="c-auto" onchange="saveAutoApply()"><span class="togslide"></span></label>
    </div>
  </div>
  <div class="scard full">
    <h3>🔍 Search Defaults</h3>
    <p>Pre-filled when you start a new scan. All terms should include student/intern/junior.</p>
    <div class="row2">
      <div class="fg"><label>Location</label><input type="text" id="c-loc"></div>
      <div class="fg"><label>Min Score</label><input type="number" id="c-min" min="0" max="100"></div>
    </div>
    <div class="fg"><label>Search Terms</label><textarea id="c-terms" rows="3"></textarea></div>
    <button class="btn btn-g sm" onclick="saveSearch()">Save Defaults</button>
  </div>
</div>
</div>

</div><!-- /main -->
</div><!-- /shell -->

<!-- COVER LETTER MODAL -->
<div class="mbg" id="clModal">
  <div class="modal">
    <div class="mh">
      <h3>✉ Apply — <span id="clJob"></span></h3>
      <p>AI-written cover letter from your CV. Edit if needed, then send. Your CV will be attached.</p>
    </div>
    <input class="min" type="email" id="clTo" placeholder="Recruiter email address (required)">
    <textarea id="clBody"></textarea>
    <div class="mfoot">
      <button class="btn btn-g" onclick="closeM()">Cancel</button>
      <button class="btn btn-p" id="clSend" onclick="sendCL()">Send + CV via Gmail →</button>
    </div>
  </div>
</div>

<!-- TOASTS -->
<div class="tray" id="tray"></div>

<!-- SPINNER -->
<div class="sov" id="sov"><div class="spin"></div><p id="sovMsg">Working…</p></div>

<script>
let JOBS = [], CFG = {}, CL_JOB_ID = null, POLL = null;

const DEFAULT_TERMS = 'Machine Learning intern Israel,Deep Learning student Israel,AI Engineer intern Israel,Data Science intern Israel,NLP intern Israel,LLM engineer intern Israel,Generative AI intern Israel,MLOps intern Israel,Python developer intern Israel,Computer Vision intern Israel,AI research student Israel,Junior Data Scientist Israel,Junior ML Engineer Israel,Junior AI Developer Israel,Backend developer student Israel,AWS cloud intern Israel,Junior Software Engineer Israel,Data Analyst intern Israel';

async function boot(){
  const r = await fetch('/api/config');
  CFG = await r.json();
  if(!CFG.api_key){
    showPg('setup');
  } else {
    showPg('dashboard');
    loadJobs();
    loadCv();
    fillScanDefaults();
  }
}

function showPg(name){
  document.querySelectorAll('.pg').forEach(p=>p.classList.remove('on'));
  const el = document.getElementById('pg-'+name);
  if(el) el.classList.add('on');
}

function go(e, name){
  e && e.preventDefault();
  showPg(name);
  document.querySelectorAll('.ni').forEach(n=>n.classList.remove('on'));
  const nav = document.getElementById('n-'+name);
  if(nav) nav.classList.add('on');
  if(name==='settings') fillSettings();
  if(name==='scan')     fillScanDefaults();
  if(name==='dashboard') loadJobs();
}

function flt(key, val){
  if(key==='priority'){ document.getElementById('sp').value=val; document.getElementById('ss').value=''; }
  if(key==='status'){   document.getElementById('ss').value=val; document.getElementById('sp').value=''; }
  renderJobs();
}

async function doSetup(){
  const key = document.getElementById('s-key').value.trim();
  if(!key){ toast('Enter your OpenAI API key','error'); return; }
  const data = {
    api_key:      key,
    email:        document.getElementById('s-email').value.trim(),
    app_password: document.getElementById('s-pw').value.trim(),
    location:     document.getElementById('s-loc').value.trim() || 'Israel',
    min_score:    40,
    auto_apply:   true,
    search_terms: DEFAULT_TERMS
  };
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  CFG = data;
  toast('Setup saved! Upload your CV next 🎉','success');
  go(null,'cv');
}

async function loadJobs(){
  const r = await fetch('/api/jobs');
  const d = await r.json();
  JOBS = d.jobs || [];
  updateBadges(JOBS);
  renderJobs();
  const aa = JOBS.filter(j=>j.status==='Auto-Applied').length;
  const banner = document.getElementById('autoBanner');
  if(aa>0){
    document.getElementById('bannerText').textContent = `Agent auto-applied to ${aa} job${aa>1?'s':''}`;
    banner.style.display='flex';
  } else { banner.style.display='none'; }
}

function updateBadges(jobs){
  document.getElementById('nb-t').textContent  = jobs.length;
  document.getElementById('nb-h').textContent  = jobs.filter(j=>j.priority==='HIGH').length;
  document.getElementById('nb-aa').textContent = jobs.filter(j=>j.status==='Auto-Applied').length;
  document.getElementById('nb-r').textContent  = jobs.filter(j=>j.status==='Ready to Apply').length;
  document.getElementById('nb-a').textContent  = jobs.filter(j=>j.status==='Applied').length;
  document.getElementById('nb-i').textContent  = jobs.filter(j=>j.status==='Interviewing').length;
}

function renderJobs(){
  const q  = (document.getElementById('sq')||{value:''}).value.toLowerCase();
  const fp = (document.getElementById('sp')||{value:''}).value;
  const fs = (document.getElementById('ss')||{value:''}).value;
  const fi = (document.getElementById('si')||{value:''}).value;
  const out = JOBS.filter(j=>{
    const txt = ((j.title||'')+' '+(j.company||'')).toLowerCase();
    return(!q||txt.includes(q))&&(!fp||j.priority===fp)
          &&(!fs||j.status===fs)&&(!fi||(j.site||'')=== fi);
  });
  document.getElementById('st-total').textContent = out.length;
  document.getElementById('st-high').textContent  = out.filter(j=>j.priority==='HIGH').length;
  document.getElementById('st-med').textContent   = out.filter(j=>j.priority==='MEDIUM').length;
  document.getElementById('st-aa').textContent    = out.filter(j=>j.status==='Auto-Applied').length;
  document.getElementById('st-app').textContent   = out.filter(j=>j.status==='Applied').length;
  document.getElementById('st-int').textContent   = out.filter(j=>j.status==='Interviewing').length;
  const g = document.getElementById('jgrid');
  if(!out.length){
    g.innerHTML=`<div class="empty" style="grid-column:1/-1">
      <span class="ei">📭</span><h3>No jobs yet</h3>
      <p>Go to <strong>Run Agent</strong> to start scanning for student &amp; junior jobs</p></div>`;
    return;
  }
  g.innerHTML = out.map(j=>{
    const sc   = parseInt(j.score)||0;
    const scl  = sc>=70?'h':sc>=45?'m':'l';
    const miss = j.missing_skills&&!['None','N/A','none'].includes(j.missing_skills)
      ? `<div class="jmiss">⚠ Missing: ${j.missing_skills}</div>` : '';
    const statusBadge = j.status==='Auto-Applied'
      ? `<span class="jauto">🤖 Auto-Applied</span>`
      : j.status==='Ready to Apply'
      ? `<span class="jready">⚡ Ready</span>`
      : '';
    return `<div class="jc ${j.priority||'LOW'}">
      <div class="jrow">
        <div class="jt">${j.title||'–'}</div>
        <span class="sc ${scl}">${sc}/100</span>
      </div>
      <div class="jmeta">
        <span>🏢 ${j.company||'–'}</span><span>📍 ${j.location||'–'}</span>
        ${j.recruiter_email?`<span>📧 ${j.recruiter_email}</span>`:''}
      </div>
      <div class="jreason">${j.match_reason||'–'}</div>
      ${miss}
      <div class="jfoot">
        <div style="display:flex;gap:4px;align-items:center">
          <span class="jsite">${j.site||'–'}</span>
          ${statusBadge}
        </div>
        <div class="jact">
          <select class="ssel" onchange="setStatus(${j.id},this.value)">
            ${['Not Applied','Auto-Applied','Ready to Apply','Applied','Interviewing','Offer','Rejected']
              .map(s=>`<option${j.status===s?' selected':''}>${s}</option>`).join('')}
          </select>
          <button class="clbtn" onclick="openCL(${j.id},'${e$(j.title)}','${e$(j.company)}','${e$(j.recruiter_email||'')}')">✉ Apply</button>
          ${j.job_url?`<a class="alink" href="${j.job_url}" target="_blank">Open</a>`:''}
        </div>
      </div>
    </div>`;
  }).join('');
}

function e$(s){ return (s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }

async function setStatus(id, status){
  await fetch('/api/status',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id,status})});
  const j = JOBS.find(x=>x.id===id);
  if(j){ j.status=status; updateBadges(JOBS); }
}

async function openCL(id, title, company, recruiterEmail){
  CL_JOB_ID = id;
  document.getElementById('clJob').textContent = title+' @ '+company;
  document.getElementById('clBody').value = 'Writing cover letter with AI…';
  document.getElementById('clSend').disabled = true;
  document.getElementById('clTo').value = recruiterEmail || '';
  document.getElementById('clModal').classList.add('open');
  const r = await fetch('/api/cover-letter',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:id})});
  const d = await r.json();
  document.getElementById('clBody').value = d.cover_letter||'Error.';
  document.getElementById('clSend').disabled = false;
}

function closeM(){ document.getElementById('clModal').classList.remove('open'); CL_JOB_ID=null; }

async function sendCL(){
  const to   = document.getElementById('clTo').value.trim();
  const body = document.getElementById('clBody').value.trim();
  if(!to){ toast('Enter the recruiter email','error'); return; }
  const j = JOBS.find(x=>x.id===CL_JOB_ID);
  document.getElementById('clSend').disabled=true;
  document.getElementById('clSend').textContent='Sending…';
  const r = await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({job_id:CL_JOB_ID,to_email:to,
      subject:`Application: ${j?.title||''} at ${j?.company||''} — Alaa Miari (Student, University of Haifa)`,body})});
  const d = await r.json();
  if(d.ok){ toast('Application sent with CV attached! ✓','success'); setStatus(CL_JOB_ID,'Applied'); closeM(); }
  else     { toast('Error: '+d.error,'error'); }
  document.getElementById('clSend').disabled=false;
  document.getElementById('clSend').textContent='Send + CV via Gmail →';
}

async function loadCv(){
  const r = await fetch('/api/cv'); const d = await r.json();
  if(d.content){
    document.getElementById('cvTitle').textContent = '✅ '+d.filename;
    showCvAnalysis(d);
  }
}

async function uploadCv(inp){
  const f = inp.files[0]; if(!f) return;
  spin('Reading and analyzing your CV…');
  const fd = new FormData(); fd.append('cv', f);
  const r  = await fetch('/api/cv',{method:'POST',body:fd});
  const d  = await r.json();
  unSpin();
  if(d.ok){
    document.getElementById('cvTitle').textContent='✅ '+f.name;
    toast('CV analyzed! Student/junior search terms generated.','success');
    showCvAnalysis(d);
    if(d.analysis?.job_types?.length){
      const terms = d.analysis.job_types.join(', ');
      await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({search_terms:terms})});
      CFG.search_terms = terms;
    }
  } else { toast('Error: '+(d.error||'upload failed'),'error'); }
}

function dropCv(e){
  e.preventDefault();
  document.getElementById('cvDrop').classList.remove('drag');
  const f = e.dataTransfer.files[0];
  if(f){ const dt=new DataTransfer(); dt.items.add(f);
    document.getElementById('cvFile').files=dt.files;
    uploadCv(document.getElementById('cvFile')); }
}

function showCvAnalysis(d){
  const a = d.analysis||{};
  document.getElementById('cvResult').style.display='block';
  document.getElementById('cvSum').textContent = a.summary||'';
  const tags = (arr,cls)=>(arr||[]).map(x=>`<span class="tag ${cls}">${x}</span>`).join('');
  const exps = (arr)=>(arr||[]).map(x=>`<div class="exprow">▸ ${x}</div>`).join('');
  document.getElementById('cvGrid').innerHTML=`
    <div class="cvcard">
      <h4>👤 Profile</h4>
      <div style="font-size:.85rem;font-weight:600">${a.name||''}</div>
      <div style="font-size:.75rem;color:var(--a2);margin:.15rem 0">${a.title||''}</div>
      <div style="font-size:.72rem;color:var(--t3)">${a.education||''}</div>
      ${a.gpa?`<div style="font-size:.72rem;color:var(--green);margin-top:2px">GPA: ${a.gpa}</div>`:''}
    </div>
    <div class="cvcard">
      <h4>💬 Languages</h4>
      <div class="tags">${tags(a.languages,'l')||'<span class="tag">–</span>'}</div>
      <div style="margin-top:.6rem"></div>
      <h4>🏅 Certifications</h4>
      <div class="tags" style="margin-top:.4rem">${tags(a.certifications,'')||'<span class="tag">–</span>'}</div>
    </div>
    <div class="cvcard full">
      <h4>🛠 Technical Skills (${(a.skills||[]).length})</h4>
      <div class="tags">${tags(a.skills,'s')||'<span class="tag">–</span>'}</div>
    </div>
    <div class="cvcard">
      <h4>💼 Experience</h4>
      ${exps(a.experience)||'<div class="exprow">–</div>'}
    </div>
    <div class="cvcard">
      <h4>🎯 Student/Junior Jobs to Apply For</h4>
      <div class="tags">${tags(a.job_types,'j')||'<span class="tag">–</span>'}</div>
    </div>`;
}

function fillScanDefaults(){
  const t = document.getElementById('sc-terms');
  const l = document.getElementById('sc-loc');
  const a = document.getElementById('sc-auto');
  if(t) t.value = CFG.search_terms || DEFAULT_TERMS;
  if(l && CFG.location) l.value = CFG.location;
  if(a) a.checked = CFG.auto_apply !== false;
}

async function startScan(){
  const terms = document.getElementById('sc-terms').value.trim();
  const loc   = document.getElementById('sc-loc').value.trim();
  const hrs   = document.getElementById('sc-hrs').value;
  const min   = document.getElementById('sc-min').value;
  const auto  = document.getElementById('sc-auto').checked;
  if(!terms){ toast('Enter at least one search term','error'); return; }

  const cv = await fetch('/api/cv'); const cvd = await cv.json();
  if(!cvd.content){ toast('Upload your CV first (My CV tab)','error'); go(null,'cv'); return; }

  document.getElementById('scanBtn').disabled=true;
  document.getElementById('scanBtn').textContent='⏳ Running…';
  document.getElementById('agDot').className='dot scanning';
  document.getElementById('agTxt').textContent='Scanning…';
  document.getElementById('autoResult').style.display='none';

  const r = await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({search_terms:terms,location:loc,hours_old:hrs,min_score:min,auto_apply:auto})});
  const d = await r.json();
  if(!d.ok){ toast('Error: '+d.error,'error'); resetScanBtn(); return; }

  POLL = setInterval(pollScan, 2000);
}

async function pollScan(){
  const r = await fetch('/api/scan/status');
  const d = await r.json();

  const pct = d.total>0 ? Math.round(d.done/d.total*100) : (d.running?8:100);
  const pbar = document.getElementById('pbar');
  pbar.style.width = pct+'%';
  pbar.className = 'pfill' + (d.phase==='applying'?' applying':'');
  document.getElementById('pmsg').textContent  = d.progress||'';

  const pt = document.getElementById('phaseTag');
  if(d.phase && d.phase!=='idle'){
    pt.style.display='inline-flex';
    const labels = {searching:'🔍 Searching',scoring:'🤖 Scoring',applying:'🚀 Auto-Applying',done:'✓ Done'};
    pt.className = 'phase-tag '+(d.phase||'');
    pt.textContent = labels[d.phase]||d.phase;
  }

  if(d.phase==='applying'){
    document.getElementById('agDot').className='dot applying';
    document.getElementById('agTxt').textContent='Applying…';
  }

  if(d.log){
    const lb = document.getElementById('logbox');
    lb.innerHTML = d.log.slice(-40).map(l=>{
      const cls = l.msg&&(l.msg.includes('Auto-Apply')||l.msg.includes('sent'))&&l.level==='ok'?'apply':(l.level||'');
      return `<div class="ll ${cls}">${l.t}  ${l.msg}</div>`;
    }).join('');
    lb.scrollTop = lb.scrollHeight;
  }

  if(!d.running){
    clearInterval(POLL); POLL=null;
    resetScanBtn();
    document.getElementById('agDot').className='dot done';
    document.getElementById('agTxt').textContent='Done';
    document.getElementById('pbar').style.width='100%';
    document.getElementById('pbar').className='pfill';
    if(d.auto_applied>0){
      const ar = document.getElementById('autoResult');
      ar.textContent = `🤖 Agent auto-applied to ${d.auto_applied} job${d.auto_applied>1?'s':''}! Check your Gmail sent folder.`;
      ar.style.display='block';
      toast(`Auto-applied to ${d.auto_applied} jobs! Check Gmail.`,'apply');
    } else {
      toast('Scan complete! Check Dashboard for results.','success');
    }
    loadJobs();
    setTimeout(()=>{ document.getElementById('agDot').className='dot idle';
      document.getElementById('agTxt').textContent='Idle'; }, 5000);
  }
}

function resetScanBtn(){
  document.getElementById('scanBtn').disabled=false;
  document.getElementById('scanBtn').textContent='⚡ Start Agent';
}

async function fillSettings(){
  const r = await fetch('/api/config'); CFG = await r.json();
  document.getElementById('c-key').value   = CFG.api_key||'';
  document.getElementById('c-email').value = CFG.email||'';
  document.getElementById('c-pw').value    = '';
  document.getElementById('c-loc').value   = CFG.location||'';
  document.getElementById('c-min').value   = CFG.min_score||40;
  document.getElementById('c-terms').value = CFG.search_terms||DEFAULT_TERMS;
  document.getElementById('c-auto').checked = CFG.auto_apply !== false;
}
async function saveCfg(key,id){
  const v=document.getElementById(id).value.trim();
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:v})});
  CFG[key]=v; toast('Saved!','success');
}
async function saveGmail(){
  const d={email:document.getElementById('c-email').value.trim(),
            app_password:document.getElementById('c-pw').value.trim()};
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  CFG={...CFG,...d}; toast('Gmail saved!','success');
}
async function saveAutoApply(){
  const v = document.getElementById('c-auto').checked;
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_apply:v})});
  CFG.auto_apply=v; toast(v?'Auto-Apply enabled!':'Auto-Apply disabled','success');
}
async function saveSearch(){
  const d={location:document.getElementById('c-loc').value.trim(),
            min_score:parseInt(document.getElementById('c-min').value)||40,
            search_terms:document.getElementById('c-terms').value.trim()};
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  CFG={...CFG,...d}; fillScanDefaults(); toast('Search defaults saved!','success');
}

function spin(msg){ document.getElementById('sovMsg').textContent=msg||'Working…'; document.getElementById('sov').classList.add('open'); }
function unSpin(){ document.getElementById('sov').classList.remove('open'); }
function toast(msg,type='info'){
  const t=document.getElementById('tray');
  const el=document.createElement('div'); el.className='toast '+type; el.textContent=msg;
  t.appendChild(el); setTimeout(()=>el.remove(),4000);
}

boot();
</script>
</body>
</html>"""

# ─── routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template_string(PAGE)

@app.route("/api/config", methods=["GET","POST"])
def api_cfg():
    if request.method=="GET":
        c = read_cfg()
        return jsonify({k:v for k,v in c.items() if k!="app_password"}|{"has_gmail":bool(c.get("app_password"))})
    write_cfg(request.get_json()); return jsonify({"ok":True})

@app.route("/api/cv", methods=["GET","POST"])
def api_cv():
    if request.method=="GET":
        c=get_db(); row=c.execute("SELECT raw,filename,analysis FROM cv WHERE id=1").fetchone(); c.close()
        if row:
            try: a=json.loads(row["analysis"] or "{}")
            except: a={}
            return jsonify({"content":row["raw"],"filename":row["filename"],"analysis":a})
        return jsonify({"content":None})
    f=request.files.get("cv")
    if not f: return jsonify({"ok":False,"error":"No file uploaded"})
    ext="."+f.filename.rsplit(".",1)[-1].lower()
    with tempfile.NamedTemporaryFile(suffix=ext,delete=False) as tmp:
        f.save(tmp.name); path=tmp.name
    text=parse_file(path,f.filename); os.unlink(path)
    if not text: return jsonify({"ok":False,"error":"Could not read file"})
    key=read_cfg().get("api_key","")
    analysis=ai_analyze_cv(text,key) if key else {}
    c=get_db(); c.execute("DELETE FROM cv")
    c.execute("INSERT INTO cv(id,raw,filename,saved_at,analysis)VALUES(1,?,?,?,?)",
              (text,f.filename,datetime.now().isoformat(),json.dumps(analysis)))
    c.commit(); c.close()
    return jsonify({"ok":True,"analysis":analysis})

@app.route("/api/jobs")
def api_jobs():
    c=get_db(); rows=c.execute("SELECT * FROM jobs ORDER BY score DESC").fetchall(); c.close()
    return jsonify({"jobs":[dict(r) for r in rows]})

@app.route("/api/status", methods=["POST"])
def api_status():
    d=request.get_json(); c=get_db()
    c.execute("UPDATE jobs SET status=? WHERE id=?",(d["status"],d["id"]))
    if d["status"] in ("Applied","Auto-Applied"):
        c.execute("UPDATE jobs SET applied_at=? WHERE id=?",(datetime.now().isoformat(),d["id"]))
    c.commit(); c.close(); return jsonify({"ok":True})

@app.route("/api/cover-letter", methods=["POST"])
def api_cl():
    d=request.get_json(); c=get_db()
    job=c.execute("SELECT * FROM jobs WHERE id=?",(d["job_id"],)).fetchone()
    cv=c.execute("SELECT raw FROM cv WHERE id=1").fetchone(); c.close()
    if not job: return jsonify({"cover_letter":"Job not found."})
    if not cv:  return jsonify({"cover_letter":"Upload your CV first."})
    cfg=read_cfg()
    # Return cached cover letter if already generated
    if job["cover_letter"]:
        return jsonify({"cover_letter":job["cover_letter"]})
    cl=ai_cover_letter(job["title"],job["company"],job["description"] or "",
                       cv["raw"],cfg.get("email",""),cfg.get("api_key",""))
    c=get_db(); c.execute("UPDATE jobs SET cover_letter=? WHERE id=?",(cl,d["job_id"])); c.commit(); c.close()
    return jsonify({"cover_letter":cl})

@app.route("/api/send", methods=["POST"])
def api_send():
    d=request.get_json(); cfg=read_cfg()
    em=cfg.get("email",""); pw=cfg.get("app_password","")
    if not em or not pw: return jsonify({"ok":False,"error":"Gmail not configured in Settings"})
    # Attach CV
    c=get_db(); cv_row=c.execute("SELECT raw,filename FROM cv WHERE id=1").fetchone(); c.close()
    cv_text=cv_row["raw"] if cv_row else None
    cv_name=cv_row["filename"] if cv_row else "Alaa_Miari_CV.txt"
    ok,msg=send_gmail(d["to_email"],d["subject"],d["body"],em,pw,cv_text=cv_text,cv_filename=cv_name)
    if ok:
        c=get_db(); c.execute("UPDATE jobs SET status='Applied',applied_at=?,recruiter_email=? WHERE id=?",
                               (datetime.now().isoformat(),d["to_email"],d["job_id"])); c.commit(); c.close()
    return jsonify({"ok":ok,"error":msg if not ok else ""})

@app.route("/api/scan", methods=["POST"])
def api_scan():
    if SCAN["running"]: return jsonify({"ok":False,"error":"Scan already running"})
    d=request.get_json(); cfg=read_cfg()
    c=get_db(); cv=c.execute("SELECT raw,filename FROM cv WHERE id=1").fetchone(); c.close()
    if not cv: return jsonify({"ok":False,"error":"Upload your CV first (My CV tab)"})
    if not cfg.get("api_key"): return jsonify({"ok":False,"error":"No API key in Settings"})
    auto_apply = d.get("auto_apply", cfg.get("auto_apply", False))
    threading.Thread(target=run_scan_thread, daemon=True, args=(
        cv["raw"],
        cv["filename"],
        cfg["api_key"],
        d.get("search_terms", cfg.get("search_terms", "")),
        d.get("location",     cfg.get("location", "Israel")),
        d.get("hours_old",    72),
        d.get("min_score",    cfg.get("min_score", 40)),
        auto_apply,
        cfg.get("email", ""),
        cfg.get("app_password", ""),
    )).start()
    return jsonify({"ok":True})

@app.route("/api/scan/status")
def api_scan_status(): return jsonify(SCAN)

# ─── run ──────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    init_db()
    print("\n"+"="*55)
    print("  Alaa's AI Job Hunter — Student & Junior Edition")
    print("  Open: http://localhost:8080")
    print("  Features: Student/Junior only · Auto-Apply engine")
    print("="*55+"\n")
    app.run(debug=False,port=8080,host="0.0.0.0")
