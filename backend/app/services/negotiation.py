"""
Drafts a polite WhatsApp message asking the supplier for a better price.

Python decides the numbers (target prices). Gemini only writes the words.
If Gemini is unavailable, a ready-made template is used, so this never fails.
"""
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.services.extractor import make_client
from app.services.quote_checker import QuoteCheck


def _target_lines(check: QuoteCheck) -> list[str]:
    lines = []
    for c in check.items:
        if c.verdict == "overpriced" and c.fair_price:
            lines.append(f"{c.material_name}: quoted ₹{c.price_per_kg:.2f}/kg, "
                         f"market ₹{c.market_price:.2f}/kg, asking for ₹{c.fair_price:.2f}/kg "
                         f"({c.quantity_kg:,.0f} kg)")
    return lines


def template_message(supplier_name: str, check: QuoteCheck) -> str:
    lines = _target_lines(check)
    if not lines:
        return ""
    name = supplier_name or "ji"
    body = "\n".join(f"- {line}" for line in lines)
    return (f"Namaste {name},\n\nThank you for the quotation. We have checked current market rates, "
            f"and some prices are higher than the market:\n{body}\n\n"
            f"We have bought from you regularly and would like to continue. "
            f"Can you revise these rates? Please confirm, and we will place the order.\n\nRegards")


def draft_message(supplier_name: str, check: QuoteCheck) -> str:
    """Returns '' when there is nothing to negotiate."""
    lines = _target_lines(check)
    if not lines:
        return ""
    if not GEMINI_API_KEY:
        return template_message(supplier_name, check)

    prompt = (
        "Write a short, polite WhatsApp message from a small factory owner in India to their "
        f"raw-material supplier '{supplier_name or 'the supplier'}', asking for a price revision. "
        "Tone: respectful, friendly, firm. Mention that they are a regular customer. "
        "Use simple English (a few common Hindi words like 'ji' are fine). Under 90 words. "
        "Use EXACTLY these numbers, do not change or add any:\n" + "\n".join(lines)
    )
    try:
        client = make_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4),
        )
        text = (response.text or "").strip()
        return text or template_message(supplier_name, check)
    except Exception:   # any Gemini problem -> use the template instead
        return template_message(supplier_name, check)
