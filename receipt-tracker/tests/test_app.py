"""Integration tests for the webhook, auth, and JSON API."""

WEBHOOK_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "websecret"}
API_HEADERS = {"X-API-Token": "apitoken"}


def test_health(client):
    assert client.get("/receipts-api/health").json() == {"ok": True}


def test_api_requires_token(client):
    assert client.get("/receipts-api/receipts").status_code == 401
    assert client.get("/receipts-api/receipts", headers=API_HEADERS).status_code == 200


def test_webhook_rejects_bad_secret(client):
    r = client.post(
        "/receipts-api/webhook",
        json={},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert r.status_code == 403


def test_webhook_accepts_good_secret(client):
    r = client.post("/receipts-api/webhook", json={}, headers=WEBHOOK_HEADERS)
    assert r.status_code == 200


def test_store_receipt_parses_and_dedupes(app_module):
    app_module.ocr_image = lambda b: 'VeloGrip\nסה"כ 1,234.56\n01/02/2026'
    rid, summary = app_module.store_receipt(42, 100, 7, b"img")
    assert rid == 1
    assert "1234.56" in summary

    # A retry of the same chat/message must not create a second row.
    try:
        app_module.store_receipt(42, 100, 7, b"img")
        assert False, "expected DuplicateReceipt"
    except app_module.DuplicateReceipt:
        pass


def test_confirm_receipt(app_module):
    app_module.ocr_image = lambda b: "Shop\n50.00"
    rid, _ = app_module.store_receipt(42, 200, 8, b"img")
    label, text = app_module.confirm_receipt(rid, "vehicle")
    assert "Vehicle" in label
    assert app_module.confirm_receipt(999999, "vehicle") is None


def test_patch_business_use_percent_and_validation(app_module, client):
    app_module.ocr_image = lambda b: "Shop\n50.00"
    rid, _ = app_module.store_receipt(42, 300, 9, b"img")

    ok = client.patch(
        f"/receipts-api/receipts/{rid}",
        headers=API_HEADERS,
        json={"business_use_percent": 50, "category": "vehicle"},
    )
    assert ok.status_code == 200
    assert ok.json()["business_use_percent"] == 50
    assert ok.json()["category"] == "vehicle"

    assert client.patch(
        f"/receipts-api/receipts/{rid}", headers=API_HEADERS,
        json={"business_use_percent": 150},
    ).status_code == 400
    assert client.patch(
        f"/receipts-api/receipts/{rid}", headers=API_HEADERS,
        json={"category": "nope"},
    ).status_code == 400
    assert client.patch(
        "/receipts-api/receipts/424242", headers=API_HEADERS,
        json={"vendor": "x"},
    ).status_code == 404
