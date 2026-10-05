# Gonka Suite

Factory akun + panen API key dari **gateway/proxy OpenAI-compatible ke jaringan
Gonka** (jaringan inference GPU terdesentralisasi). Banyak broker pihak ketiga
menjual akses murah ke Gonka dengan **free tier**.

Suite ini: buat akun → verifikasi → ambil API key → test chat → inject ke 9router.

## Gateway yang didukung

| Site | Base URL | Captcha | Verify | Free | Status |
|---|---|---|---|---|---|
| `gonka-proxy` | `api.proxy.gonka.gg/v1` | none | OTP 6-digit | 1M token | ✅ E2E |
| `gonka24` | `api.gonka24.com/v1` | none | magic-link | $10 | ✅ E2E |
| `mingles` | `router.mingles.ai/v1` | none | magic-link | ~3.9M/mgg | ✅ E2E |
| `dahl` | `inference.dahl.global/v1` | none | username-only | 100M token | ✅ E2E |
| `gonka-api` | `.../functions/v1/gonka` | none | agent-signup | $0.05 (~2.5M) | ✅ E2E |
| `gonkagate` | `api.gonkagate.com/v1` | none | magic-link | $10 | ⏳ register OK |
| `joingonka` | `gate.joingonka.ai/v1` | robot-check | ? | 3M | 🔴 |
| `gonka-broker` | `proxy.gonkabroker.com/v1` | reCAPTCHA Ent. | ? | 1M/bln | 🔴 403 |
| `hyperfusion` | – | reCAPTCHA | ? | – | 🔴 |
| `gonkarouter` | `api.gonkarouter.io/v1` | ? | ? | $20 | ⏳ |

Model tersedia: MiniMax M2.7, DeepSeek V4 Flash, GLM-5.3-Flash, Kimi K2.6, Qwen 3.8 Flash.

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install playwright rich
.venv/bin/playwright install chromium
```

## Command

```bash
./run.sh list                    # daftar gateway + metadata
./run.sh probe <site>            # recon halaman signup (form/captcha/endpoint)
./run.sh harvest <site>          # harvest 1 akun (browser, gateway standar)
./run.sh harvest-extra dahl -n 1 # harvest gateway alur khusus (dahl, gonka-api)
./run.sh pipeline <site> -n 10   # harvest massal + verifikasi chat
./run.sh test all                # test semua API key tersimpan
./run.sh report                  # ringkasan akun
./run.sh sync [site]             # inject akun ke 9router (OpenAI-compatible node)
```

## Format akun (`accounts.txt`)

```
email:password:api_key:base_url
```
Catatan: `dahl` pakai `username:fingerprint:api_key:base_url`.
`base_url` boleh mengandung `:` (di-parse dengan split max 3).

## Alur harvest (reverse-engineered)

1. **Inbox** temp-mail (session persisten per-situs di `data/inboxes.json`).
2. **Signup** via browser (React → wajib real typing, bukan set value).
3. **Verifikasi**: OTP 6-digit / magic-link dari inbox.
4. **API key** dari response `POST /api/keys` (field `key`/`rawKey`/`token`).
5. **Test chat** → simpan.

### Endpoint kunci per gateway
- proxy.gonka.gg: `POST /api/auth/register`, `POST /api/keys`
- gonka24: `POST /api/auth/register` (Firebase), `POST /api/keys`
- mingles: `POST /api/auth/register`, `POST /api/keys`
- dahl: `POST /v1/auth/signup` → fingerprint + key; `POST /v1/account/allocate` (100M)
- gonka-api: `POST /functions/v1/agent-signup` (1 request = akun + token, tanpa email)

## Integrasi 9router

Menambah gateway sebagai provider OpenAI-compatible:
1. `POST /api/provider-nodes` `{name, prefix, apiType:"chat", baseUrl, type:"openai-compatible"}`
2. `POST /api/providers` `{provider:<nodeId>, apiKey, name}`
3. `POST /api/providers/{id}/test`

Lihat `src/router9.py`. Prefix wajib unik per gateway (dibuat dari slug host).

## Catatan keamanan / operasional

- **Rate limit**: dahl & gonka-api membatasi signup per-IP. Spasi batch.
- **reCAPTCHA Enterprise** (gonka-broker, hyperfusion) memblokir signup headless.
- **gonka-api `agent-signup`** adalah jalur resmi untuk agen — tanpa email/captcha.
- Jangan commit `accounts.txt` / `data/` (berisi kredensial).
