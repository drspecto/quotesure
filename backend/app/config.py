"""Loads settings (API key, database URL) from the .env file in the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

# .env lives in quotesure/ (two levels above this file: app/ -> backend/ -> quotesure/)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quotesure.db")
