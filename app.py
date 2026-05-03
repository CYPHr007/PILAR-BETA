# -*- coding: utf-8 -*-
"""
PILAR Beta — Access portal
==========================
Public landing → request access → admin approves → signup link →
user creates account → protected download page.

ENV vars:
  SECRET_KEY       Flask secret (required in prod)
  ADMIN_PASSWORD   Admin panel password  (default: pilar-admin-2026)
  DATABASE_URL     postgres://... (Railway/Render) or leave blank for SQLite
  DOWNLOAD_URL     Direct .exe download link (GitHub release asset)
  APP_VERSION      e.g. v1.5.1
  BASE_URL         https://your-domain.com
  GMAIL_ADDRESS    Gmail sender address (optional — for email notifications)
  GMAIL_APP_PASS   Gmail App Password   (optional)
  NOTIFY_EMAIL     Where to send new-request alerts (optional)
"""

import os, secrets, hashlib, smtplib, json
from datetime import datetime, timezone
from functools import wraps
from email.mime.text import MIMEText

from flask import (Flask, Blueprint, request, session, redirect, url_for,
                   render_template, render_template_string, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy

# ── Config ────────────────────────────────────────────────────────────────────
APP_VERSION    = os.environ.get('APP_VERSION',    'v1.5.1')
BASE_URL       = os.environ.get('BASE_URL',       'http://localhost:5002')
DOWNLOAD_URL   = os.environ.get('DOWNLOAD_URL',   'https://github.com/CYPHr007/PILAR/releases/download/v1.5.1/PILAR_Setup_1.5.1.exe')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'pilar-admin-2026')
ADMIN_PATH     = os.environ.get('ADMIN_PATH',     'pilar-control')
GMAIL          = os.environ.get('GMAIL_ADDRESS',  '')
GMAIL_PASS     = os.environ.get('GMAIL_APP_PASS', '').replace(' ', '')
NOTIFY_EMAIL   = os.environ.get('NOTIFY_EMAIL',   '')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

_db_url = os.environ.get('DATABASE_URL', '')
if not _db_url:
    _db_url = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'pilar_beta.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ── Models ────────────────────────────────────────────────────────────────────
class AccessRequest(db.Model):
    __tablename__ = 'access_requests'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200))
    email        = db.Column(db.String(200), nullable=False)
    company      = db.Column(db.String(200))
    role         = db.Column(db.String(200))
    use_case     = db.Column(db.Text)
    status       = db.Column(db.String(20), default='pending')  # pending|approved|rejected
    signup_token = db.Column(db.String(64), unique=True, nullable=True)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    approved_at  = db.Column(db.DateTime, nullable=True)


class User(db.Model):
    __tablename__ = 'users'
    id               = db.Column(db.Integer, primary_key=True)
    email            = db.Column(db.String(200), unique=True, nullable=False)
    name             = db.Column(db.String(200), default='')
    company          = db.Column(db.String(200), default='')
    pw_hash          = db.Column(db.String(128))
    license_key      = db.Column(db.String(32), unique=True, nullable=True)
    license_revoked  = db.Column(db.Boolean, default=False)
    request_id       = db.Column(db.Integer, nullable=True)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ── Helpers ───────────────────────────────────────────────────────────────────
def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

def _gen_license():
    p = secrets.token_hex(8).upper()
    return f"PILAR-{p[:4]}-{p[4:8]}-{p[8:12]}"

def _send_email(to, subject, body):
    if not GMAIL or not GMAIL_PASS:
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = GMAIL
        msg['To'] = to
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(GMAIL, GMAIL_PASS)
            s.sendmail(GMAIL, to, msg.as_string())
        return True
    except Exception as e:
        print(f'[email] {e}')
        return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page', next=request.path))
        return f(*args, **kwargs)
    return decorated

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated

# ── CSS / HTML fragments ──────────────────────────────────────────────────────
_FONTS = 'https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Serif+Display&family=JetBrains+Mono:wght@300;400;500&display=swap'

_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#08090c;--surface:#0f1117;--surface2:#131720;
  --border:#1c2130;--border2:#252d3d;
  --accent:#0d9488;--accent-dim:rgba(13,148,136,.12);
  --text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;
  --red:#f87171;--red-dim:rgba(248,113,113,.12);
  --green:#34d399;--green-dim:rgba(52,211,153,.10);
  --amber:#fbbf24;
  --r:6px;--r-sm:4px;
  --sans:'DM Sans',system-ui,sans-serif;
  --serif:'DM Serif Display',Georgia,serif;
  --mono:'JetBrains Mono','IBM Plex Mono',monospace;
}
body{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5;font-size:15px}
a{color:var(--accent);text-decoration:none}
a:hover{opacity:.8}
.container{max-width:880px;margin:0 auto;padding:0 28px}
/* ── Nav ── */
nav{position:sticky;top:0;z-index:100;background:rgba(8,9,12,.9);
  backdrop-filter:blur(14px);border-bottom:1px solid var(--border);padding:0 28px}
