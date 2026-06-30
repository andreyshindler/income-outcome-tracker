import asyncio
import logging
import os
from datetime import date as date_cls
from typing import Optional

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import (
    TELEGRAM_API_BASE,
    TELEGRAM_FILE_BASE,
    TELEGRAM_ALLOWED_USER_IDS,
    TELEGRAM_WEBHOOK_SECRET,
    RECEIPTS_API_TOKEN,
    RECEIPTS_IMAGE_DIR,
    WEBHOOK_PATH,
)
from app.database import Base, engine, SessionLocal
from app.models import Receipt
from app.ocr import ocr_image
from app.parser import extract_amount, extract_date, extract_vendor
from app.categories import category_keyboard, CATEGORY_CODES, CATEGORY_LABELS

logger = logging.getLogger("receipts")

Base.metadata.create_all(bind=engine)
os.makedirs(RECEIPTS_IMAGE_DIR, exist_ok=True)

app = FastAPI()


class DuplicateReceipt(Exception):
    """Raised when an incoming photo was already stored (Telegram retry)."""


async def tg_call(method: str, payload: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{TELEGRAM_API_BASE}/{method}", json=payload)
        resp.raise_for_status()
        return resp.json()


async def download_telegram_file(file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        info = await client.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id})
        info.raise_for_status()
        file_path = info.json()["result"]["file_path"]
        file_resp = await client.get(f"{TELEGRAM_FILE_BASE}/{file_path}")
        file_resp.raise_for_status()
        return file_resp.content


def summary_text(amount, currency, vendor, receipt_date, receipt_id) -> str:
    amount_str = f"{amount} {currency}" if amount is not None else "not detected"
    vendor_str = vendor or "not detected"
    rdate = receipt_date.isoformat() if receipt_date else "not detected"
    return (
        f"📄 Receipt #{receipt_id}\n"
        f"Amount: {amount_str}\n"
        f"Vendor: {vendor_str}\n"
        f"Date: {rdate}\n\n"
        f"Pick a category:"
    )


# --- Blocking work (OCR + DB), run off the event loop via asyncio.to_thread ---

def store_receipt(user_id: int, chat_id: int, message_id: int, image_bytes: bytes):
    """Persist image, OCR + parse, and insert one receipt row.

    Returns (receipt_id, summary). Raises DuplicateReceipt if this chat/message
    was already stored. Runs in a worker thread; no async/await here.
    """
    filename = f"{chat_id}_{message_id}.jpg"
    filepath = os.path.join(RECEIPTS_IMAGE_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)

    text = ocr_image(image_bytes)
    amount = extract_amount(text)
    vendor = extract_vendor(text)
    raw_date = extract_date(text)
    receipt_date = date_cls.fromisoformat(raw_date) if raw_date else None

    db = SessionLocal()
    try:
        existing = (
            db.query(Receipt)
            .filter(
                Receipt.telegram_chat_id == chat_id,
                Receipt.telegram_message_id == message_id,
            )
            .first()
        )
        if existing:
            raise DuplicateReceipt

        receipt = Receipt(
            telegram_user_id=user_id,
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            image_filename=filename,
            amount=amount,
            vendor=vendor,
            receipt_date=receipt_date,
            raw_ocr_text=text,
            status="pending",
        )
        db.add(receipt)
        try:
            db.commit()
        except IntegrityError:
            # Lost a race with a concurrent retry; treat as duplicate.
            db.rollback()
            raise DuplicateReceipt
        db.refresh(receipt)
        return receipt.id, summary_text(
            receipt.amount, receipt.currency, receipt.vendor,
            receipt.receipt_date, receipt.id,
        )
    finally:
        db.close()


def confirm_receipt(receipt_id: int, category_code: str):
    """Mark a receipt confirmed under the given category. Returns (label, text)
    or None if the receipt doesn't exist. Runs in a worker thread."""
    db = SessionLocal()
    try:
        receipt = db.get(Receipt, receipt_id)
        if not receipt:
            return None
        receipt.category = category_code
        receipt.status = "confirmed"
        db.commit()
        db.refresh(receipt)

        label = CATEGORY_LABELS.get(category_code, category_code)
        text = (
            f"✅ Receipt #{receipt.id} saved as {label}\n"
            f"Amount: {receipt.amount if receipt.amount is not None else 'n/a'} {receipt.currency}\n"
            f"Vendor: {receipt.vendor or 'n/a'}\n"
            f"Date: {receipt.receipt_date.isoformat() if receipt.receipt_date else 'n/a'}"
        )
        return label, text
    finally:
        db.close()


# --- Telegram update handlers (run as background tasks) ---

