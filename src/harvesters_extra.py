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
    try:
        body = json.dumps({"model": model,
                           "messages": [{"role": "user", "content": "Reply exactly: PONG"}],
                           "max_tokens": 16}).encode()
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        return {"ok": True, "usage": d.get("usage")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:120]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