.nav-inner{max-width:880px;margin:0 auto;display:flex;align-items:center;
  justify-content:space-between;height:54px}
.nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text)}
.logo-mark{display:flex;gap:5px;align-items:center}
.bar{border-radius:2px;flex-shrink:0}
.bar1{width:5px;height:20px;background:var(--text)}
.bar2{width:5px;height:14px;background:var(--text3)}
.logo-word{font-family:var(--mono);font-size:13px;font-weight:500;letter-spacing:.22em;
  text-transform:uppercase;color:var(--text)}
.nav-links{display:flex;gap:24px;align-items:center}
.nav-link{font-family:var(--mono);font-size:10px;font-weight:400;letter-spacing:.1em;
  text-transform:uppercase;color:var(--text2);text-decoration:none;transition:color .15s}
.nav-link:hover{color:var(--text);opacity:1}
.nav-cta{font-family:var(--mono);font-size:10px;font-weight:500;letter-spacing:.1em;
  text-transform:uppercase;color:var(--text);background:var(--accent);
  padding:8px 18px;border-radius:var(--r);text-decoration:none;transition:opacity .15s}
.nav-cta:hover{opacity:.85}
/* ── Hero ── */
.hero{padding:96px 0 72px;text-align:center}
.hero-chip{font-family:var(--mono);font-size:10px;font-weight:400;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);border:1px solid var(--accent-dim);
  border-radius:20px;padding:5px 16px;display:inline-block;margin-bottom:28px}
.hero-title{font-family:var(--serif);font-size:clamp(2.6rem,5.5vw,4.2rem);font-weight:400;
  line-height:1.08;letter-spacing:-.01em;margin-bottom:20px;color:var(--text)}
.hero-sub{font-size:1rem;color:var(--text2);max-width:50ch;margin:0 auto 40px;line-height:1.75;font-weight:300}
/* ── Stats ── */
.stats{display:flex;justify-content:center;gap:0;
  border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-bottom:72px}
.stat{padding:28px 48px;text-align:center;border-right:1px solid var(--border)}
.stat:last-child{border-right:none}
.stat-val{font-family:var(--mono);font-size:1.6rem;font-weight:500;color:var(--text)}
.stat-lbl{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.12em;
  text-transform:uppercase;color:var(--text3);margin-top:4px}
/* ── Features ── */
.features{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;
  background:var(--border);border:1px solid var(--border);border-radius:var(--r);
  overflow:hidden;margin-bottom:72px}
.feat{background:var(--surface);padding:28px 24px}
.feat:hover{background:var(--surface2)}
.feat-num{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.14em;
  text-transform:uppercase;color:var(--text3);margin-bottom:16px}
.feat-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:8px}
.feat-body{font-size:13px;color:var(--text2);line-height:1.65;font-weight:300}
/* ── Download gate ── */
.dl-gate{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:36px 40px;margin-bottom:48px;display:grid;
  grid-template-columns:1fr auto;gap:40px;align-items:center}
.dl-eyebrow{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin-bottom:10px}
.dl-title{font-family:var(--serif);font-size:1.75rem;font-weight:400;
  color:var(--text);margin-bottom:10px;line-height:1.2}
.dl-sub{font-size:13px;color:var(--text2);line-height:1.7;max-width:46ch;font-weight:300}
.dl-badge{display:inline-flex;align-items:center;gap:6px;
  font-family:var(--mono);font-size:9px;font-weight:400;letter-spacing:.1em;text-transform:uppercase;
  color:var(--green);background:var(--green-dim);border:1px solid rgba(52,211,153,.2);
  border-radius:20px;padding:5px 14px;margin-top:14px}
.dl-note{font-family:var(--mono);font-size:10px;font-weight:300;color:var(--text3);
  margin-top:10px;text-align:right;letter-spacing:.06em}
/* ── Request form ── */
.req-section{margin-bottom:80px}
.eyebrow{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin-bottom:10px}
.section-title{font-family:var(--serif);font-size:2rem;font-weight:400;
  color:var(--text);margin-bottom:10px;line-height:1.15}
.section-sub{font-size:13px;color:var(--text2);max-width:50ch;line-height:1.75;
  font-weight:300;margin-bottom:32px}
.form-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:32px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.field{display:flex;flex-direction:column;gap:7px}
.field.full{grid-column:1/-1}
.field label{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.12em;
  text-transform:uppercase;color:var(--text3)}
.fi{background:var(--bg);border:1px solid var(--border2);border-radius:var(--r-sm);
  color:var(--text);font-size:13px;font-family:var(--sans);
  padding:10px 13px;outline:none;width:100%;transition:border-color .15s}
.fi:focus{border-color:var(--accent)}
.fi::placeholder{color:var(--text3)}
textarea.fi{min-height:88px;resize:vertical}
.btn{padding:11px 24px;border-radius:var(--r);font-size:13px;font-weight:500;
  font-family:var(--sans);cursor:pointer;border:none;transition:opacity .15s,transform .1s}
