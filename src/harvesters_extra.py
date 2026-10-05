"""Harvester khusus per-gateway yang punya alur non-standar.

- dahl: username-only signup -> fingerprint + api_key -> allocate 100M -> key aktif
- gonka-api: POST /agent-signup -> akun + token otomatis (tanpa email)
"""
import json
import random
import string
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any

from rich.console import Console

C = Console()
ACCOUNTS = Path(__file__).resolve().parent.parent / "accounts.txt"


def _post(url, payload, headers=None, timeout=60):
    body = json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "User-Agent": "gonka-suite/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def _get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def _append_account(email, password, key, base):
    ACCOUNTS.open("a").write(f"{email}:{password}:{key}:{base}\n")


# ======================= DAHL =======================
DAHL_BASE = "https://inference.dahl.global/v1"
DAHL_HOST = "https://inference.dahl.global"


def harvest_dahl(username: str = None) -> Dict[str, Any]:
    """Signup dahl (username-only) -> fingerprint + key -> allocate 100M."""
    uname = username or ("gnk" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7)))
    out = {"site": "dahl", "ok": False, "username": uname}
    try:
        st, d = _post(f"{DAHL_HOST}/v1/auth/signup", {"username": uname})
    except urllib.error.HTTPError as e:
        out["error"] = f"signup HTTP {e.code}: {e.read().decode()[:120]}"
        return out
    except Exception as e:
        out["error"] = f"signup: {str(e)[:120]}"
        return out
    if st != 201:
        out["error"] = f"signup status {st}"
        return out

    fp = d.get("fingerprint")
    key0 = (d.get("api_key") or {}).get("token")
    out["fingerprint"] = fp
    # buat key baru + alokasi 100M (pool dari free grant)
    hdr = {"Authorization": f"Bearer {key0}"}
    try:
        # login pakai fingerprint utk dapat sesi (endpoint keys butuh bearer key; buat key baru)
        st2, k2 = _post(f"{DAHL_HOST}/v1/account/keys", {}, headers=hdr)
        newkey = (k2.get("key") or {}).get("token")
        kid = (k2.get("key") or {}).get("id")
        if newkey and kid:
            st3, alloc = _post(f"{DAHL_HOST}/v1/account/allocate",
                               {"amount": 100000000, "key_id": kid}, headers=hdr)
            active = (alloc.get("key") or {}).get("status")
            out["key"] = newkey
            out["allocated"] = (alloc.get("key") or {}).get("available_tokens")
            out["status"] = active
            out["ok"] = active == "active"
            _append_account(uname, fp, newkey, DAHL_BASE)
    except Exception as e:
        out["key_error"] = str(e)[:150]
        if key0:
            out["key"] = key0
    return out


# ======================= GONKA-API (agent-signup) =======================
GKA_SIGNUP = "https://hskyauefqcgbvgvxkluj.supabase.co/functions/v1/agent-signup"


def harvest_gonka_api(agent_name: str = "gonka-suite",
                      purpose: str = None) -> Dict[str, Any]:
    """POST /agent-signup -> akun + API token otomatis. Tanpa email/captcha."""
    purpose = purpose or ("Harvesting free-tier API keys for personal research "
                          "and testing of decentralized inference gateways.")
    out = {"site": "gonka-api", "ok": False}
    try:
        st, d = _post(GKA_SIGNUP, {"agent_name": agent_name, "purpose": purpose})
    except urllib.error.HTTPError as e:
        out["error"] = f"HTTP {e.code}: {e.read().decode()[:150]}"
        return out
    except Exception as e:
        out["error"] = str(e)[:150]
        return out
    acct = d.get("account", {})
    api = d.get("api", {})
    tok = api.get("access_token")
    base = api.get("base_url")
    out.update({
        "email": acct.get("email"),
        "key": tok,
        "base_url": base,
        "balance_usd": (d.get("balance") or {}).get("usd"),
        "ok": bool(tok),
    })
    if tok:
        _append_account(acct.get("email"), acct.get("user_password", ""), tok, base)
    return out


