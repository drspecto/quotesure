"""Entry point. Run from backend/:  uvicorn app.main:app --reload
Then open http://127.0.0.1:8000 for the dashboard, or /docs for the API."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  (importing registers the tables)
from app.database import Base, engine
from app.routers import agent, alerts, buying, dashboard, prices, quoting, settings, suppliers

# Creates all tables in quotesure.db if they don't exist yet
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="QuoteSure API",
    description="AI agent that helps small factories buy raw material right and quote orders profitably.",
    version="0.1.0",
)

# Plug in each group of endpoints
app.include_router(prices.router)
app.include_router(suppliers.router)
app.include_router(settings.router)
app.include_router(quoting.router)
app.include_router(buying.router)
app.include_router(alerts.router)
app.include_router(agent.router)
app.include_router(dashboard.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "app": "QuoteSure"}


# The web dashboard (plain HTML/CSS/JS, no build step) and the sample quotes
BACKEND_DIR = Path(__file__).resolve().parents[1]
app.mount("/app", StaticFiles(directory=BACKEND_DIR / "app" / "static", html=True), name="dashboard")
app.mount("/samples", StaticFiles(directory=BACKEND_DIR / "data" / "sample_quotes"), name="samples")


@app.get("/", include_in_schema=False)
def open_dashboard():
    return RedirectResponse("/app/")
