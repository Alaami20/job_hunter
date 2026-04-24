"""
╔══════════════════════════════════════════════════════╗
║   🚀 Alaa's AI Job Hunter — Web Dashboard (Phase 2)  ║
╚══════════════════════════════════════════════════════╝

RUN:
    python web_app.py
    Open browser: http://localhost:5000
"""

from flask import Flask, render_template_string, jsonify, request
import gspread
from google.oauth2.service_account import Credentials
import anthropic
import time, json
from datetime import datetime

# Import shared config from job_scraper
from job_scraper import (
    ANTHROPIC_API_KEY, GOOGLE_CREDS_FILE, SPREADSHEET_NAME,
    CV_PROFILE, scrape_all_jobs, score_job, SHEET_HEADERS
)

app = Flask(__name__)

# ── Sheets helpers ─────────────────────────────────────────────────────────────

def get_sheet():
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds  = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
    return gspread.authorize(creds).open(SPREADSHEET_NAME).sheet1

def get_all_jobs():
    try:
        return get_sheet().get_all_records()
    except Exception as e:
        return []

def set_status(row_index, status):
    get_sheet().update_cell(row_index + 2, 12, status)

# ── HTML Dashboard ─────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alaa's Job Hunter</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f4f0;color:#111}
header{background:#0f0f2a;color:#fff;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:1.1rem;font-weight:500}
.tag{font-size:.7rem;background:#ffffff22;padding:2px 8px;border-radius:10px;margin-left:8px}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;padding:1.25rem 2rem 0}
.stat{background:#fff;border-radius:10px;padding:.9rem 1.1rem}
.stat .n{font-size:1.9rem;font-weight:600}
.stat .l{font-size:.72rem;color:#888;margin-top:2px}
.stat.g .n{color:#16a34a}
.stat.y .n{color:#ca8a04}

.bar{display:flex;gap:.75rem;padding:1rem 2rem;flex-wrap:wrap;align-items:center}
.bar input,.bar select{padding:.45rem .75rem;border:1px solid #ddd;border-radius:8px;font-size:.85rem;background:#fff}
.bar input{width:210px}
.scan-btn{background:#0f0f2a;color:#fff;border:none;padding:.45rem 1.2rem;border-radius:8px;font-size:.85rem;cursor:pointer}
.scan-btn:hover{background:#1e1e4a}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem;padding:0 2rem 2rem}

.card{background:#fff;border-radius:12px;padding:1.1rem 1.2rem;border:1px solid #eee;position:relative}
.card.H{border-left:4px solid #16a34a}
.card.M{border-left:4px solid #ca8a04}
.card.L{border-left:4px solid #e5e7eb}

.ch{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}
.ct{font-size:.92rem;font-weight:600;line-height:1.3;flex:1;margin-right:8px}
.score{font-size:.78rem;font-weight:700;padding:2px 9px;border-radius:20px;white-space:nowrap}
.sh{background:#dcfce7;color:#15803d}
.sm{background:#fef9c3;color:#854d0e}
.sl{background:#f3f4f6;color:#6b7280}

.co{font-size:.78rem;color:#555;margin-bottom:8px}
.reason{font-size:.76rem;color:#333;line-height:1.5;background:#f9f9f7;padding:7px 9px;border-radius:6px;margin-bottom:8px}
.miss{font-size:.73rem;color:#b45309;margin-bottom:10px}
.miss b{font-weight:600}

.cf{display:flex;justify-content:space-between;align-items:center}
.site-tag{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:#aaa;background:#f4f4f0;padding:2px 7px;border-radius:4px}
.actions{display:flex;gap:5px;align-items:center}
.sel{font-size:.73rem;padding:4px 7px;border:1px solid #ddd;border-radius:6px;background:#fff;cursor:pointer}
.apply{background:#0f0f2a;color:#fff;padding:4px 12px;border-radius:7px;font-size:.75rem;text-decoration:none;white-space:nowrap}
.apply:hover{background:#1e1e4a}

.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:99;align-items:center;justify-content:center;flex-direction:column;gap:1rem;color:#fff;font-size:.95rem}
.overlay.on{display:flex}
.spin{width:38px;height:38px;border:3px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

.empty{padding:3rem 2rem;color:#888;font-size:.9rem}

@media(max-width:600px){
  .stats{grid-template-columns:1fr 1fr}
  .grid{grid-template-columns:1fr;padding:0 1rem 1rem}
  .bar{padding:1rem}
}
</style>
</head>
<body>

<header>
  <h1>🚀 Alaa's Job Hunter <span class="tag">Growwithyouu</span></h1>
  <span id="ts" style="font-size:.75rem;opacity:.5">Loading…</span>
</header>

<div class="stats">
  <div class="stat"><div class="n" id="s-total">–</div><div class="l">Total jobs</div></div>
  <div class="stat g"><div class="n" id="s-high">–</div><div class="l">HIGH priority</div></div>
  <div class="stat y"><div class="n" id="s-med">–</div><div class="l">MEDIUM priority</div></div>
  <div class="stat"><div class="n" id="s-applied">–</div><div class="l">Applied / Interview</div></div>
</div>

<div class="bar">
  <input  id="q"  placeholder="Search title or company…" oninput="filter()">
  <select id="fp" onchange="filter()">
    <option value="">All priorities</option>
    <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
  </select>
  <select id="fs" onchange="filter()">
    <option value="">All sites</option>
    <option>linkedin</option><option>indeed</option><option>glassdoor</option>
  </select>
  <select id="fst" onchange="filter()">
    <option value="">All statuses</option>
    <option>Not Applied</option><option>Applied</option>
    <option>Interviewing</option><option>Offer</option><option>Rejected</option>
  </select>
  <button class="scan-btn" onclick="scan()">🔍 Scan new jobs</button>
</div>

<div class="grid" id="grid"></div>

<div class="overlay" id="ov">
  <div class="spin"></div>
  <div id="ovmsg">Scanning LinkedIn · Indeed · Glassdoor…</div>
</div>

<script>
let all = [];

async function load(){
  const r = await fetch('/api/jobs');
  const d = await r.json();
  all = d.jobs || [];
  stats(all); render(all);
  document.getElementById('ts').textContent = 'Updated ' + new Date().toLocaleTimeString();
}

function stats(j){
  document.getElementById('s-total').textContent   = j.length;
  document.getElementById('s-high').textContent    = j.filter(x=>x['Apply Priority']==='HIGH').length;
  document.getElementById('s-med').textContent     = j.filter(x=>x['Apply Priority']==='MEDIUM').length;
  document.getElementById('s-applied').textContent = j.filter(x=>['Applied','Interviewing','Offer'].includes(x['Status'])).length;
}

function render(jobs){
  const g = document.getElementById('grid');
  if(!jobs.length){g.innerHTML='<p class="empty">No jobs found. Run a scan!</p>';return;}
  g.innerHTML = jobs.map((j,i)=>{
    const sc   = parseInt(j['Match Score'])||0;
    const pr   = (j['Apply Priority']||'L')[0];
    const scls = sc>=70?'sh':sc>=45?'sm':'sl';
    const miss = (j['Key Missing Skills']&&j['Key Missing Skills']!=='None')
      ? `<div class="miss"><b>Missing:</b> ${j['Key Missing Skills']}</div>` : '';
    const url  = j['Job URL']||'';
    return `<div class="card ${pr}">
      <div class="ch">
        <div class="ct">${j['Job Title']||'–'}</div>
        <span class="score ${scls}">${sc}/100</span>
      </div>
      <div class="co">🏢 ${j['Company']||'–'} &nbsp;·&nbsp; 📍 ${j['Location']||'–'}</div>
      <div class="reason">${j['Match Reason']||'–'}</div>
      ${miss}
      <div class="cf">
        <span class="site-tag">${j['Site']||'–'}</span>
        <div class="actions">
          <select class="sel" onchange="upd(${i},this.value)">
            ${['Not Applied','Applied','Interviewing','Offer','Rejected']
              .map(s=>`<option${j['Status']===s?' selected':''}>${s}</option>`).join('')}
          </select>
          ${url?`<a class="apply" href="${url}" target="_blank">Apply →</a>`:''}
        </div>
      </div>
    </div>`;
  }).join('');
}

function filter(){
  const q   = document.getElementById('q').value.toLowerCase();
  const fp  = document.getElementById('fp').value;
  const fs  = document.getElementById('fs').value;
  const fst = document.getElementById('fst').value;
  const out = all.filter(j=>{
    const txt = ((j['Job Title']||'')+' '+(j['Company']||'')).toLowerCase();
    return (!q||txt.includes(q))
      && (!fp||j['Apply Priority']===fp)
      && (!fs||(j['Site']||'').toLowerCase()===fs.toLowerCase())
      && (!fst||j['Status']===fst);
  });
  stats(out); render(out);
}

async function upd(i, status){
  all[i]['Status'] = status;
  await fetch('/api/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:i,status})});
}

async function scan(){
  document.getElementById('ov').classList.add('on');
  document.getElementById('ovmsg').textContent = 'Scanning LinkedIn · Indeed · Glassdoor…';
  try{
    const r = await fetch('/api/scan',{method:'POST'});
    const d = await r.json();
    document.getElementById('ovmsg').textContent = `Found ${d.new_jobs} new jobs! Reloading…`;
    await new Promise(r=>setTimeout(r,1500));
    await load();
  } catch(e){
    document.getElementById('ovmsg').textContent = 'Error — check your terminal.';
    await new Promise(r=>setTimeout(r,2000));
  }
  document.getElementById('ov').classList.remove('on');
}

load();
setInterval(load, 60000);
</script>
</body>
</html>"""

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/jobs")
def api_jobs():
    try:
        jobs = get_all_jobs()
        return jsonify({"jobs": jobs})
    except Exception as e:
        return jsonify({"jobs": [], "error": str(e)})

@app.route("/api/status", methods=["POST"])
def api_status():
    d = request.get_json()
    try:
        set_status(d["index"], d["status"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/scan", methods=["POST"])
def api_scan():
    try:
        sheet    = get_sheet()
        existing = {row[9] for row in sheet.get_all_values()[1:] if len(row) > 9}
        jobs     = scrape_all_jobs()
        claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        rows     = []
        for job in jobs:
            url = str(job.get("job_url",""))
            if url in existing:
                continue
            r    = score_job(job, claude)
            desc = str(job.get("description",""))[:300].replace("\n"," ")
            rows.append([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                str(job.get("title","")), str(job.get("company","")),
                str(job.get("location","")), str(job.get("site","")),
                r["score"], r["match_reason"], r["missing_skills"],
                r["priority"], url, desc, "Not Applied"
            ])
            time.sleep(0.5)
        if rows:
            sheet.append_rows(rows, value_input_option="USER_ENTERED")
        return jsonify({"new_jobs": len(rows)})
    except Exception as e:
        return jsonify({"new_jobs": 0, "error": str(e)})

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Alaa's Job Hunter — Web Dashboard")
    print("  Open: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, port=5000)
