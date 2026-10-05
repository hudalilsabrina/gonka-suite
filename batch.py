#!/usr/bin/env python3
"""Batch harvester: buat N akun dari satu atau beberapa gateway.

Fitur:
- Multi-gateway dengan auto-fallback: kalau gateway aktif kena rate-limit,
  otomatis pindah ke gateway berikutnya yang masih sehat.
- Deteksi rate-limit dari pesan error -> cooldown gateway itu (tidak diulang
  sampai jendela cooldown lewat).
- Log tiap hasil ke data/batch_<site>.jsonl (append, tahan timeout) + agregasi.
- Verifikasi chat nyata untuk setiap key yang didapat.

Pakai:
  .venv/bin/python batch.py <site> <n> [--headed]        # satu gateway
  .venv/bin/python batch.py --auto <n>                   # fallback multi-gateway
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import harvesters_extra as hx
from src import harvester

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)

# Gateway yang bisa di-batch (terurut prioritas) untuk mode --auto.
AUTO_ORDER = ["gonkarouter", "gonka-proxy"]

# Sinyal rate-limit (lowercase) di pesan error -> gateway di-cooldown.
RATE_HINTS = ["too many", "rate limit", "rate_limit", "try again", "429",
              "slow down", "exceeded"]


async def _run(site, headless):
    if site == "gonkarouter":
        return await hx.harvest_gonkarouter(headless=headless)
    if site == "dahl":
        return hx.harvest_dahl()
    if site == "gonka-api":
        return hx.harvest_gonka_api()
    return await harvester.harvest(site, headless=headless)


def _log(site, idx, r, extra=None):
    rec = {"site": site, "idx": idx, "ts": int(time.time()),
           "ok": bool(r.get("ok")), "key_len": len(r.get("key") or ""),
           "email": r.get("email"), "error": (r.get("error") or "")[:150]}
    if extra:
        rec.update(extra)
    with (DATA / f"batch_{site}.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _is_rate_limited(r):
    msg = (r.get("error") or "").lower()
    return any(h in msg for h in RATE_HINTS)


async def run_one(site, idx, headless):
    try:
        r = await _run(site, headless)
    except Exception as e:
        r = {"ok": False, "error": str(e)[:150]}
    rec = _log(site, idx, r)
    if r.get("key") and r.get("base_url"):
        t = hx.test_chat(r["base_url"], r["key"])
        rec["chat_ok"] = bool(t.get("ok"))
        if not t.get("ok"):
            rec["chat_error"] = str(t.get("error"))[:120]
        _log(site, idx, r, {"verify": True, "chat_ok": rec["chat_ok"]})
    tag = "OK " if rec["ok"] else "FAIL"
    print(f"[{idx}] {tag} {rec.get('email')} {rec.get('error', '')}", flush=True)
    return rec


async def run_single(site, n, headless):
    ok = 0
    for i in range(1, n + 1):
        r = await run_one(site, i, headless)
        ok += bool(r["ok"])
        print(f"=== progress: {i}/{n}, sukses {ok} ===", flush=True)
    print(f"SELESAI {site}: {ok}/{n} sukses", flush=True)
    return ok


async def run_auto(n, headless, cooldown=3600):
    """Buat n akun, pindah gateway otomatis saat kena rate-limit."""
    ok = total = 0
    cooldown_until = {}
    while total < n:
        now = time.time()
        cands = [s for s in AUTO_ORDER if cooldown_until.get(s, 0) <= now]
        if not cands:
            wait = min(cooldown_until.values()) - now
            print(f"[auto] semua gateway cooldown, tunggu {int(wait)}s", flush=True)
            await asyncio.sleep(min(max(wait, 1), 300))
            continue
        site = cands[0]
        total += 1
        r = await run_one(site, total, headless)
        if r["ok"]:
            ok += 1
        elif _is_rate_limited(r):
            cooldown_until[site] = time.time() + cooldown
            print(f"[auto] {site} rate-limited -> cooldown {cooldown}s", flush=True)
        print(f"=== auto progress: {total}/{n}, sukses {ok} (site={site}) ===", flush=True)
    print(f"SELESAI auto: {ok}/{n} sukses", flush=True)
    return ok


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site", nargs="?")
    ap.add_argument("n", nargs="?", type=int)
    ap.add_argument("--auto", action="store_true",
                    help="fallback multi-gateway otomatis")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--cooldown", type=int, default=3600)
    a = ap.parse_args()
    headless = not a.headed
    if a.auto:
        # `batch.py --auto 2` -> argparse menaruh "2" di posisi site
        if a.n is None and a.site is not None:
            a.n, a.site = int(a.site), None
        if not a.n:
            ap.error("mode --auto butuh jumlah akun: batch.py --auto <n>")
        await run_auto(a.n, headless, a.cooldown)
    else:
        if not (a.site and a.n):
            ap.error("butuh <site> <n> atau --auto <n>")
        await run_single(a.site, a.n, headless)


if __name__ == "__main__":
    asyncio.run(main())
