"""Shared test setup: stub the Google Vision SDK, point the app at an in-memory
SQLite DB, and expose a FastAPI TestClient."""
import os
import sys
import types

import pytest

# Stub google.cloud.vision so app.ocr imports without the real SDK installed.
_google = types.ModuleType("google")
_cloud = types.ModuleType("google.cloud")
_vision = types.ModuleType("google.cloud.vision")
_vision.ImageAnnotatorClient = object
_vision.Image = object
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.cloud", _cloud)
sys.modules.setdefault("google.cloud.vision", _vision)

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("TELEGRAM_ALLOWED_USER_IDS", "42")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "websecret")
os.environ.setdefault("RECEIPTS_API_TOKEN", "apitoken")
os.environ.setdefault("RECEIPTS_IMAGE_DIR", "/tmp/receipt-tracker-test-imgs")


@pytest.fixture()
def app_module():
    """Import the app and rebind its engine to a shared in-memory SQLite DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.database as database
    import app.main as main

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    database.engine = engine
    database.SessionLocal = session_local
    main.engine = engine
    main.SessionLocal = session_local
    main.Base.metadata.create_all(bind=engine)

    return main


@pytest.fixture()
def client(app_module):
    from fastapi.testclient import TestClient

    return TestClient(app_module.app)
