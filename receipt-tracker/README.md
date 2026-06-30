# VeloGrip Receipt Tracker

Send a photo of a receipt to a Telegram bot → Google Vision OCRs it → amount/date/vendor are
extracted automatically → you tap a category button → it's saved to Postgres.

## How it works

1. You photograph a receipt and send it to the bot.
2. The bot acknowledges immediately, then in the background saves the image to disk and sends
   it to Google Cloud Vision for text detection.
3. Simple parsing pulls out the total amount, date, and vendor name from the OCR text.
4. The bot replies with what it found plus category buttons (Race Timing, 3D Printing,
   MTB Coaching, Vehicle, VPS/Software, Equipment, General/Office, Personal, Other - edit
   the list in `app/categories.py` if you want different ones).
5. Tapping a category confirms the receipt and marks it `confirmed` in the DB.
6. `GET /receipts-api/receipts` returns everything as JSON (filterable by `?category=` and
   `?status=`) - handy for pulling into your existing openpyxl tax tracker.
7. `PATCH /receipts-api/receipts/{id}` lets you correct a stored receipt (amount, vendor,
   date, category, status, or `business_use_percent` for partial-business expenses).

OCR accuracy on real-world Hebrew receipts is decent but not perfect, especially for faded
thermal paper. The amount-extraction logic prefers the line containing a "total"/"סה"כ"
keyword, falling back to the largest money-looking number on the receipt (thousands
separators like `1,234.56` are handled). Worth spot-checking totals against the stored
images (`receipts_images` Docker volume) before filing taxes.

## Security model

This app is reachable from the public internet via nginx, so access is gated in three places:

- **Bot messages** are restricted to `TELEGRAM_ALLOWED_USER_IDS`. Leaving that empty disables
  the check and opens the bot to everyone, so keep it set.
- **The webhook** verifies Telegram's `X-Telegram-Bot-Api-Secret-Token` header against
  `TELEGRAM_WEBHOOK_SECRET`, so nobody can forge updates by POSTing to the public path.
- **The JSON API** (`GET /receipts` and `PATCH /receipts/{id}`) requires the `X-API-Token`
  header to match `RECEIPTS_API_TOKEN`. It fails closed: if the token isn't configured the
  API returns `503`.

## One-time setup

**1. Create the Telegram bot**
Message @BotFather → `/newbot` → copy the token into `.env`.

**2. Get a Google Cloud Vision API key**
- Create/use a GCP project, enable the "Cloud Vision API".
- Create a service account, generate a JSON key.
- Save it as `credentials/google-vision.json` in this project (already gitignored).
- Vision API pricing: first 1,000 units/month free, then ~$1.50 per 1,000 - plenty for
  personal receipt volume.

**3. Configure**
```bash
cp .env.example .env
# edit .env: POSTGRES_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS,
#            TELEGRAM_WEBHOOK_SECRET, RECEIPTS_API_TOKEN
# generate the two secrets with e.g. `openssl rand -hex 32`
mkdir -p credentials
# place google-vision.json in credentials/
```

## Deploy to srv1515969

Same pattern as shopping-list / strava-bot:

```bash
scp -r receipt-tracker komodo@srv1515969:~/
ssh komodo@srv1515969
cd receipt-tracker
docker compose up -d --build
```

Add the block from `nginx-snippet.conf` to the existing nginx server block (same one
serving `/jarvis/`, `/list/`, `/stats/`), then:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

Register the webhook with the secret (replace with your real domain and the secret from `.env`):
```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  --data-urlencode "url=https://yourdomain.com/receipts-api/webhook" \
  --data-urlencode "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Test: send a photo to the bot. You should get a reply with the parsed amount and category
buttons within a few seconds.

Reading the API:
```bash
curl -H "X-API-Token: <RECEIPTS_API_TOKEN>" \
  "https://yourdomain.com/receipts-api/receipts?status=confirmed"
```

## Notes

- Port `8431` is used for the app container - change it in `docker-compose.yml` and
  `nginx-snippet.conf` together if it collides with anything else on the box.
- Receipt images are kept in a Docker volume (`receipts_images`), not deleted automatically -
  useful as a backup/audit trail for tax purposes.
- Webhook re-deliveries are idempotent: a unique `(chat_id, message_id)` constraint plus an
  in-handler check means a retried photo won't create a duplicate receipt.
