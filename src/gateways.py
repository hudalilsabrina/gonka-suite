"""Registry gateway Gonka: definisi tiap broker/gateway + alur signup-nya.

Setiap entry mendeskripsikan:
- name, home, signup_url, base_url (untuk inference)
- signup_api: endpoint POST registrasi (bila diketahui)
- captcha: 'none' | 'recaptcha' | 'turnstile' | 'slider' | 'robot-check'
- verify: 'otp6' | 'magic-link' | 'none'
- notes: catatan recon

Diisi dari hasil recon langsung (lihat data/recon_*.json).
"""

GATEWAYS = {
    "gonka-broker": {
        "home": "https://gonkabroker.com/",
        "signup_url": "https://app.gonkabroker.com/signup",
        "base_url": "https://proxy.gonkabroker.com/v1",
        "signup_api": "https://app.gonkabroker.com/api/users/signup",
        "key_prefix": "gnk-prx-",
        "captcha": "recaptcha",   # Google reCAPTCHA Enterprise -> 403 headless
        "verify": "unknown",
        "free": ">=1M token/bulan",
        "notes": "reCAPTCHA Enterprise (k=6LeOXyss...) memblokir signup headless (403).",
    },
    "gonka24": {
        "home": "https://gonka24.com/",
        "signup_url": "https://gonka24.com/auth/register",
        "base_url": "https://api.gonka24.com/v1",
        "signup_api": "https://gonka24.com/api/auth/register",
        "key_api": "https://gonka24.com/api/keys",
        "captcha": "none",
        "verify": "magic-link",   # Firebase email verification
        "free": "$10 bonus",
        "notes": "Register 201 -> Firebase verify link -> dashboard. Key via POST /api/keys (rawKey).",
    },
    "gonkagate": {
        "home": "https://gonkagate.com/en",
        "signup_url": "https://gonkagate.com/en/register",
        "base_url": "https://api.gonkagate.com/v1",
        "signup_api": "https://gonkagate.com/api/v1/auth/register",
        "captcha": "none",
        "verify": "magic-link",
        "free": "$10 kredit",
        "notes": "Register 201 -> 'Check your inbox' -> verify link.",
    },
    "joingonka": {
        "home": "https://gate.joingonka.ai/",
        "signup_url": "https://gate.joingonka.ai/register",
        "base_url": "https://gate.joingonka.ai/v1",
        "signup_api": None,
        "key_prefix": "jg-",
        "captcha": "robot-check",  # 'I'm not a robot' + Cloudflare-ish
        "verify": "unknown",
        "free": "3M token",
        "notes": "Ada verifikasi 'I'm not a robot'; kandidat butuh captcha solving.",
    },
    "gonka-proxy": {
        "home": "https://proxy.gonka.gg/",
        "signup_url": "https://proxy.gonka.gg/register",
        "base_url": "https://api.proxy.gonka.gg/v1",
        "signup_api": "https://proxy.gonka.gg/api/auth/register",
        "key_api": "https://proxy.gonka.gg/api/keys",
        "key_prefix": "sk-",
        "captcha": "none",
        "verify": "otp6",
        "free": "1M token",
        "notes": "TERVERIFIKASI END-TO-END. OTP 6-digit, key via POST /api/keys (field 'key').",
    },
    "gonkarouter": {
        "home": "https://router.gonkascan.com/",
        "signup_url": "https://gonkarouter.io/dashboard",
        "base_url": "https://api.gonkarouter.io/v1",
        "signup_api": None,
        "key_prefix": "sk-",
        "captcha": "unknown",
        "verify": "unknown",
        "free": "$20 kredit",
        "notes": "Dashboard guest mode; perlu cari alur signup (mungkin wallet/crypto).",
    },
    "hyperfusion": {
        "home": "https://console.hyperfusion.io/",
        "signup_url": "https://console.hyperfusion.io/auth?mode=signup",
        "base_url": None,
        "signup_api": None,
        "captcha": "recaptcha",   # google recaptcha anchor
        "verify": "unknown",
        "free": "-",
        "notes": "Portal hardware/AI wizard, bukan gateway LLM murni; reCAPTCHA.",
    },
    "mingles": {
        "home": "https://router.mingles.ai/",
        "signup_url": "https://router.mingles.ai/app",
        "base_url": "https://router.mingles.ai/v1",
        "signup_api": "https://router.mingles.ai/api/auth/register",
        "key_api": "https://router.mingles.ai/api/keys",
        "key_prefix": "sk-",
        "captcha": "none",
        "verify": "magic-link",
        "free": "~3.9M token/minggu",
        "notes": "TERVERIFIKASI. Verify link /api/auth/verify?token=... ; key via POST /api/keys.",
    },
    "gonka-api": {
        "home": "https://gonka-api.org/",
        "signup_url": "https://gonka-api.org/dashboard-demo",
        "base_url": "https://hskyauefqcgbvgvxkluj.supabase.co/functions/v1/gonka",
        "signup_api": None,
        "captcha": "unknown",
        "verify": "unknown",
        "free": "10M token",
        "notes": "Supabase-backed; butuh recon alur signup.",
    },
    "dahl": {
        "home": "https://inference.dahl.global/",
        "signup_url": "https://inference.dahl.global/account",
        "base_url": "https://inference.dahl.global/v1",
        "signup_api": None,
        "captcha": "none",
        "verify": "fingerprint",  # password = 32-char fingerprint
        "free": "100M token",
        "notes": "Login pakai 32-char fingerprint (bukan email/pw). Free 100M token.",
    },
}


def get(name: str):
    return GATEWAYS.get(name)


def all_names():
    return list(GATEWAYS.keys())
