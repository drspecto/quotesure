"""Shapes of the data our API sends back (and later, receives).
FastAPI uses these to validate data and to draw the /docs page."""
from datetime import date

from pydantic import BaseModel, ConfigDict


# ---------- Materials & prices ----------

class MaterialOut(BaseModel):
    id: int
    name: str
    grade: str
    unit: str
    latest_price: float | None       # ₹ per unit today
    change_30d_percent: float | None  # +3.2 = up 3.2% in 30 days


class PricePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # can be built straight from a DB row

    date: date
    price_per_unit: float


class PriceHistoryOut(BaseModel):
    material_id: int
    material_name: str
    prices: list[PricePoint]


# ---------- Suppliers & purchases ----------

class SupplierOut(BaseModel):
    id: int
    name: str
    city: str
    phone: str
    rating: float
    purchase_count: int
    avg_markup_percent: float | None  # average % paid above market


class PurchaseOut(BaseModel):
    id: int
    date: date
    material_name: str
    quantity: float
    price_per_unit: float
    market_price: float | None
    markup_percent: float | None


class SupplierDetailOut(SupplierOut):
    """Same as SupplierOut, plus the purchase list."""
    purchases: list[PurchaseOut]