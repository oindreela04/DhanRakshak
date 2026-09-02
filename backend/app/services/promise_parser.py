from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


def parse_promise(text: str, amount: float | None = None) -> dict:
    lower = text.lower(); language = "Bengali" if any(word in lower for word in ["করব", "দেব", "পরিশোধ"]) else "Hindi" if any(word in lower for word in ["ko", "kar", "dunga", "tak", "clear"]) else "English"
    found = re.search(r"(?:₹|rs\.?\s*)?([\d,]+)", text, re.I); parsed_amount = amount or (float(found.group(1).replace(",", "")) if found else 0)
    today = datetime.now(timezone.utc); promised = today + timedelta(days=1)
    if "monday" in lower or "सोम" in lower: promised = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    elif "friday" in lower or "शुक्र" in lower: promised = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    confidence = .9 if found and any(day in lower for day in ["monday", "friday", "tomorrow", "सोम", "शुक्र"]) else .65 if parsed_amount else .3
    return {"amount": parsed_amount, "promised_for": promised, "language": language, "confidence": confidence}
