"""Database tables. Each class = one table, each Column = one column."""
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class FactorySettings(Base):
    """The factory's own cost numbers. The cost engine uses these for every quote."""
    __tablename__ = "factory_settings"

    id = Column(Integer, primary_key=True)
    factory_name = Column(String, default="My Factory")
    labour_rate_per_hr = Column(Float, default=150.0)     # ₹ per worker-hour
    machine_rate_per_hr = Column(Float, default=400.0)    # ₹ per machine-hour (wear, maintenance)
    power_cost_per_hr = Column(Float, default=120.0)      # ₹ electricity per machine-hour
    scrap_percent = Column(Float, default=8.0)            # % of material wasted
    overhead_percent = Column(Float, default=12.0)        # rent, admin, etc. as % of direct cost
    target_margin_percent = Column(Float, default=15.0)   # profit the owner wants


class Material(Base):
    """A raw material, e.g. 'MS Sheet' grade '2mm'."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    grade = Column(String, default="")
    unit = Column(String, default="kg")

    prices = relationship("MarketPrice", back_populates="material")


class MarketPrice(Base):
    """Daily market price of a material (simulated feed for the prototype)."""
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    date = Column(Date, default=date.today)
    price_per_unit = Column(Float, nullable=False)

    material = relationship("Material", back_populates="prices")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    city = Column(String, default="")
    phone = Column(String, default="")
    rating = Column(Float, default=3.0)  # 1–5, how reliable they've been

    purchases = relationship("Purchase", back_populates="supplier")


class Purchase(Base):
    """Past raw material purchases. Used to say 'you paid less last month'."""
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    price_per_unit = Column(Float, nullable=False)
    date = Column(Date, default=date.today)

    supplier = relationship("Supplier", back_populates="purchases")
    material = relationship("Material")


class SupplierQuote(Base):
    """A quote uploaded by the owner (photo/PDF), plus the AI's verdict."""
    __tablename__ = "supplier_quotes"

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    file_name = Column(String, default="")
    created_at = Column(DateTime, default=datetime.now)
    verdict = Column(String, default="pending")   # fair / overpriced / good_deal / pending
    summary = Column(Text, default="")            # short explanation shown to the owner
    negotiation_message = Column(Text, default="")

    supplier = relationship("Supplier")
    items = relationship("SupplierQuoteItem", back_populates="quote", cascade="all, delete-orphan")


class SupplierQuoteItem(Base):
    """One line from a supplier quote, e.g. 'MS Sheet 2mm, 500 kg @ ₹68/kg'."""
    __tablename__ = "supplier_quote_items"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("supplier_quotes.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)  # matched material
    raw_description = Column(String, default="")   # exactly what the quote said
    quantity = Column(Float, default=0)
    price_per_unit = Column(Float, default=0)
    market_price = Column(Float, nullable=True)     # filled in after comparison
    difference_percent = Column(Float, nullable=True)  # +11 means 11% above market

    quote = relationship("SupplierQuote", back_populates="items")
    material = relationship("Material")


class Quotation(Base):
    """A quote the factory gives to ITS customer, with the full cost breakdown."""
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True)
    customer_name = Column(String, nullable=False)
    part_name = Column(String, nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    weight_per_piece_kg = Column(Float, nullable=False)
    machine_hours_per_piece = Column(Float, default=0)
    labour_hours_per_piece = Column(Float, default=0)

    material_price_used = Column(Float, nullable=False)  # ₹/kg at the time of quoting
    total_cost = Column(Float, nullable=False)           # true cost for the whole order
    quoted_price = Column(Float, nullable=False)         # total price offered to customer
    status = Column(String, default="open")              # open / won / lost
    created_at = Column(DateTime, default=datetime.now)
    valid_until = Column(Date, nullable=True)

    material = relationship("Material")


class Alert(Base):
    """Warnings shown on the dashboard, e.g. 'Quote #12 is now loss-making'."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    type = Column(String, default="info")   # price_spike / loss_risk / overpriced_quote / info
    message = Column(Text, nullable=False)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    is_read = Column(Boolean, default=False)