.btn:hover{opacity:.88;transform:translateY(-1px)}
.btn-primary{background:var(--accent);color:#fff}
.btn-ghost{background:var(--surface2);border:1px solid var(--border2);color:var(--text)}
.form-actions{margin-top:22px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.form-note{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.08em;color:var(--text3)}
.form-msg{font-size:13px;margin-top:12px;min-height:18px}
.form-msg.ok{color:var(--green)}
.form-msg.err{color:var(--red)}
/* ── Auth ── */
.auth-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.auth-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:36px;width:100%;max-width:400px}
.auth-logo{display:flex;align-items:center;gap:10px;margin-bottom:32px}
.auth-title{font-family:var(--serif);font-size:1.5rem;font-weight:400;color:var(--text);margin-bottom:5px}
.auth-sub{font-family:var(--mono);font-size:10px;font-weight:300;letter-spacing:.08em;
  color:var(--text3);margin-bottom:24px}
.auth-fields{display:flex;flex-direction:column;gap:16px}
.auth-footer{margin-top:20px;font-family:var(--mono);font-size:10px;font-weight:300;
  letter-spacing:.06em;color:var(--text3);text-align:center}
.alert{padding:10px 14px;border-radius:var(--r-sm);font-size:13px;margin-bottom:16px}
.alert-err{background:var(--red-dim);border:1px solid rgba(248,113,113,.2);color:var(--red)}
.alert-ok{background:var(--green-dim);border:1px solid rgba(52,211,153,.2);color:var(--green)}
/* ── Admin ── */
.admin-bar{background:var(--surface);border-bottom:1px solid var(--border);
  padding:14px 28px;display:flex;align-items:center;justify-content:space-between;margin-bottom:32px}
table{width:100%;border-collapse:collapse;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r);overflow:hidden;font-size:12px}
th{background:var(--surface2);padding:10px 14px;text-align:left;
  font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--text3);border-bottom:1px solid var(--border)}
td{padding:11px 14px;border-bottom:1px solid var(--border);color:var(--text2)}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--surface2)}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;
  font-family:var(--mono);font-size:9px;font-weight:500;letter-spacing:.06em}
.badge-pending{background:rgba(251,191,36,.1);color:var(--amber);border:1px solid rgba(251,191,36,.2)}
.badge-approved{background:var(--green-dim);color:var(--green);border:1px solid rgba(52,211,153,.2)}
.badge-rejected{background:var(--red-dim);color:var(--red);border:1px solid rgba(248,113,113,.2)}
.btn-sm{padding:5px 12px;font-size:11px;font-weight:600;border:none;border-radius:4px;cursor:pointer;font-family:var(--sans)}
.btn-approve{background:var(--green-dim);color:var(--green)}
.btn-reject{background:var(--red-dim);color:var(--red)}
.btn-copy{background:var(--surface2);color:var(--accent);border:1px solid var(--border2)}
.settings-row{display:flex;gap:10px;align-items:center;margin-bottom:12px}
.settings-input{flex:1;background:var(--bg);border:1px solid var(--border2);border-radius:var(--r-sm);
  color:var(--text);font-size:13px;padding:8px 12px;outline:none}
/* ── Download portal ── */
.dl-page{max-width:620px;margin:0 auto;padding:64px 28px}
.dl-page-title{font-family:var(--serif);font-size:2.2rem;font-weight:400;color:var(--text);margin-bottom:6px}
.dl-page-sub{font-family:var(--mono);font-size:10px;font-weight:300;letter-spacing:.08em;
  color:var(--text3);margin-bottom:40px}
.key-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:28px 32px;margin-bottom:28px}
.key-label{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.14em;
  text-transform:uppercase;color:var(--text3);margin-bottom:10px}
.key-val{font-family:var(--mono);font-size:1.1rem;font-weight:500;color:var(--accent);
  letter-spacing:.06em;word-break:break-all}
.dl-btn{display:inline-flex;align-items:center;gap:10px;background:var(--accent);color:#fff;
  font-weight:500;font-size:14px;font-family:var(--sans);
  padding:14px 28px;border-radius:var(--r);text-decoration:none;transition:opacity .15s}
.dl-btn:hover{opacity:.85}
/* ── Footer ── */
footer{border-top:1px solid var(--border);padding:24px 0;margin-top:72px}
.footer-inner{max-width:880px;margin:0 auto;padding:0 28px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.footer-logo{display:flex;align-items:center;gap:8px}
.footer-word{font-family:var(--mono);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--text3)}
.footer-tagline{font-family:var(--mono);font-size:9px;font-weight:300;letter-spacing:.1em;
  text-transform:uppercase;color:var(--text3)}
