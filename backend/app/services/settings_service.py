"""Reads the factory's cost settings from the database."""
from sqlalchemy.orm import Session

from app import models
from app.services.cost_engine import CostSettings


def get_factory_settings(db: Session) -> models.FactorySettings:
    """The single settings row. Creates one with default values if it's missing."""
    fs = db.query(models.FactorySettings).first()
    if fs is None:
        fs = models.FactorySettings()
        db.add(fs)
        db.commit()
        db.refresh(fs)
    return fs


def to_cost_settings(fs: models.FactorySettings) -> CostSettings:
    """Convert the database row into the plain object the cost engine expects."""
    return CostSettings(
        labour_rate_per_hr=fs.labour_rate_per_hr,
        machine_rate_per_hr=fs.machine_rate_per_hr,
        power_cost_per_hr=fs.power_cost_per_hr,
        scrap_percent=fs.scrap_percent,
        overhead_percent=fs.overhead_percent,
        target_margin_percent=fs.target_margin_percent,
    )
