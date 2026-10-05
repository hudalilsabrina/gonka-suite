#!/usr/bin/env python3
"""
Gonka Suite - Factory akun + panen API key dari gateway/proxy jaringan Gonka.

Gateway: broker/broker pihak ketiga yang menjual akses OpenAI-compatible ke
jaringan inference terdesentralisasi Gonka. Banyak yang punya free tier.

Command:
  list                 Daftar gateway + status recon
  harvest <site>       Buat 1 akun di gateway, verifikasi, ambil API key
  harvest-all          Coba harvest semua gateway yang feasible
  test <site|all>      Test API key tersimpan (chat nyata)
  report               Ringkasan akun & key yang berhasil
  probe <site>         Recon halaman signup (form, captcha, endpoint)
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.table import Table
from rich import box

from src.gateways import GATEWAYS, all_names, get as get_gw
from src import harvester
from src import harvesters_extra as hx
from src.inboxstore import get as get_inbox

C = Console()
ACCOUNTS = Path(__file__).resolve().parent / "accounts.txt"


def cmd_list():
    t = Table(box=box.ROUNDED, title="Gonka Gateways")
    t.add_column("Site", style="cyan")
    t.add_column("Base URL", style="dim", overflow="fold")
    t.add_column("Captcha", style="yellow")
    t.add_column("Verify", style="white")
    t.add_column("Free", style="green")
    for n in all_names():
        g = GATEWAYS[n]
        t.add_row(n, g.get("base_url") or "-", g.get("captcha", "?"),
                  g.get("verify", "?"), g.get("free", "-"))
    C.print(t)


async def cmd_harvest(site, headless=True):
    r = await harvester.harvest(site, headless=headless)
    C.print(json.dumps({k: v for k, v in r.items() if k != "key"}, indent=1, default=str))
    if r.get("key"):
        C.print("[green]KEY diperoleh[/]")
    else:
        C.print("[yellow]KEY tidak diperoleh[/]")


async def cmd_harvest_all(headless=True):
    ok = []
    for n in all_names():
        g = GATEWAYS[n]
        if g.get("captcha") == "recaptcha":
            C.print(f"[dim]skip {n} (recaptcha)[/]")
            continue
        try:
            r = await harvester.harvest(n, headless=headless)
            if r.get("ok"):
                ok.append(n)
                C.print(f"[green]OK {n}[/]")
            else:
                C.print(f"[yellow]{n}: {r.get('error') or 'no key'}[/]")
        except Exception as e:
            C.print(f"[red]{n}: {e}[/]")
    C.print(f"\n[bold]Berhasil: {len(ok)}[/] -> {ok}")


def cmd_harvest_extra(site, n=1):
    """Harvester untuk gateway dengan alur khusus (dahl, gonka-api)."""
    for i in range(n):
        if site == "dahl":
            r = hx.harvest_dahl()
        elif site in ("gonka-api", "gonka_api"):
            r = hx.harvest_gonka_api()
        else:
            C.print(f"[red]site tidak didukung harvest-extra: {site}[/]"); return
        red = {k: (v if not isinstance(v, str) or len(v) < 20 else v[:8] + "..." + v[-4:])
               for k, v in r.items()}
        C.print(f"[{i+1}/{n}] {json.dumps(red, default=str)}")


async def cmd_pipeline(site, n=1, headless=True):
    """Harvest massal di gateway tanpa captcha (proxy.gonka.gg, gonka24, mingles).

    Setiap akun diverifikasi (chat test) sebelum dicatat sukses.
    """
    import time as _t
    ok = fail = 0
    for i in range(1, n + 1):
        C.print(f"[cyan]=== Akun {i}/{n} @ {site} ===[/]")
        try:
            if site in ("dahl", "gonka-api"):
                r = hx.harvest_dahl() if site == "dahl" else hx.harvest_gonka_api()
                key, base = r.get("key"), r.get("base_url") or "https://inference.dahl.global/v1"
            else:
                r = await harvester.harvest(site, headless=headless)
                key, base = r.get("key"), r.get("base_url")
            if key and base:
                t = hx.test_chat(base, key)
                if t.get("ok"):
                    ok += 1; C.print("[green]  OK (chat verified)[/]")
                else:
                    fail += 1; C.print(f"[yellow]  key ok tapi chat gagal: {t.get('error')}[/]")
            else:
                fail += 1; C.print(f"[red]  gagal: {r.get('error') or 'no key'}[/]")
        except Exception as e:
            fail += 1; C.print(f"[red]  error: {str(e)[:100]}[/]")
        _t.sleep(2)
    C.print(f"\n[bold]Pipeline {site}: {ok} sukses, {fail} gagal[/]")


def _parse_accounts():
    """Parse accounts.txt: format email:password:key:baseurl (baseurl mengandung ':').

    Gunakan rsplit agar baseurl utuh; email & password tidak mengandung ':'.
    """
    lines = ACCOUNTS.read_text().strip().splitlines() if ACCOUNTS.exists() else []
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        # email:password:key:baseurl  -> split max 3 kali (baseurl boleh mengandung ':')
        try:
            email, password, key, base = ln.split(":", 3)
            out.append({"email": email, "password": password, "key": key, "base_url": base})
        except ValueError:
            continue
    return out


def cmd_test(site, model=None):
    rows = []
    for a in _parse_accounts():
        if site not in ("all", None) and site not in a["base_url"]:
            continue
        r = harvester.test_key(a["base_url"], a["key"], model)
        rows.append((a["email"], a["base_url"], r.get("ok"), r.get("model"),
                     r.get("chat_error") or r.get("models_error")))
    t = Table(box=box.ROUNDED, title="Test API Keys")
    t.add_column("Email"); t.add_column("Base", overflow="fold")
    t.add_column("OK"); t.add_column("Model"); t.add_column("Error", overflow="fold")
    for e, b, ok, m, err in rows:
        t.add_row(e, b, "[green]yes[/]" if ok else "[red]no[/]", m or "-", (err or "")[:60])
    C.print(t)


def cmd_report():
    accounts = _parse_accounts()
    t = Table(box=box.ROUNDED, title="Gonka Suite Report")
    t.add_column("Metrik", style="cyan"); t.add_column("Nilai", style="white")
    t.add_row("Akun tersimpan", str(len(accounts)))
    sites = {}
    for a in accounts:
        sites[a["base_url"]] = sites.get(a["base_url"], 0) + 1
    for b, n in sites.items():
        t.add_row(f"  {b}", str(n))
    C.print(t)


async def cmd_probe(site):
    from playwright.async_api import async_playwright
    from src.stealth import launch_stealth_browser, create_stealth_context
    gw = get_gw(site)
    if not gw:
        C.print(f"[red]gateway tidak dikenal: {site}[/]"); return
    async with async_playwright() as p:
        b = await launch_stealth_browser(p, headless=True)
        ctx = await create_stealth_context(b)
        pg = await ctx.new_page()
        await pg.goto(gw["signup_url"], wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3500)
        info = await pg.evaluate("""() => {
          const o={url:location.href,inputs:[],buttons:[],iframes:[],text:document.body.innerText.slice(0,200)};
          document.querySelectorAll('input').forEach(i=>o.inputs.push({type:i.type,ph:i.placeholder}));
          document.querySelectorAll('button').forEach(b=>{const t=b.textContent.trim(); if(t)o.buttons.push(t.slice(0,25));});
          document.querySelectorAll('iframe').forEach(f=>o.iframes.push((f.src||'').slice(0,70)));
          return o;
        }""")
        C.print(json.dumps(info, indent=1))
        await ctx.close(); await b.close()


def cmd_sync(site=None, base=None):
    """Injeksi akun gateway ke 9router sebagai provider OpenAI-compatible."""
    from src import router9
    accounts = _parse_accounts()
    if site:
        # cocokkan keyword ke base_url (mis. 'gonka-proxy'->'proxy.gonka.gg',
        # 'gonka24'->'gonka24.com'); pakai bagian signifikan
        key = site.replace("-", "").replace("gonka", "")
        accounts = [a for a in accounts
                    if site in a["base_url"] or (key and key in a["base_url"])]
    if not accounts:
        C.print("[yellow]Tidak ada akun untuk disync[/]"); return
    # kelompokkan per base_url -> 1 node per gateway
    groups = {}
    for a in accounts:
        groups.setdefault(a["base_url"], []).append(a)
    for base_url, accts in groups.items():
        # nama & prefix unik per gateway (host penuh, bukan hanya segmen pertama)
        host = base_url.split("//")[-1].split("/")[0]
        slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
        name = f"gonka-{slug}"[:40]
        prefix = f"gk-{slug}"[:32]
        C.print(f"[cyan]Sync {name} ({len(accts)} akun) -> {base_url}[/]")
        r = router9.ingest_gateway(name, prefix, base_url, accts, base)
        C.print(f"  {json.dumps(r)}")


def main():
    ap = argparse.ArgumentParser(prog="gonka", description="Gonka Suite")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    p_h = sub.add_parser("harvest"); p_h.add_argument("site"); p_h.add_argument("--headed", action="store_true")
    p_ha = sub.add_parser("harvest-all"); p_ha.add_argument("--headed", action="store_true")
    p_he = sub.add_parser("harvest-extra"); p_he.add_argument("site"); p_he.add_argument("-n", type=int, default=1)
    p_pl = sub.add_parser("pipeline"); p_pl.add_argument("site"); p_pl.add_argument("-n", type=int, default=1); p_pl.add_argument("--headed", action="store_true")
    p_t = sub.add_parser("test"); p_t.add_argument("site", nargs="?", default="all"); p_t.add_argument("--model")
    p_s = sub.add_parser("sync"); p_s.add_argument("site", nargs="?", default=None); p_s.add_argument("--base", default=None)
    sub.add_parser("report")
    p_p = sub.add_parser("probe"); p_p.add_argument("site")
    args = ap.parse_args()

    if args.cmd == "list" or not args.cmd:
        cmd_list()
    elif args.cmd == "harvest":
        asyncio.run(cmd_harvest(args.site, headless=not args.headed))
    elif args.cmd == "harvest-all":
        asyncio.run(cmd_harvest_all(headless=not args.headed))
    elif args.cmd == "harvest-extra":
        cmd_harvest_extra(args.site, args.n)
    elif args.cmd == "pipeline":
        asyncio.run(cmd_pipeline(args.site, args.n, headless=not args.headed))
    elif args.cmd == "test":
        cmd_test(args.site, args.model)
    elif args.cmd == "sync":
        cmd_sync(args.site, args.base)
    elif args.cmd == "report":
        cmd_report()
    elif args.cmd == "probe":
        asyncio.run(cmd_probe(args.site))


if __name__ == "__main__":
    main()
