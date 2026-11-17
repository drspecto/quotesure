"""
The AI quote READER. Gemini looks at a supplier quote (photo or PDF) and
returns clean, structured data: supplier name, and each line item with
quantity and price per kg.

The AI only READS here. All comparisons and math happen in quote_checker.py.
"""
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from app.config import GEMINI_API_KEY, GEMINI_MODEL

SUPPORTED_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


class ExtractedItem(BaseModel):
    description: str = Field(description="The item exactly as written on the quote")
    quantity_kg: float = Field(description="Quantity converted to kg (1 MT = 1 tonne = 1000 kg)")
    price_per_kg: float = Field(description="Price per kg in rupees, BEFORE GST, converted if quoted per tonne/MT/quintal")
    material_id: int | None = Field(description="id of the matching material from the list, or null if none match")


class ExtractedQuote(BaseModel):
    supplier_name: str = Field(description="The seller's business name, or empty string if not visible")
    quote_date: str | None = Field(description="Date on the quote as written, or null")
    items: list[ExtractedItem]
    notes: str = Field(description="Anything unclear or unreadable, in one short sentence. Empty if all clear.")


class ExtractionError(Exception):
    """Raised with a message that is safe to show to the user."""


TIMEOUT_SECONDS = 60


def make_client() -> genai.Client:
    """A Gemini client that gives up after 60 seconds instead of waiting forever,
    and retries at most once if Google is busy."""
    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=TIMEOUT_SECONDS * 1000,   # milliseconds
            retry_options=types.HttpRetryOptions(attempts=2),
        ),
    )


PROMPT = """You are reading a raw-material price quotation sent by a supplier to a small
Indian manufacturing factory. It may be typed, handwritten, a phone photo, or a PDF,
and may mix English and Hindi.

Extract every raw-material line item.

Rules:
- Convert every quantity to kg (1 MT / tonne / ton = 1000 kg, 1 quintal = 100 kg).
- Convert every price to rupees PER KG, before GST. If a price is per MT/tonne,
  divide by 1000. If GST is included in the price, remove it (GST % is usually written).
- Indian number formats like 1,24,000 mean 124000.
- Ignore freight, loading, and tax summary lines; they are not items.
- Match each item to ONE material from this list by meaning (e.g. "CR sheet 2 mm" or
  "CRCA 2mm sheet" = MS Sheet 2mm CRCA). If nothing matches, use null.

Materials list (id: name):
{materials}

If you cannot read a number, do not guess: leave the item out and say so in notes."""


def extract_quote(file_bytes: bytes, mime_type: str,
                  materials: list[tuple[int, str]]) -> ExtractedQuote:
    """Send the file to Gemini and get back structured quote data."""
    if mime_type not in SUPPORTED_TYPES:
        raise ExtractionError(f"Unsupported file type {mime_type}. Use PNG, JPG, WEBP or PDF.")
    if not GEMINI_API_KEY:
        raise ExtractionError("GEMINI_API_KEY is missing from .env")

    material_list = "\n".join(f"{mid}: {name}" for mid, name in materials)
    client = make_client()

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                PROMPT.format(materials=material_list),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedQuote,   # forces Gemini to answer in this exact shape
                temperature=0,                    # same input -> same answer
            ),
        )
    except errors.APIError as e:
        raise ExtractionError(
            f"Gemini error ({e.code}): {e.message}. "
            f"If the model name is the problem, set GEMINI_MODEL in .env (now: {GEMINI_MODEL})."
        ) from e
    except Exception as e:   # timeouts, no internet, etc.
        raise ExtractionError(
            f"Could not reach Gemini within {TIMEOUT_SECONDS}s ({type(e).__name__}). "
            "Check your internet, then run: python -m data.check_gemini"
        ) from e

    result = response.parsed
    if result is None:
        raise ExtractionError("Gemini could not read this quote. Try a clearer photo.")

    # Safety net: drop items with impossible numbers, and unknown material ids
    valid_ids = {mid for mid, _ in materials}
    clean = []
    for item in result.items:
        if item.quantity_kg <= 0 or item.price_per_kg <= 0:
            continue
        if item.material_id not in valid_ids:
            item.material_id = None
        clean.append(item)
    result.items = clean
    return result