.footer-link{font-family:var(--mono);font-size:9px;letter-spacing:.08em;color:var(--text3)}
/* ── Responsive ── */
@media(max-width:640px){
  .features{grid-template-columns:1fr}
  .form-grid{grid-template-columns:1fr}
  .dl-gate{grid-template-columns:1fr}
  .stats{flex-direction:column}
  .stat{border-right:none;border-bottom:1px solid var(--border);padding:20px 28px}
  .stat:last-child{border-bottom:none}
  .nav-links .nav-link{display:none}
}
"""

def _logo_html(size=20):
    s2 = round(size * .70)
    return (f'<div class="logo-mark">'
            f'<div class="bar bar1" style="height:{size}px;width:5px"></div>'
            f'<div class="bar bar2" style="height:{s2}px;width:5px"></div>'
            f'</div>')

def _page(title, body, active_user=None):
    if active_user:
        nav_right = '<a href="/download" class="nav-cta">My Portal</a>'
    else:
        nav_right = ('<a href="/login" class="nav-link">Sign in</a>'
                     '<a href="#request-access" class="nav-cta">Request Access</a>')
    footer = '''<footer><div class="footer-inner">
  <div class="footer-logo">''' + _logo_html(14) + '''
    <span class="footer-word">PILAR</span>
    <span class="footer-tagline" style="margin-left:16px">Anticipate &middot; Master &middot; Perform</span>
  </div>
  <div style="display:flex;gap:24px">
    <a href="mailto:contact@trypilar.com" class="footer-link">Contact</a>
    <span class="footer-link">&copy; 2026 PILAR</span>
  </div>
</div></footer>'''
    return render_template_string(f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#08090c">
<title>{title} — PILAR</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="{_FONTS}" rel="stylesheet">
<style>{_CSS}</style>
</head><body>
<nav><div class="nav-inner">
  <a href="/" class="nav-logo">{_logo_html()} <span class="logo-word">PILAR</span></a>
  <div class="nav-links">{nav_right}</div>
</div></nav>
{body}
{footer}
</body></html>""")


