"""Shapes of the data our API sends back (and later, receives).
FastAPI uses these to validate data and to draw the /docs page."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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


# ---------- Factory settings ----------

class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factory_name: str
    labour_rate_per_hr: float
    machine_rate_per_hr: float
    power_cost_per_hr: float
    scrap_percent: float
    overhead_percent: float
    target_margin_percent: float


class SettingsUpdate(BaseModel):
    """Send only the fields you want to change."""
    factory_name: str | None = None
    labour_rate_per_hr: float | None = Field(default=None, ge=0)
    machine_rate_per_hr: float | None = Field(default=None, ge=0)
    power_cost_per_hr: float | None = Field(default=None, ge=0)
    scrap_percent: float | None = Field(default=None, ge=0, lt=100)
    overhead_percent: float | None = Field(default=None, ge=0)
    target_margin_percent: float | None = Field(default=None, ge=0)


# ---------- Customer quotes ----------

class QuoteRequest(BaseModel):
    """The order details. Used to get a cost estimate."""
    material_id: int
    quantity: int = Field(gt=0, examples=[500])
    weight_per_piece_kg: float = Field(gt=0, examples=[1.2])
    machine_hours_per_piece: float = Field(default=0, ge=0, examples=[0.1])
    labour_hours_per_piece: float = Field(default=0, ge=0, examples=[0.1])
    material_price_per_kg: float | None = Field(
        default=None, gt=0, description="Leave empty to use today's market price")
    owner_price_per_piece: float | None = Field(
        default=None, gt=0, description="The price you were planning to quote, to check it")


class CostBreakdownOut(BaseModel):
    material_name: str
    material_price_used: float
    raw_material_kg_per_piece: float
    material_cost: float
    machine_cost: float
    labour_cost: float
    direct_cost: float
    overhead_cost: float
    total_cost: float
    cost_per_piece: float
    recommended_price_per_piece: float
    recommended_total: float
    owner_total: float | None
    owner_profit: float | None
    owner_margin_percent: float | None
    verdict: str
    cost_if_material_up_10: float


class QuoteCreate(QuoteRequest):
    """Order details + who it's for. Saves a quotation."""
    customer_name: str = Field(min_length=1, examples=["Deccan Auto Components"])
    part_name: str = Field(min_length=1, examples=["Mounting bracket"])
    final_price_per_piece: float | None = Field(
        default=None, gt=0, description="Leave empty to use the recommended price")
    valid_days: int = Field(default=15, ge=1, le=90)


class QuotationOut(BaseModel):
    id: int
    customer_name: str
    part_name: str
    material_name: str
    quantity: int
    price_per_piece: float
    quoted_price: float
    total_cost: float
    profit: float
    margin_percent: float
    material_price_used: float
    status: str
    created_at: datetime
    valid_until: date | None
    # Same order re-costed at TODAY's material price (feeds the alerts later)
    today_material_price: float | None
    today_total_cost: float | None
    today_profit: float | None
