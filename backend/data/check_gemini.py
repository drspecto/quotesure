"""
Checks the Gemini connection step by step and shows how long each step takes.

Run from backend/:   python -m data.check_gemini
"""
import time
from pathlib import Path

from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.services.extractor import make_client

SAMPLE = Path(__file__).parent / "sample_quotes" / "1_sharma_steel_overpriced.png"


def step(name, fn):
    print(f"\n▶ {name} ...", flush=True)
    start = time.time()
    try:
        result = fn()
        print(f"  ✅ OK in {time.time() - start:.1f}s")
        return result
    except Exception as e:
        print(f"  ❌ FAILED after {time.time() - start:.1f}s: {type(e).__name__}: {e}")
        return None


def main():
    print(f"API key loaded: {'yes, starts with ' + GEMINI_API_KEY[:6] if GEMINI_API_KEY else 'NO - check .env'}")
    print(f"Model: {GEMINI_MODEL}")
    if not GEMINI_API_KEY:
        return
    client = make_client()

    models = step("1. List models your key can use", lambda: [m.name for m in client.models.list()])
    if models:
        flash = [m.replace("models/", "") for m in models if "flash" in m]
        print("  Flash models:", ", ".join(flash[:12]))
        if f"models/{GEMINI_MODEL}" not in models:
            print(f"  ⚠️  '{GEMINI_MODEL}' is NOT in your list. Put one of the names above in .env as GEMINI_MODEL=...")

    reply = step("2. Tiny text question", lambda: client.models.generate_content(
        model=GEMINI_MODEL, contents="Reply with just the word OK").text)
    if reply:
        print("  Gemini said:", reply.strip())

    reply = step("3. Read the sample quote image", lambda: client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Part.from_bytes(data=SAMPLE.read_bytes(), mime_type="image/png"),
                  "List the item names and rates on this quotation, one per line."]).text)
    if reply:
        print("  Gemini said:\n ", reply.strip().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