# ── Landing page ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    uid = session.get('user_id')
    active_user = None
    if uid:
        u = db.session.get(User, uid)
        if u and not u.license_revoked:
            active_user = u

    dl_section = ''
    if active_user:
        dl_section = f'''
<div class="dl-gate">
  <div>
    <div class="dl-eyebrow">Your portal</div>
    <div class="dl-title">Welcome back, {active_user.name.split()[0] if active_user.name else active_user.email.split("@")[0]}.</div>
    <div class="dl-sub">Your account is active and certified. Go to your portal to download PILAR and find your license key.</div>
    <div class="dl-badge">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
      Account certified
    </div>
  </div>
  <div style="text-align:right">
    <a href="/download" class="btn btn-primary" style="display:inline-block;padding:14px 28px;font-size:15px">Open my portal</a>
    <div class="dl-note">PILAR {APP_VERSION}</div>
  </div>
</div>'''
    else:
        dl_section = '''
<div class="dl-gate">
  <div>
    <div class="dl-eyebrow">Early access</div>
    <div class="dl-title">Get PILAR Beta.</div>
    <div class="dl-sub">Download access is reserved for certified accounts. Request access below — we review every application and respond within 48 hours.</div>
  </div>
  <div style="text-align:right">
    <a href="#request-access" class="btn btn-primary" style="display:inline-block;padding:14px 28px;font-size:15px">Request Access</a>
    <div class="dl-note">Already approved? <a href="/login">Sign in</a></div>
  </div>
</div>'''

    body = f'''
<section class="hero">
  <div class="container">
    <div class="hero-chip">Beta Program</div>
    <h1 class="hero-title">Predict failures<br>before they happen.</h1>
    <p class="hero-sub">PILAR is an AI-powered predictive maintenance platform for any industrial machine — pumps, compressors, motors, conveyors, robots.</p>
    <a href="#request-access" class="btn btn-primary" style="font-size:15px;padding:14px 32px">Request Beta Access</a>
  </div>
</section>

<div class="container">
  <div class="stats">
    <div class="stat"><div class="stat-val">100%</div><div class="stat-lbl">Recall</div></div>
    <div class="stat"><div class="stat-val">99.9%</div><div class="stat-lbl">Precision</div></div>
    <div class="stat"><div class="stat-val">5 h</div><div class="stat-lbl">Early warning</div></div>
    <div class="stat"><div class="stat-val">Any</div><div class="stat-lbl">Machine type</div></div>
  </div>

  {dl_section}

  <div class="features">
    <div class="feat">
      <div class="feat-num">01 — Risk score</div>
      <div class="feat-title">Real-time risk score</div>
      <div class="feat-body">0–100% failure probability updated with every sensor reading. Clear thresholds, no guessing.</div>
    </div>
    <div class="feat">
      <div class="feat-num">02 — Prognosis</div>
      <div class="feat-title">Remaining useful life</div>
      <div class="feat-body">Hours-to-failure estimate trained on NASA C-MAPSS data and scaled to your machine's MTBF.</div>
    </div>
    <div class="feat">
      <div class="feat-num">03 — Diagnosis</div>
      <div class="feat-title">5 failure zones</div>
      <div class="feat-body">Cavitation, bearing wear, seal failure, impeller erosion, motor fault — each diagnosed independently.</div>
    </div>
    <div class="feat">
      <div class="feat-num">04 — Deployment</div>
      <div class="feat-title">Desktop app</div>
      <div class="feat-body">Runs locally on Windows. No cloud dependency. Your sensor data never leaves your machine.</div>
    </div>
    <div class="feat">
      <div class="feat-num">05 — Collaboration</div>
      <div class="feat-title">Team desk</div>
      <div class="feat-body">Share machines and results with colleagues. Role-based access — owner, analyst, viewer.</div>
    </div>
    <div class="feat">
      <div class="feat-num">06 — Integration</div>
      <div class="feat-title">CSV or live feed</div>
      <div class="feat-body">Drop a CSV export from any historian, or connect a Modbus adapter for live polling. No code required.</div>
    </div>
  </div>

  <section class="req-section" id="request-access">
    <div class="eyebrow">Beta access</div>
    <div class="section-title">Apply for early access.</div>
    <div class="section-sub">We onboard new sites progressively. Tell us about your machines and we'll get back to you within 48 hours.</div>
    <div class="form-card">
      <form id="req-form">
        <div class="form-grid">
          <div class="field">
            <label>Full name *</label>
            <input class="fi" name="name" type="text" required placeholder="Your name">
          </div>
          <div class="field">
            <label>Work email *</label>
            <input class="fi" name="email" type="email" required placeholder="you@company.com">
          </div>
          <div class="field">
            <label>Company *</label>
            <input class="fi" name="company" type="text" required placeholder="Your company">
          </div>
          <div class="field">
            <label>Role</label>
            <input class="fi" name="role" type="text" placeholder="Maintenance manager, plant lead…">
          </div>
          <div class="field full">
            <label>What do you want to monitor?</label>
            <textarea class="fi" name="use_case" placeholder="Tell us about the machines, site, or pilot scope"></textarea>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit" id="req-btn">Request Access</button>
          <div class="form-note">No commitment. We respond within 48 hours.</div>
        </div>
        <div class="form-msg" id="req-msg"></div>
      </form>
    </div>
  </section>
</div>

<script>
document.getElementById('req-form').addEventListener('submit', async function(e) {{
  e.preventDefault();
  var btn = document.getElementById('req-btn');
  var msg = document.getElementById('req-msg');
  btn.disabled = true; btn.textContent = 'Sending…';
  var fd = new FormData(this);
  try {{
    var r = await fetch('/api/request-access', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        name: fd.get('name'), email: fd.get('email'),
        company: fd.get('company'), role: fd.get('role'), use_case: fd.get('use_case')
      }})
    }});
    var j = await r.json();
    if (r.ok) {{
      msg.className = 'form-msg ok';
      msg.textContent = j.message || 'Request received. We will be in touch.';
      this.reset();
    }} else {{
      msg.className = 'form-msg err';
      msg.textContent = j.error || 'Something went wrong. Try again.';
    }}
  }} catch(_) {{
    msg.className = 'form-msg err'; msg.textContent = 'Network error. Please try again.';
  }} finally {{
    btn.disabled = false; btn.textContent = 'Request Access';
  }}
}});
</script>'''
    return _page('Predictive Maintenance', body, active_user)


# ── API: request access ───────────────────────────────────────────────────────
@app.route('/api/request-access', methods=['POST'])
def api_request_access():
    d = request.get_json(silent=True) or {}
    email = (d.get('email') or '').strip().lower()
    name  = (d.get('name')  or '').strip()[:200]
    if not email or '@' not in email:
        return jsonify({'error': 'Valid email required.'}), 400
    if AccessRequest.query.filter_by(email=email).first():
        return jsonify({'message': 'A request for this email already exists. We will be in touch.'}), 200
    req = AccessRequest(
        email    = email,
        name     = name,
        company  = (d.get('company')  or '').strip()[:200],
        role     = (d.get('role')     or '').strip()[:200],
        use_case = (d.get('use_case') or '').strip()[:2000],
    )
    db.session.add(req)
    db.session.commit()
    # Notify admin
    if NOTIFY_EMAIL:
        _send_email(NOTIFY_EMAIL, f'PILAR Beta — New access request: {name}',
            f'Name: {name}\nEmail: {email}\nCompany: {d.get("company","")}\n'
            f'Role: {d.get("role","")}\n\nUse case:\n{d.get("use_case","")}\n\n'
            f'Approve at: {BASE_URL}/{ADMIN_PATH}')
    return jsonify({'message': 'Request received. We review every application and respond within 48 hours.'}), 200


