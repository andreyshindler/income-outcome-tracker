import os

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

TELEGRAM_ALLOWED_USER_IDS = {
    int(x) for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()
}

# Shared secret Telegram echoes back in the X-Telegram-Bot-Api-Secret-Token
# header (set it when registering the webhook). When non-empty it is enforced,
# so forged requests to the public webhook path are rejected.
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# Token required to read/modify the receipts JSON API (sent as X-API-Token).
# The API fails closed: if this is unset, the API returns 503.
RECEIPTS_API_TOKEN = os.environ.get("RECEIPTS_API_TOKEN", "")

DATABASE_URL = os.environ["DATABASE_URL"]

RECEIPTS_IMAGE_DIR = os.environ.get("RECEIPTS_IMAGE_DIR", "/app/data/images")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/receipts-api/webhook")
