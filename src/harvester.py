"""Harvester: buat akun di gateway Gonka, verifikasi, ambil API key, test.

Alur generik (per gateway):
  1. Buat inbox temp-mail (session disimpan per-situs).
  2. Buka halaman signup, isi form, submit (tangkap API).
  3. Verifikasi: OTP 6-digit atau magic-link dari inbox.
  4. Buat API key (tombol/endpoint), tangkap key penuh dari response.
  5. Test chat ke base_url; simpan ke accounts.txt (email:pw:key:baseurl).

Karena halaman memakai React, pengetikan dilakukan via Playwright (real typing),
bukan set value manual.
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional

from rich.console import Console

from .config import DATA_DIR
from .gateways import get as get_gw, all_names
from .inboxstore import save as save_inbox, get as get_inbox
from .tempmail import TempikClient

C = Console()

CAPTURE_JS = """() => {
  if (window.__gnk_hooked) return 'already';
  window.__gnk_hooked = true;
  window.__gnk_cap = [];
  const of = window.fetch;
  window.fetch = async function(...a){
    const r=a[0], o=a[1]||{};
    let u=(typeof r==='string')?r:r.url;
    let b=o.body;
    let resp=await of.apply(this,a);
    let t=''; try{ t=await resp.clone().text(); }catch(e){}
    if(!/google|gtag|analytics|posthog|vercel|yandex|hotjar|sentry|facebook/.test(u))
      window.__gnk_cap.push({url:u, method:o.method||'GET', body:String(b||'').slice(0,600), status:resp.status, resp:t.slice(0,1200)});
    return resp;
  };
  return 'ok';
}"""


def _new_inbox(site: str, password: str) -> Dict[str, str]:
    c = TempikClient()
    addr = c.create_inbox()
    save_inbox(site, addr, c.session_id, password)
    return {"email": addr, "session_id": c.session_id, "password": password}


def _read_otp(site: str, timeout: int = 150) -> Optional[str]:
    info = get_inbox(site)
    if not info:
        return None
    c = TempikClient(); c.session_id = info["session_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            msgs = c.get_messages(info["email"])
        except Exception:
            msgs = []
        for m in (msgs or []):
            body = m.get("body", "") or m.get("text", "")
            plain = re.sub(r"<[^>]+>", " ", body)
            codes = re.findall(r"\b(\d{6})\b", plain)
            if codes:
                return codes[0]
        time.sleep(5)
    return None


def _read_link(site: str, keywords=("verify", "confirm", "token", "activate", "auth/action"),
               timeout: int = 150) -> Optional[str]:
    info = get_inbox(site)
    if not info:
        return None
    c = TempikClient(); c.session_id = info["session_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            msgs = c.get_messages(info["email"])
        except Exception:
            msgs = []
        for m in (msgs or []):
            body = m.get("body", "") or m.get("text", "")
            for u in re.findall(r"https?://[^\s\"'<>]+", body):
                if any(k in u.lower() for k in keywords):
                    return u.replace("&amp;", "&")
        time.sleep(5)
    return None


async def harvest(site: str, headless: bool = True, password: str = "Gonka#2026xY",
                  timeout_verify: int = 150) -> Dict[str, Any]:
    """Jalankan alur harvest lengkap untuk satu gateway. Return dict hasil."""
    from playwright.async_api import async_playwright
    from .stealth import launch_stealth_browser, create_stealth_context

    gw = get_gw(site)
    if not gw:
        return {"site": site, "ok": False, "error": "gateway tidak dikenal"}
    if gw.get("captcha") in ("recaptcha",):
        return {"site": site, "ok": False, "error": f"captcha {gw['captcha']} (butuh solver)"}

    result = {"site": site, "ok": False, "email": None, "key": None, "base_url": gw.get("base_url")}

    # 1. inbox
    inbox = _new_inbox(site, password)
    result["email"] = inbox["email"]
    C.print(f"[cyan]{site}[/] inbox: {inbox['email']}")

    async with async_playwright() as p:
        browser = await launch_stealth_browser(p, headless=headless)
        ctx = await create_stealth_context(browser)
        page = await ctx.new_page()
        try:
            await page.goto(gw["signup_url"], wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3500)
            await page.evaluate(CAPTURE_JS)

            # isi form: email + semua password
            email_sel = "input[type=email]"
            try:
                await page.fill(email_sel, inbox["email"])
            except Exception:
                # fallback: input pertama
                await page.fill("input", inbox["email"])
            for sel in ["input[type=password]"]:
                els = await page.query_selector_all(sel)
                for e in els:
                    await e.fill(password)
            await page.wait_for_timeout(800)

            # submit
            clicked = False
            for txt in ["create account", "sign up", "register", "continue", "create"]:
                b = await page.query_selector(f"button:has-text('{txt}')")
                if b:
                    await b.click(); clicked = True; break
            if not clicked:
                await page.keyboard.press("Enter")
            await page.wait_for_timeout(6000)

            # 3. verifikasi
            verify = gw.get("verify")
            if verify == "otp6":
                otp = await asyncio.to_thread(_read_otp, site, timeout_verify)
                if otp:
                    boxes = await page.query_selector_all("input[maxlength='1']")
                    if boxes:
                        for i, ch in enumerate(otp):
                            if i < len(boxes):
                                await boxes[i].click()
                                await page.keyboard.type(ch)
                                await page.wait_for_timeout(200)
                    else:
                        inp = await page.query_selector("input[type=text],input[type=number]")
                        if inp:
                            await inp.fill(otp)
                    await page.wait_for_timeout(4000)
                    result["otp"] = otp
            elif verify in ("magic-link",):
                link = await asyncio.to_thread(_read_link, site)
                if link:
                    await page.goto(link, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(4000)
                    result["verify_link"] = link[:80]

            await page.wait_for_timeout(3000)
            result["final_url"] = page.url
            caps = await page.evaluate("() => JSON.stringify(window.__gnk_cap||[])")

            # 4. buat API key
            key = None
            try:
                kb = await page.query_selector("button:has-text('Create key'), button:has-text('Create API Key'), button:has-text('New Key')")
                if kb:
                    await kb.click()
                    await page.wait_for_timeout(2500)
                    # isi nama bila ada
                    nm = await page.query_selector("input[placeholder*='App'],input[placeholder*='Production'],input[placeholder*='name']")
                    if nm:
                        try:
                            await nm.fill("gonka-suite")
                        except Exception:
                            pass
                    cb = await page.query_selector("button:has-text('Create')")
                    if cb:
                        await cb.click()
                        await page.wait_for_timeout(4000)
                caps = await page.evaluate("() => JSON.stringify(window.__gnk_cap||[])")
                key = _extract_key(caps)
            except Exception as e:
                result["key_error"] = str(e)[:100]

            if key:
                result["key"] = key
                result["ok"] = True
                _save_account(result)
        except Exception as e:
            result["error"] = str(e)[:150]
        finally:
            try:
                await ctx.close(); await browser.close()
            except Exception:
                pass
    return result


def _extract_key(caps_json: str) -> Optional[str]:
    """Ambil API key penuh dari captured responses (field key/rawKey/api_key)."""
    try:
        caps = json.loads(caps_json)
    except Exception:
        return None
    for c in caps:
        body = c.get("resp", "")
        try:
            j = json.loads(body)
        except Exception:
            continue
        for field in ("key", "rawKey", "api_key", "apiKey", "token"):
            v = j.get(field)
            if isinstance(v, str) and len(v) >= 20 and re.match(r"^(sk-|gnk-|jg-|gsk_)", v):
                return v
    return None


def _save_account(result: Dict[str, Any]):
    line = f"{result['email']}:{get_inbox(result['site'])['password']}:{result['key']}:{result.get('base_url')}\n"
    (Path(DATA_DIR).parent / "accounts.txt").open("a").write(line)


def test_key(base_url: str, key: str, model: str = None, timeout: int = 90) -> Dict[str, Any]:
    import urllib.request, urllib.error
    out = {"base_url": base_url, "ok": False}
    try:
        req = urllib.request.Request(base_url.rstrip("/") + "/models",
                                     headers={"Authorization": f"Bearer {key}"})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        models = [m.get("id") for m in d.get("data", [])]
        out["models"] = models
        model = model or (models[0] if models else None)
    except Exception as e:
        out["models_error"] = str(e)[:100]
    if not model:
        return out
    try:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply exactly: PONG"}],
                           "max_tokens": 16}).encode()
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        out["ok"] = True
        out["model"] = model
        out["usage"] = d.get("usage")
    except urllib.error.HTTPError as e:
        out["chat_error"] = f"HTTP {e.code}: {e.read().decode()[:120]}"
    except Exception as e:
        out["chat_error"] = str(e)[:100]
    return out
