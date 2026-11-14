"""Entry point. Run from backend/:  uvicorn app.main:app --reload"""
from fastapi import FastAPI

from app import models  # noqa: F401  (importing registers the tables)
from app.database import Base, engine

# Creates all tables in quotesure.db if they don't exist yet
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="QuoteSure API",
    description="AI agent that helps small factories buy raw material right and quote orders profitably.",
    version="0.1.0",
)


@app.get("/")
def health_check():
    return {"status": "ok", "app": "QuoteSure"}