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
| `gonkarouter` | `api.gonkarouter.io/v1` | none | email OTP | 20 USDT | ✅ E2E |
| `gonkagate` | `api.gonkagate.com/v1` | none | magic-link | $10 | ⏳ register 201, email blocked |
| `joingonka` | `gate.joingonka.ai/v1` | Turnstile | ? | 3M | 🔴 Cloudflare |
| `gonka-broker` | `proxy.gonkabroker.com/v1` | reCAPTCHA Ent. | ? | 1M/bln | 🔴 403 |
| `hyperfusion` | – | reCAPTCHA | ? | – | 🔴 |

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

### Batch runner (multi-gateway)

```bash
.venv/bin/python batch.py <site> <n>   # N akun dari satu gateway, log ke data/batch_<site>.jsonl
.venv/bin/python batch.py --auto <n>   # N akun, auto-fallback antar-gateway saat kena rate-limit
```

`--auto` mendeteksi pesan rate-limit dan otomatis pindah ke gateway berikutnya
(urutan `AUTO_ORDER`), dengan cooldown per-gateway. Setiap key diverifikasi chat
sebelum dicatat. Gateway yang punya batas per-IP akan di-cooldown, sementara
gateway tanpa batas (mis. gonkarouter) terus dipakai.

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

Temp-mail memakai **[tempik](https://github.com/hirotomasato/tempik)** — layanan
disposable email self-hosted. Kliennya ada di `src/tempmail.py`; set base URL-nya
lewat `config.toml [api] tempmail_base` atau env `TEMPIK_BASE`.

### Endpoint kunci per gateway
- proxy.gonka.gg: `POST /api/auth/register`, `POST /api/keys`
- gonka24: `POST /api/auth/register` (Firebase), `POST /api/keys`
- mingles: `POST /api/auth/register`, `POST /api/keys`
- dahl: `POST /v1/auth/signup` → fingerprint + key; `POST /v1/account/allocate` (100M)
- gonka-api: `POST /functions/v1/agent-signup` (1 request = akun + token, tanpa email)
- gonkarouter: email-OTP login (auto-create) → `GET /api/keys` → `POST /api/keys/{id}/reveal`
- gonkagate: `POST /api/v1/auth/register` → 201; `POST /api/v1/auth/resend-verification`

## Harvester alur khusus (`harvest-extra`)

Beberapa gateway tidak memakai form signup standar:

| Site | Alur |
|---|---|
| `dahl` | username-only → fingerprint + key → allocate 100M |
| `gonka-api` | `POST /agent-signup` (1 request, tanpa email/captcha) |
| `gonkarouter` | email → OTP 6-digit (auto-create) → reveal key |

```bash
./run.sh harvest-extra dahl -n 1
./run.sh harvest-extra gonka-api -n 1
./run.sh harvest-extra gonkarouter -n 1
```

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

## Credits

- **[tempik](https://github.com/hirotomasato/tempik)** — self-hosted disposable
  temp-mail service. Endpoint klien (`/api/session`, `/api/inboxes`,
  `/api/inboxes/{addr}/messages`) yang dipakai `src/tempmail.py` mengikuti API
  tempik. Terima kasih kepada penulisnya.
- Slider captcha solver di `src/captcha.py` di-port dari `captcha-solver.js`
  (algoritma alpha NCC + Canny edges + Sobel gap detection).
- Model diakses lewat gateway OpenAI-compatible ke jaringan Gonka.