# ── Admin routes (secret path: /{ADMIN_PATH}) ────────────────────────────────
@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    error = ''
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin.admin_panel'))
        error = 'Wrong password.'
    body = f'''
<div class="auth-wrap"><div class="auth-card">
  <div class="auth-logo">{_logo_html()} <span style="font-weight:700">PILAR Admin</span></div>
  <div class="auth-title">Admin access</div>
  {"<div class='alert alert-err'>" + error + "</div>" if error else ""}
  <form method="POST" class="auth-fields">
    <div class="field"><label>Password</label>
      <input class="fi" name="password" type="password" autofocus></div>
    <button class="btn btn-primary" type="submit" style="width:100%">Sign in</button>
  </form>
</div></div>'''
    return _page('Admin', body)


@admin_bp.route('/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin.admin_login'))


@admin_bp.route('/')
@admin_required
def admin_panel():
    reqs  = AccessRequest.query.order_by(AccessRequest.created_at.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
    dl_url = DOWNLOAD_URL

    rows = ''
    for r in reqs:
        badge = f'<span class="badge badge-{r.status}">{r.status}</span>'
        approve_url = url_for('admin.admin_approve', req_id=r.id)
        reject_url  = url_for('admin.admin_reject',  req_id=r.id)
        approve_btn = (
            f'<form method="POST" action="{approve_url}" style="display:inline">'
            f'<button class="btn-sm btn-approve" type="submit">Approve</button></form> '
            if r.status == 'pending' else ''
        )
        reject_btn = (
            f'<form method="POST" action="{reject_url}" style="display:inline">'
            f'<button class="btn-sm btn-reject" type="submit">Reject</button></form>'
            if r.status != 'rejected' else ''
        )
        link_cell = ''
        if r.signup_token:
            link = f'{BASE_URL}/signup/{r.signup_token}'
            link_cell = (f'<input id="lnk{r.id}" value="{link}" readonly style="width:180px;font-size:11px;'
                         f'background:var(--bg);border:1px solid var(--border2);border-radius:4px;'
                         f'color:var(--text2);padding:3px 6px">'
                         f' <button class="btn-sm btn-copy" onclick="navigator.clipboard.writeText'
                         f'(document.getElementById(\'lnk{r.id}\').value)">Copy</button>')
        rows += (f'<tr><td>{r.id}</td><td>{r.name or "—"}</td><td>{r.email}</td>'
                 f'<td>{r.company or "—"}</td><td>{badge}</td>'
                 f'<td>{approve_btn}{reject_btn}</td>'
                 f'<td>{link_cell}</td>'
                 f'<td style="font-size:11px;color:var(--text3)">{r.created_at.strftime("%Y-%m-%d") if r.created_at else ""}</td></tr>')

    user_rows = ''
    for u in users:
        revoked = u.license_revoked
        revoke_url = url_for('admin.admin_revoke', user_id=u.id)
        key_style = 'color:var(--red);text-decoration:line-through' if revoked else 'font-family:monospace;font-size:12px'
        rl = 'Reinstate' if revoked else 'Revoke'
        rc = 'btn-approve' if revoked else 'btn-reject'
        user_rows += (f'<tr><td>{u.id}</td><td>{u.email}</td><td>{u.name or "—"}</td>'
                      f'<td><span style="{key_style}">{u.license_key or "—"}</span></td>'
                      f'<td><form method="POST" action="{revoke_url}" style="display:inline">'
                      f'<button class="btn-sm {rc}" type="submit">{rl}</button></form></td>'
                      f'<td style="font-size:11px;color:var(--text3)">{u.created_at.strftime("%Y-%m-%d") if u.created_at else ""}</td></tr>')

    logout_url   = url_for('admin.admin_logout')
    settings_url = url_for('admin.admin_settings')
    body = f'''
<div class="admin-bar">
  <div style="display:flex;align-items:center;gap:10px">{_logo_html(16)} <span style="font-family:var(--mono);font-size:11px;font-weight:500;letter-spacing:.14em;text-transform:uppercase">PILAR Admin</span></div>
  <div style="display:flex;gap:12px;align-items:center">
    <div style="font-family:var(--mono);font-size:10px;color:var(--text3)">{len(reqs)} requests · {len(users)} users</div>
    <a href="{logout_url}" style="font-family:var(--mono);font-size:10px;color:var(--text3)">Sign out</a>
  </div>
</div>
<div class="container" style="padding-bottom:48px">
  <!-- Settings -->
  <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:20px 24px;margin-bottom:28px">
    <div style="font-family:var(--mono);font-size:9px;font-weight:400;text-transform:uppercase;letter-spacing:.12em;color:var(--text3);margin-bottom:12px">Download URL</div>
    <div class="settings-row">
      <input class="settings-input" id="s-dl" value="{dl_url}" placeholder="https://github.com/.../releases/...">
      <button class="btn-sm btn-copy" onclick="saveDl()">Save</button>
    </div>
    <div style="font-size:11px;color:var(--text3)" id="dl-msg"></div>
  </div>

  <!-- Requests -->
  <div style="font-family:var(--mono);font-size:9px;font-weight:400;text-transform:uppercase;letter-spacing:.12em;color:var(--text3);margin-bottom:12px">Access Requests</div>
  <div style="overflow-x:auto;margin-bottom:32px">
  <table>
    <thead><tr><th>#</th><th>Name</th><th>Email</th><th>Company</th><th>Status</th><th>Actions</th><th>Signup link</th><th>Date</th></tr></thead>
    <tbody>{rows or "<tr><td colspan=8 style='text-align:center;color:var(--text3);padding:24px'>No requests yet</td></tr>"}</tbody>
  </table></div>

  <!-- Users -->
  <div style="font-family:var(--mono);font-size:9px;font-weight:400;text-transform:uppercase;letter-spacing:.12em;color:var(--text3);margin-bottom:12px">Certified Users</div>
  <div style="overflow-x:auto">
  <table>
    <thead><tr><th>#</th><th>Email</th><th>Name</th><th>License key</th><th>Access</th><th>Since</th></tr></thead>
    <tbody>{user_rows or "<tr><td colspan=6 style='text-align:center;color:var(--text3);padding:24px'>No users yet</td></tr>"}</tbody>
  </table></div>
</div>
<script>
async function saveDl() {{
  var v = document.getElementById('s-dl').value;
  var r = await fetch('{settings_url}', {{method:'POST',
    headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{download_url: v}})}});
  var d = await r.json();
  document.getElementById('dl-msg').textContent = d.ok ? 'Saved.' : 'Error.';
}}
</script>'''
    return _page('Admin', body)


@admin_bp.route('/approve/<int:req_id>', methods=['POST'])
@admin_required
def admin_approve(req_id):
    r = db.session.get(AccessRequest, req_id)
    if not r: abort(404)
    token = secrets.token_urlsafe(32)
    r.status = 'approved'
    r.signup_token = token
    r.approved_at  = datetime.now(timezone.utc)
    db.session.commit()
    signup_url = f'{BASE_URL}/signup/{token}'
    _send_email(r.email, 'Your PILAR Beta access is approved',
        f'Hi {r.name or "there"},\n\n'
        f'Your request to access PILAR Beta has been approved.\n\n'
        f'Create your account here (link expires once used):\n{signup_url}\n\n'
        f'The PILAR team')
    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/reject/<int:req_id>', methods=['POST'])
@admin_required
def admin_reject(req_id):
    r = db.session.get(AccessRequest, req_id)
    if not r: abort(404)
    r.status = 'rejected'
    db.session.commit()
    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/revoke/<int:user_id>', methods=['POST'])
@admin_required
def admin_revoke(user_id):
    u = db.session.get(User, user_id)
    if not u: abort(404)
    u.license_revoked = not u.license_revoked
    db.session.commit()
    return redirect(url_for('admin.admin_panel'))


@admin_bp.route('/api/settings', methods=['POST'])
@admin_required
def admin_settings():
    global DOWNLOAD_URL
    d = request.get_json(silent=True) or {}
    if 'download_url' in d:
        DOWNLOAD_URL = d['download_url'].strip()
        cfg = os.path.join(os.path.dirname(__file__), 'settings.json')
        try:
            with open(cfg, 'w') as f:
                json.dump({'download_url': DOWNLOAD_URL}, f)
        except Exception:
            pass
    return jsonify({'ok': True})


app.register_blueprint(admin_bp, url_prefix=f'/{ADMIN_PATH}')


# ── Signup (approved users only) ──────────────────────────────────────────────
@app.route('/signup/<token>', methods=['GET', 'POST'])
def signup(token):
    req = AccessRequest.query.filter_by(signup_token=token, status='approved').first()
    if not req:
        body = '<div class="auth-wrap"><div class="auth-card"><div class="auth-title">Link invalid or expired.</div><p style="color:var(--text2);margin-top:8px;font-size:14px">This signup link has already been used or does not exist. Contact us if you need a new one.</p></div></div>'
        return _page('Invalid link', body), 404

    error = ''
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        pw   = request.form.get('password', '')
        pw2  = request.form.get('password2', '')
        if not name:
            error = 'Name is required.'
        elif len(pw) < 8:
            error = 'Password must be at least 8 characters.'
        elif pw != pw2:
            error = 'Passwords do not match.'
        else:
            existing = User.query.filter_by(email=req.email).first()
            if existing:
                error = 'An account with this email already exists. Please sign in.'
            else:
                key = _gen_license()
                u = User(email=req.email, name=name,
                         company=req.company or '',
                         pw_hash=_hash(pw), license_key=key,
                         request_id=req.id)
                db.session.add(u)
                # Invalidate the token so it can't be reused
                req.signup_token = None
                db.session.commit()
                session['user_id'] = u.id
                session.permanent = True
                return redirect('/download?welcome=1')

    body = f'''
<div class="auth-wrap"><div class="auth-card">
  <div class="auth-logo">{_logo_html()} <span style="font-weight:700">PILAR Beta</span></div>
  <div class="auth-title">Create your account</div>
  <div class="auth-sub">You've been approved. Set up your account to download PILAR.</div>
  {"<div class='alert alert-err'>" + error + "</div>" if error else ""}
  <form method="POST" class="auth-fields">
    <div class="field"><label>Email</label>
      <input class="fi" value="{req.email}" disabled></div>
    <div class="field"><label>Full name *</label>
      <input class="fi" name="name" type="text" required value="{req.name or ''}" autofocus></div>
    <div class="field"><label>Password *</label>
      <input class="fi" name="password" type="password" required placeholder="8+ characters"></div>
    <div class="field"><label>Confirm password *</label>
      <input class="fi" name="password2" type="password" required></div>
    <button class="btn btn-primary" type="submit" style="width:100%;margin-top:4px">Create account & download</button>
  </form>
</div></div>'''
    return _page('Create account', body)


# ── Login / logout ────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    next_url = request.args.get('next', '/download')
    error = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        u = User.query.filter_by(email=email).first()
        if u and u.pw_hash == _hash(pw):
            if u.license_revoked:
                error = 'Your access has been revoked. Contact support.'
            else:
                session['user_id'] = u.id
                session.permanent = True
                return redirect(next_url)
        else:
            error = 'Invalid email or password.'

    body = f'''
<div class="auth-wrap"><div class="auth-card">
  <div class="auth-logo">{_logo_html()} <span style="font-weight:700">PILAR Beta</span></div>
  <div class="auth-title">Sign in</div>
  <div class="auth-sub">Access your PILAR Beta portal.</div>
  {"<div class='alert alert-err'>" + error + "</div>" if error else ""}
  <form method="POST" class="auth-fields">
    <div class="field"><label>Email</label>
      <input class="fi" name="email" type="email" required autofocus></div>
    <div class="field"><label>Password</label>
      <input class="fi" name="password" type="password" required></div>
    <button class="btn btn-primary" type="submit" style="width:100%;margin-top:4px">Sign in</button>
  </form>
  <div class="auth-footer">Don't have an account? <a href="/#request-access">Request access</a></div>
</div></div>'''
    return _page('Sign in', body)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ── Download page (certified users only) ─────────────────────────────────────
@app.route('/download')
@login_required
def download_page():
    u = db.session.get(User, session['user_id'])
    if not u:
        return redirect('/login')
    if u.license_revoked:
        body = '''<div class="auth-wrap"><div class="auth-card">
  <div style="text-align:center;padding:8px 0">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="1.5" style="margin-bottom:16px"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>
    <div class="auth-title">Access Revoked</div>
    <p style="color:var(--text2);font-size:14px;margin-top:8px;line-height:1.6">Your download access has been revoked by an administrator. Contact support if you believe this is an error.</p>
    <a href="/logout" style="display:block;margin-top:20px;font-size:13px;color:var(--text3)">Sign out</a>
  </div></div></div>'''
        return _page('Access Revoked', body), 403

    welcome = request.args.get('welcome')
    first_name = (u.name or u.email).split()[0]

    body = f'''
<div class="dl-page">
  {"<div class='alert alert-ok' style='margin-bottom:24px'>Welcome to PILAR Beta, " + first_name + "! Your account is ready.</div>" if welcome else ""}
  <div class="dl-page-title">Hello, {first_name}.</div>
  <div class="dl-page-sub">Your account is certified and ready. Download PILAR and activate it with your license key below.</div>

  <div class="key-card">
    <div class="key-label">Your License Key</div>
    <div class="key-val" id="lkey">{u.license_key or "—"}</div>
    <div style="margin-top:12px">
      <button class="btn btn-ghost" style="font-size:13px;padding:8px 18px"
        onclick="navigator.clipboard.writeText(document.getElementById('lkey').textContent);this.textContent='Copied!'">
        Copy key
      </button>
    </div>
    <div style="font-size:12px;color:var(--text3);margin-top:10px">Enter this key the first time you launch PILAR to activate your account.</div>
  </div>

  <a href="{DOWNLOAD_URL}" class="dl-btn">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    Download PILAR {APP_VERSION}
  </a>
  <div style="font-size:12px;color:var(--text3);margin-top:10px">Windows 10/11 · Requires Edge WebView2 (included with Windows 11)</div>

  <div style="margin-top:40px;padding-top:24px;border-top:1px solid var(--border)">
    <div style="font-size:12px;color:var(--text3)">Signed in as <strong style="color:var(--text2)">{u.email}</strong> · <a href="/logout">Sign out</a></div>
  </div>
</div>'''
    return _page('My Portal', body, active_user=u)


# ── Boot ──────────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    # Load saved settings
    cfg = os.path.join(os.path.dirname(__file__), 'settings.json')
    if os.path.exists(cfg):
        try:
            with open(cfg) as f:
                saved = json.load(f)
            if 'download_url' in saved:
                DOWNLOAD_URL = saved['download_url']
        except Exception:
            pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    print(f'PILAR Beta portal -> http://localhost:{port}')
    print(f'Admin panel       -> http://localhost:{port}/{ADMIN_PATH}/')
    app.run(host='0.0.0.0', port=port, debug=False)
