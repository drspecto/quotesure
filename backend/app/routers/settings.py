"""Endpoints to view and change the factory's cost settings."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services.settings_service import get_factory_settings

router = APIRouter(prefix="/settings", tags=["Factory Settings"])


@router.get("", response_model=schemas.SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    return get_factory_settings(db)


@router.put("", response_model=schemas.SettingsOut)
def update_settings(changes: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    """Change one or more settings, e.g. {"labour_rate_per_hr": 175}."""
    fs = get_factory_settings(db)
    for field, value in changes.model_dump(exclude_none=True).items():
        setattr(fs, field, value)
    db.commit()
    db.refresh(fs)
    return fs
