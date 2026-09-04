import os

# пробуем подтянуть .env и для прямого импорта config
for _p in [".env", "C:\\Users\\user\\Desktop\\bot\\.env", os.path.join(os.path.dirname(__file__), ".env")]:
    if os.path.exists(_p):
        try:
            with open(_p, encoding="utf-8-sig") as _f:
                for _line in _f:
                    _line=_line.strip()
                    if not _line or _line.startswith("#") or "=" not in _line:
                        continue
                    _k,_v=_line.split("=",1)
                    _k=_k.strip().lstrip("\ufeff")
                    _v=_v.strip().strip('"').strip("'")
                    if _k and _v and not os.getenv(_k):
                        os.environ[_k]=_v
        except: pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

SHEETS = {
    "chapaeva": {
        "id": "1eobrgtYnn3IHf3_47-Vc-H0qsl4PzvXR1Sm6bfUP_qk",
        "gid": "647718560",
        "name": "Чапаева 33",
        "full": "г. Краснокамск, ул. Чапаева, 33",
        "emoji": "🏫",
    },
    "pushkino": {
        "id": "1H6UAGHWJf6IwcTtJW35Z_k4hTp2AudgkNeCOMkMCbOQ",
        "gid": "2011998642",
        "name": "Пушкина 15",
        "full": "г. Краснокамск, ул. Пушкина, 15",
        "emoji": "🎓",
    },
}

# кэш в памяти на 10 минут
CACHE_TTL = 600

NUM_EMOJI = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