async def handle_message(message: dict):
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    if TELEGRAM_ALLOWED_USER_IDS and user_id not in TELEGRAM_ALLOWED_USER_IDS:
        await tg_call("sendMessage", {"chat_id": chat_id, "text": "Not authorized."})
        return

    photos = message.get("photo")
    if not photos:
        await tg_call(
            "sendMessage",
            {"chat_id": chat_id, "text": "Send a photo of a receipt and I'll read it."},
        )
        return

    message_id = message["message_id"]
    # Telegram sends multiple resolutions; last one is the largest.
    file_id = photos[-1]["file_id"]

    try:
        image_bytes = await download_telegram_file(file_id)
    except Exception:
        logger.exception("Failed to download Telegram file")
        await tg_call(
            "sendMessage",
            {"chat_id": chat_id, "text": "Couldn't download that image - please try again."},
        )
        return

    try:
        receipt_id, summary = await asyncio.to_thread(
            store_receipt, user_id, chat_id, message_id, image_bytes
        )
    except DuplicateReceipt:
        # Already processed this exact photo (webhook retry) - stay silent.
        return
    except Exception:
        logger.exception("Failed to OCR/store receipt")
        await tg_call(
            "sendMessage",
            {"chat_id": chat_id, "text": "Sorry, I couldn't read that receipt. Try a clearer photo."},
        )
        return

    await tg_call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": summary,
            "reply_markup": category_keyboard(receipt_id),
        },
    )


async def handle_callback(callback: dict):
    callback_id = callback["id"]
    user_id = callback["from"]["id"]
    data = callback.get("data", "")

    if TELEGRAM_ALLOWED_USER_IDS and user_id not in TELEGRAM_ALLOWED_USER_IDS:
        await tg_call(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": "Not authorized."},
        )
        return

    parts = data.split(":", 2)
    if len(parts) != 3 or parts[0] != "cat" or parts[2] not in CATEGORY_CODES:
        await tg_call("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    _, receipt_id_str, category_code = parts
    try:
        receipt_id = int(receipt_id_str)
    except ValueError:
        await tg_call("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    result = await asyncio.to_thread(confirm_receipt, receipt_id, category_code)
    if result:
        _, text = result
        await tg_call(
            "editMessageText",
            {
                "chat_id": callback["message"]["chat"]["id"],
                "message_id": callback["message"]["message_id"],
                "text": text,
            },
        )

    # Always answer so the client stops showing a spinner on the button.
    await tg_call("answerCallbackQuery", {"callback_query_id": callback_id})


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    # Reject forged calls to the public webhook path when a secret is configured.
    if TELEGRAM_WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TELEGRAM_WEBHOOK_SECRET:
            return JSONResponse({"ok": False}, status_code=403)

    update = await request.json()

    # Respond 200 immediately and do the slow work (download/OCR/DB) in the
    # background, so we never block the event loop or trip Telegram's retry.
    if "callback_query" in update:
        background_tasks.add_task(handle_callback, update["callback_query"])
    elif update.get("message"):
        background_tasks.add_task(handle_message, update["message"])

    return {"ok": True}


# --- JSON API (token-protected, fails closed) ---

def require_api_token(x_api_token: Optional[str] = Header(default=None)):
    if not RECEIPTS_API_TOKEN:
        raise HTTPException(status_code=503, detail="API token not configured")
    if x_api_token != RECEIPTS_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def serialize(r: Receipt) -> dict:
    return {
        "id": r.id,
        "amount": float(r.amount) if r.amount is not None else None,
        "currency": r.currency,
        "date": r.receipt_date.isoformat() if r.receipt_date else None,
        "vendor": r.vendor,
        "category": r.category,
        "business_use_percent": r.business_use_percent,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@app.get("/receipts-api/receipts", dependencies=[Depends(require_api_token)])
def list_receipts(category: Optional[str] = None, status: Optional[str] = None):
    db = SessionLocal()
    try:
        query = db.query(Receipt)
        if category:
            query = query.filter(Receipt.category == category)
        if status:
            query = query.filter(Receipt.status == status)
        rows = query.order_by(Receipt.created_at.desc()).all()
        return [serialize(r) for r in rows]
    finally:
        db.close()


@app.patch("/receipts-api/receipts/{receipt_id}", dependencies=[Depends(require_api_token)])
async def update_receipt(receipt_id: int, request: Request):
    """Correct a stored receipt - amount, vendor, date, category, status and
    business_use_percent (e.g. mark a 50%-business expense). Only whitelisted
    fields are accepted."""
    payload = await request.json()
    db = SessionLocal()
    try:
        receipt = db.get(Receipt, receipt_id)
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt not found")

        if "amount" in payload:
            receipt.amount = payload["amount"]
        if "vendor" in payload:
            receipt.vendor = payload["vendor"]
        if "currency" in payload:
            receipt.currency = payload["currency"]
        if "category" in payload:
            code = payload["category"]
            if code is not None and code not in CATEGORY_CODES:
                raise HTTPException(status_code=400, detail="Unknown category")
            receipt.category = code
        if "status" in payload:
            receipt.status = payload["status"]
        if "business_use_percent" in payload:
            pct = payload["business_use_percent"]
            if not isinstance(pct, int) or not 0 <= pct <= 100:
                raise HTTPException(status_code=400, detail="business_use_percent must be 0-100")
            receipt.business_use_percent = pct
        if "date" in payload:
            receipt.receipt_date = (
                date_cls.fromisoformat(payload["date"]) if payload["date"] else None
            )

        db.commit()
        db.refresh(receipt)
        return serialize(receipt)
    finally:
        db.close()


@app.get("/receipts-api/health")
def health():
    return {"ok": True}