def test_chat(base_url: str, key: str, model: str = "MiniMaxAI/MiniMax-M2.7") -> Dict[str, Any]:
    # GonkaRouter dilindungi Cloudflare (error 1010 pada urllib polos) -> kirim
    # header browser lengkap agar lolos.
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
         "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
         "Accept": "application/json"}
    try:
        body = json.dumps({"model": model,
                           "messages": [{"role": "user", "content": "Reply exactly: PONG"}],
                           "max_tokens": 16}).encode()
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=h)
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        return {"ok": True, "usage": d.get("usage")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:120]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ======================= GONKAROUTER =======================
GR_HOST = "https://gonkarouter.io"
GR_API = "https://api.gonkarouter.io"
GR_BASE = "https://api.gonkarouter.io/v1"
_GR_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


async def harvest_gonkarouter(headless: bool = True, password: str = "n/a",
                              timeout_verify: int = 150) -> Dict[str, Any]:
    """Signup/login gonkarouter via email OTP (auto-create) -> reveal API key.

    Alur: inbox -> Sign In -> email -> Continue -> OTP 6-digit -> dashboard
    (balance 20 USDT) -> POST /api/keys/{id}/reveal (pakai cookie auth_token).
    """
    import asyncio
    from .inboxstore import save as save_inbox, get as get_inbox
    from .tempmail import TempikClient

    out = {"site": "gonkarouter", "ok": False, "base_url": GR_BASE}
    # 1. inbox
    tc = TempikClient()
    email = tc.create_inbox()
    save_inbox("gonkarouter", email, tc.session_id, password)
    out["email"] = email
    C.print(f"[cyan]gonkarouter[/] inbox: {email}")

    async def _read_otp(timeout):
        c = TempikClient(); c.session_id = tc.session_id
        import time as _t, re as _re
        t0 = _t.time()
        while _t.time() - t0 < timeout:
            try:
                for m in (c.get_messages(email) or []):
                    plain = _re.sub(r"<[^>]+>", " ", (m.get("body", "") or "") + " " + (m.get("subject", "") or ""))
                    codes = _re.findall(r"\b(\d{6})\b", plain)
                    if codes:
                        return codes[0]
            except Exception:
                pass
            await asyncio.sleep(5)
        return None

    from playwright.async_api import async_playwright
    from .stealth import launch_stealth_browser, create_stealth_context

    async with async_playwright() as p:
        browser = await launch_stealth_browser(p, headless=headless)
        ctx = await create_stealth_context(browser)
        page = await ctx.new_page()
        try:
            await page.goto(f"{GR_HOST}/dashboard", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3500)
            # klik Sign In (JS click: elemen nav bisa tak "visible" bagi Playwright)
            await page.evaluate("""() => {
                const b = [...document.querySelectorAll('button,a')].find(
                    x => /^sign in$/i.test((x.innerText||'').trim()));
                if (b) b.click();
            }""")
            await page.wait_for_timeout(2500)
            await page.fill("input[type=email]", email)
            await page.wait_for_timeout(600)
            await page.evaluate("""() => {
                const b = [...document.querySelectorAll('button')].find(
                    x => /^continue$/i.test((x.innerText||'').trim()));
                if (b) b.click();
            }""")
            await page.wait_for_timeout(4000)
            # OTP
            otp = await _read_otp(timeout_verify)
            out["otp"] = otp
            if otp:
                boxes = await page.query_selector_all("input[maxlength='1']")
                for i, ch in enumerate(otp):
                    if i < len(boxes):
                        await boxes[i].click(); await page.keyboard.type(ch)
                        await page.wait_for_timeout(150)
                await page.wait_for_timeout(5000)
            out["final_url"] = page.url
            # ambil auth_token dari cookie
            tok = await page.evaluate("""(() => { const m=document.cookie.match(/auth_token=([^;]+)/); return m?decodeURIComponent(m[1]):null; })()""")
            if not tok:
                out["error"] = "auth_token tidak ada (login gagal)"
                return out
            # list keys + reveal
            key = await page.evaluate("""(async (tok) => {
                const H = {'Authorization':'Bearer '+tok,'Accept':'application/json'};
                const r = await fetch('https://api.gonkarouter.io/api/keys', {headers:H});
                const j = await r.json();
                const id = j.items && j.items[0] && j.items[0].id;
                if (!id) return null;
                const r2 = await fetch('https://api.gonkarouter.io/api/keys/'+id+'/reveal', {method:'POST', headers:H});
                const j2 = await r2.json();
                return j2.key || null;
            })""", tok)
            if key:
                out["key"] = key; out["ok"] = True
                _append_account(email, password, key, GR_BASE)
        except Exception as e:
            out["error"] = str(e)[:150]
        finally:
            try:
                await ctx.close(); await browser.close()
            except Exception:
                pass
    return out


