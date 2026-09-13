"""The hosted central login/signup page — plain server-rendered HTML +
vanilla JS (no SPA build needed for two forms), styled to match the
ecosystem's brand gradient. This is the page every product redirects an
unauthenticated user to (mission-brief section 5's "Redirect to Central
Identity" step) and, if the user already has an active central session,
`/oauth/authorize` never even reaches it — SSO across products with no
password re-entry.

`next` is validated server-side before ever being embedded in the page:
only a same-path `/oauth/authorize?...` value is accepted, so this page
can never be turned into an open redirect by a crafted `?next=` query
(mission-brief section 24).
"""
from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

_STYLE = """
<style>
  :root{color-scheme:dark;}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:radial-gradient(circle at 20% 20%,rgba(59,130,246,.18),transparent 40%),
               radial-gradient(circle at 80% 30%,rgba(139,92,246,.16),transparent 45%),
               radial-gradient(circle at 50% 90%,rgba(34,211,238,.14),transparent 40%),#0b0f1a;
    font-family:'Sora',Inter,system-ui,sans-serif;color:#e2e8f0;}
  .card{width:360px;background:rgba(17,24,39,.72);border:1px solid rgba(255,255,255,.08);
    border-radius:20px;padding:32px;backdrop-filter:blur(16px);
    box-shadow:0 20px 60px -12px rgba(59,130,246,.35);}
  h1{font-size:20px;margin:0 0 4px;background:linear-gradient(135deg,#22D3EE,#3B82F6,#8B5CF6);
    -webkit-background-clip:text;background-clip:text;color:transparent;}
  p.sub{color:#94a3b8;font-size:13px;margin:0 0 24px;}
  label{display:block;font-size:12px;color:#94a3b8;margin:14px 0 6px;}
  input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;
    border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#e2e8f0;font-size:14px;}
  button{width:100%;margin-top:22px;padding:11px;border:none;border-radius:10px;font-weight:600;
    color:#0b0f1a;cursor:pointer;background:linear-gradient(135deg,#22D3EE,#3B82F6,#8B5CF6);}
  .err{color:#f87171;font-size:13px;margin-top:12px;min-height:16px;}
  .switch{margin-top:18px;font-size:13px;color:#94a3b8;text-align:center;}
  .switch a{color:#67e8f9;text-decoration:none;}
</style>
"""


def _safe_next(raw: str | None) -> str:
    if raw and raw.startswith("/oauth/authorize?"):
        return raw
    return "/"


@router.get("/login", response_class=HTMLResponse)
async def login_page(next: str | None = Query(default=None)) -> HTMLResponse:
    safe_next = _safe_next(next)
    # Two different embeddings of the SAME validated path need two different
    # escapings: inside an href's query string, `&`/`=`/`?` inside the value
    # must be percent-encoded or the browser reparses them as this page's
    # OWN query params (a real bug caught by a live browser run - see
    # docs/platform/SSO.md); inside the inline <script>, json.dumps produces
    # a safe JS string literal instead.
    href_next = quote(safe_next, safe="")
    js_next = json.dumps(safe_next)
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Sign in - Central Identity</title>{_STYLE}</head><body>
<div class="card">
  <h1>Central Identity</h1>
  <p class="sub">Sign in once. Use it everywhere in the ecosystem.</p>
  <form id="f">
    <label for="email">Email</label>
    <input id="email" type="email" required autocomplete="username">
    <label for="password">Password</label>
    <input id="password" type="password" required autocomplete="current-password">
    <button type="submit">Sign in</button>
    <div class="err" id="err"></div>
  </form>
  <div class="switch">No account? <a href="/signup?next={href_next}">Create one</a></div>
</div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const err = document.getElementById('err');
  err.textContent = '';
  const res = await fetch('/api/v1/auth/login', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}}, credentials: 'include',
    body: JSON.stringify({{
      email: document.getElementById('email').value,
      password: document.getElementById('password').value,
      remember_me: true,
    }}),
  }});
  if (res.ok) {{ window.location = {js_next}; }}
  else {{ const body = await res.json().catch(() => ({{}})); err.textContent = body.message || 'Sign-in failed.'; }}
}});
</script>
</body></html>""")


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(next: str | None = Query(default=None)) -> HTMLResponse:
    safe_next = _safe_next(next)
    href_next = quote(safe_next, safe="")
    js_next = json.dumps(safe_next)
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Create account - Central Identity</title>{_STYLE}</head><body>
<div class="card">
  <h1>Create your account</h1>
  <p class="sub">One identity. Every product in the ecosystem.</p>
  <form id="f">
    <label for="email">Email</label>
    <input id="email" type="email" required autocomplete="username">
    <label for="password">Password</label>
    <input id="password" type="password" required minlength="8" autocomplete="new-password">
    <button type="submit">Create account</button>
    <div class="err" id="err"></div>
  </form>
  <div class="switch">Already have an account? <a href="/login?next={href_next}">Sign in</a></div>
</div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const err = document.getElementById('err');
  err.textContent = '';
  const res = await fetch('/api/v1/auth/signup', {{
    method: 'POST', headers: {{'Content-Type':'application/json'}}, credentials: 'include',
    body: JSON.stringify({{
      email: document.getElementById('email').value,
      password: document.getElementById('password').value,
    }}),
  }});
  if (res.ok) {{ window.location = {js_next}; }}
  else {{ const body = await res.json().catch(() => ({{}})); err.textContent = body.message || 'Sign-up failed.'; }}
}});
</script>
</body></html>""")
