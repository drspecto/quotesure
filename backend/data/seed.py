"""
Fills the database with realistic DEMO data for a small fabrication factory.

Run from backend/:   python -m data.seed

Running it again wipes the database and rebuilds it from scratch, so it's safe
to re-run any time the data gets messy.
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from app import models
from app.database import Base, SessionLocal, engine
from app.services.cost_engine import CostSettings, OrderInput, calculate

# Same "random" numbers every run, so the demo always looks the same
random.seed(42)

DAYS_OF_HISTORY = 90
CSV_PATH = Path(__file__).parent / "market_prices.csv"

# (name, grade, unit, starting price ₹ per unit, daily volatility %)
# Prices are SIMULATED for the prototype, roughly in a realistic range.
MATERIALS = [
    ("MS Sheet", "2mm CRCA", "kg", 62.0, 0.8),
    ("MS Round Bar", "20mm EN8", "kg", 58.0, 0.7),
    ("SS Sheet", "304 1.5mm", "kg", 225.0, 0.6),
    ("Aluminium Rod", "6061 T6", "kg", 265.0, 0.9),
    ("Copper Wire", "ETP 2.5mm", "kg", 860.0, 1.0),
    ("PP Granules", "Injection grade", "kg", 112.0, 0.7),
]

# (name, city, phone, rating, usual markup over market price in %)
# Sharma Steel Traders is the "villain": the owner has used them for years
# and they quietly charge ~10-14% above market. The demo exposes this.
SUPPLIERS = [
    ("Sharma Steel Traders", "Pune", "+91 98220 11111", 4.0, (10, 14)),
    ("Om Sai Metals", "Pune", "+91 98220 22222", 3.5, (1, 4)),
    ("Bharat Alloys & Co.", "Mumbai", "+91 98200 33333", 4.2, (2, 5)),
    ("Shree Polymers", "Bhosari MIDC", "+91 98220 44444", 3.8, (3, 6)),
]

# Which supplier sells which materials (by index into the lists above)
SUPPLIER_MATERIALS = {
    0: [0, 1, 2],   # Sharma: MS sheet, MS bar, SS sheet
    1: [0, 1],      # Om Sai: MS sheet, MS bar
    2: [2, 3, 4],   # Bharat: SS, aluminium, copper
    3: [5],         # Shree: plastic granules
}


def generate_price_history():
    """Random-walk prices for each material over the last 90 days.
    Returns {material_index: [(date, price), ...]} and writes market_prices.csv."""
    today = date.today()
    history = {}
    rows = []

    for m_idx, (name, grade, unit, start_price, vol) in enumerate(MATERIALS):
        price = start_price
        series = []
        for day in range(DAYS_OF_HISTORY, -1, -1):  # 90 days ago -> today
            d = today - timedelta(days=day)
            # small daily move + slight upward drift (metal prices tend to creep up)
            change_pct = random.gauss(0.03, vol)
            price = max(price * (1 + change_pct / 100), start_price * 0.7)
            series.append((d, round(price, 2)))
            rows.append([name, grade, d.isoformat(), round(price, 2)])
        history[m_idx] = series

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["material", "grade", "date", "price_per_kg"])
        writer.writerows(rows)

    return history


def seed():
    print("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Factory settings (one row)
        db.add(models.FactorySettings(
            factory_name="Patil Precision Fabricators",
            labour_rate_per_hr=150.0,
            machine_rate_per_hr=400.0,
            power_cost_per_hr=120.0,
            scrap_percent=8.0,
            overhead_percent=12.0,
            target_margin_percent=15.0,
        ))

        # 2. Materials
        material_rows = []
        for name, grade, unit, _, _ in MATERIALS:
            m = models.Material(name=name, grade=grade, unit=unit)
            db.add(m)
            material_rows.append(m)
        db.flush()  # gives each material its id without committing yet

        # 3. Market prices (90 days)
        history = generate_price_history()
        for m_idx, series in history.items():
            for d, price in series:
                db.add(models.MarketPrice(
                    material_id=material_rows[m_idx].id, date=d, price_per_unit=price
                ))

        # 4. Suppliers
        supplier_rows = []
        for name, city, phone, rating, _ in SUPPLIERS:
            s = models.Supplier(name=name, city=city, phone=phone, rating=rating)
            db.add(s)
            supplier_rows.append(s)
        db.flush()

        # 5. Past purchases: roughly one every ~10 days per supplier-material pair
        purchase_count = 0
        for s_idx, m_indices in SUPPLIER_MATERIALS.items():
            low, high = SUPPLIERS[s_idx][4]
            for m_idx in m_indices:
                series = history[m_idx]
                day = random.randint(0, 9)
                while day < len(series) - 1:
                    d, market_price = series[day]
                    markup = random.uniform(low, high)
                    db.add(models.Purchase(
                        supplier_id=supplier_rows[s_idx].id,
                        material_id=material_rows[m_idx].id,
                        quantity=random.choice([200, 250, 300, 500, 750, 1000]),
                        price_per_unit=round(market_price * (1 + markup / 100), 2),
                        date=d,
                    ))
                    purchase_count += 1
                    day += random.randint(7, 14)

        # 6. Open customer quotations, made ~3-4 weeks ago at THAT day's prices.
        #    Prices have moved since, so later the alerts can catch quotes that
        #    became loss-making. (customer, part, material index, qty, kg/pc,
        #    machine h/pc, labour h/pc, days ago, price per piece quoted)
        settings = CostSettings(150.0, 400.0, 120.0, 8.0, 12.0, 15.0)
        QUOTES = [
            ("Deccan Auto Components", "Mounting bracket", 0, 2000, 0.8, 0.05, 0.08, 28, 104.0),
            ("Shivneri Pumps", "Pump shaft", 1, 500, 2.4, 0.25, 0.20, 25, 397.0),
            ("Sahyadri Agro Equipment", "SS hopper panel", 2, 150, 6.5, 0.40, 0.60, 21, 2290.0),
        ]
        for cust, part, m_idx, qty, kg, mh, lh, days_ago, per_piece in QUOTES:
            d, price_then = history[m_idx][DAYS_OF_HISTORY - days_ago]
            cost = calculate(OrderInput(qty, kg, price_then, mh, lh), settings)
            db.add(models.Quotation(
                customer_name=cust, part_name=part,
                material_id=material_rows[m_idx].id, quantity=qty,
                weight_per_piece_kg=kg, machine_hours_per_piece=mh, labour_hours_per_piece=lh,
                material_price_used=price_then, total_cost=cost.total_cost,
                quoted_price=round(per_piece * qty, 2), status="open",
                created_at=datetime.combine(d, datetime.min.time()),
                valid_until=d + timedelta(days=45),
            ))

        db.commit()
        print(f"✅ Seeded: 1 factory, {len(MATERIALS)} materials, "
              f"{len(MATERIALS) * (DAYS_OF_HISTORY + 1)} price points, "
              f"{len(SUPPLIERS)} suppliers, {purchase_count} purchases, "
              f"{len(QUOTES)} open quotations")
        print(f"✅ Wrote {CSV_PATH.name}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()