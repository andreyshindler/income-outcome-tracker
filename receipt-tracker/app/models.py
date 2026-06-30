from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"
    # A Telegram photo maps to exactly one receipt; the constraint makes
    # webhook re-deliveries (retries) idempotent at the DB level.
    __table_args__ = (
        UniqueConstraint(
            "telegram_chat_id",
            "telegram_message_id",
            name="uq_receipt_chat_message",
        ),
    )

    id = Column(Integer, primary_key=True)

    telegram_user_id = Column(BigInteger, nullable=False)
    telegram_chat_id = Column(BigInteger, nullable=False)
    telegram_message_id = Column(BigInteger, nullable=True)

    image_filename = Column(String, nullable=False)

    amount = Column(Numeric(10, 2), nullable=True)
    currency = Column(String, default="ILS")
    receipt_date = Column(Date, nullable=True)
    vendor = Column(String, nullable=True)
    category = Column(String, nullable=True)
    business_use_percent = Column(Integer, default=100)

    raw_ocr_text = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending, confirmed, needs_review

    created_at = Column(DateTime, server_default=func.now())
