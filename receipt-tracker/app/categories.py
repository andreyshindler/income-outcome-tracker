# Categories tuned to VeloGrip's business lines + tax tracking needs.
# Edit freely - codes are stored in the DB, labels are just for the Telegram buttons.
CATEGORIES = [
    ("race_timing", "🏁 Race Timing"),
    ("printing_3d", "🖨️ 3D Printing"),
    ("mtb_coaching", "🚵 MTB Coaching"),
    ("vehicle", "🚗 Vehicle (CX-5)"),
    ("vps_software", "💻 VPS/Software"),
    ("equipment", "🛠️ Equipment"),
    ("office_general", "📎 General/Office"),
    ("personal", "🏠 Personal"),
    ("other", "❓ Other"),
]

CATEGORY_CODES = {code for code, _ in CATEGORIES}
CATEGORY_LABELS = dict(CATEGORIES)


def category_keyboard(receipt_id: int) -> dict:
    """Telegram inline_keyboard markup, 2 buttons per row."""
    rows = []
    row = []
    for code, label in CATEGORIES:
        row.append({"text": label, "callback_data": f"cat:{receipt_id}:{code}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}