# ======================= FREE.AI =======================
FA_HOST = "https://free.ai"
FA_BASE = "https://api.free.ai/v1"


async def harvest_freeai(headless: bool = True, password: str = "",
                         timeout_verify: int = 150) -> Dict[str, Any]:
    """Signup free.ai (Django email+password) -> verifikasi kode 6-digit -> API key.

    Catatan teknis: field kode verifikasi (#verify-code) menolak input keyboard
    biasa; nilainya harus di-set via native value setter lalu form di-submit
    dengan requestSubmit(). API key penuh hanya dikembalikan saat create.
    """
    import asyncio
    from .inboxstore import save as save_inbox, get as get_inbox
    from .tempmail import TempikClient

    out = {"site": "freeai", "ok": False, "base_url": FA_BASE}
    tc = TempikClient()
    email = tc.create_inbox()
    save_inbox("freeai", email, tc.session_id, password)
    out["email"] = email
    C.print(f"[cyan]free.ai[/] inbox: {email}")

    def _read_code(timeout):
        c = TempikClient(); c.session_id = tc.session_id
        import time as _t, re as _re
        t0 = _t.time()
        while _t.time() - t0 < timeout:
            try:
                for m in (c.get_messages(email) or []):
                    plain = _re.sub(r"<[^>]+>", " ", (m.get("body", "") or "") + " " + (m.get("subject", "") or ""))
                    codes = _re.findall(r"\b(\d{6})\b", plain)
                    if codes:
                        return codes[-1]
            except Exception:
                pass
            _t.sleep(5)
        return None

    from playwright.async_api import async_playwright
    from .stealth import launch_stealth_browser, create_stealth_context

    async with async_playwright() as p:
        browser = await launch_stealth_browser(p, headless=headless)
        ctx = await create_stealth_context(browser)
        page = await ctx.new_page()
        try:
            await page.goto(f"{FA_HOST}/signup/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            await page.fill("#register-email", email)
            await page.wait_for_timeout(400)
            await page.fill("#register-password", password)
            await page.wait_for_timeout(400)
            await page.evaluate("""() => {
                const b = [...document.querySelectorAll('button')].find(x => /sign up free/i.test(x.innerText));
                if (b) b.click();
            }""")
            await page.wait_for_timeout(5000)
            out["after_signup_url"] = page.url
            # verifikasi kode 6-digit
            code = await asyncio.to_thread(_read_code, timeout_verify)
            out["code"] = code
            if code:
                # set nilai via native setter + submit (input keyboard ditolak)
                await page.evaluate("""(code) => {
                    const e = document.querySelector('#verify-code');
                    if (!e) return;
                    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    set.call(e, code);
                    e.dispatchEvent(new Event('input', {bubbles:true}));
                    const f = e.form;
                    if (f) { if (f.requestSubmit) f.requestSubmit(); else f.submit(); }
                }""", code)
                await page.wait_for_timeout(6000)
            out["final_url"] = page.url
            # generate API key via endpoint (key penuh hanya di response create)
            await page.goto(f"{FA_HOST}/account/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            key = await page.evaluate("""(async () => {
                const csrf = (document.cookie.match(/csrftoken=([^;]+)/)||[])[1];
                const r = await fetch('/api/v1/api-keys/', {method:'POST',
                    headers:{'X-CSRFToken':csrf, 'Content-Type':'application/json'},
                    credentials:'include', body: JSON.stringify({name:'gonka-suite'})});
                const j = await r.json();
                return j.key || null;
            })""")
            if key:
                out["key"] = key; out["ok"] = True
                _append_account(email, password, key, FA_BASE)
            else:
                out["error"] = "key tidak ter-generate (verifikasi mungkin gagal)"
        except Exception as e:
            out["error"] = str(e)[:150]
        finally:
            try:
                await ctx.close(); await browser.close()
            except Exception:
                pass
    return out
