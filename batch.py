#!/usr/bin/env python3
"""Batch harvester: buat N akun dari gateway feasible, log tiap hasil ke JSON.

Pakai: .venv/bin/python batch.py <site> <n> [--headed]
Hasil di-append ke data/batch_<site>.json (satu objek per baris) agar tahan
timeout & bisa diagregasi terpisah.
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


def _log(site, i, r):
    rec = {"site": site, "idx": i, "ts": int(time.time()),
           "ok": bool(r.get("ok")), "key_len": len(r.get("key") or ""),
           "email": r.get("email"), "error": (r.get("error") or "")[:120]}
    with (DATA / f"batch_{site}.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


async def run_one(site, i, headless):
    try:
        if site == "freeai":
            r = await hx.harvest_freeai(headless=headless)
        elif site == "gonkarouter":
            r = await hx.harvest_gonkarouter(headless=headless)
        elif site == "dahl":
            r = hx.harvest_dahl()
        elif site == "gonka-api":
            r = hx.harvest_gonka_api()
        else:
            r = await harvester.harvest(site, headless=headless)
    except Exception as e:
        r = {"ok": False, "error": str(e)[:150]}
    rec = _log(site, i, r)
    # verifikasi chat kalau ada key
    if r.get("key") and r.get("base_url"):
        t = hx.test_chat(r["base_url"], r["key"])
        rec["chat_ok"] = bool(t.get("ok"))
        if not t.get("ok"):
            rec["chat_error"] = str(t.get("error"))[:100]
        with (DATA / f"batch_{site}.jsonl").open("a") as f:
            f.write(json.dumps({**rec, "verify": True}) + "\n")
    status = "OK" if rec.get("ok") else "FAIL"
    print(f"[{i}] {status} {rec.get('email')} {rec.get('error','')}", flush=True)
    return rec


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("n", type=int)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    ok = 0
    for i in range(1, a.n + 1):
        r = await run_one(a.site, i, headless=not a.headed)
        if r.get("ok"):
            ok += 1
        print(f"=== progress: {i}/{a.n}, sukses {ok} ===", flush=True)
    print(f"SELESAI {a.site}: {ok}/{a.n} sukses", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
