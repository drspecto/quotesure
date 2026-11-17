"""
Creates realistic FAKE supplier quotes in data/sample_quotes/ for testing and the demo.

Run from backend/:   python -m data.make_sample_quotes

Prices are set against the seed data's "today" market prices:
  MS Sheet 64.39, MS Round Bar 67.40, SS Sheet 241.52,
  Aluminium Rod 280.96, Copper Wire 825.52, PP Granules 112.91 (₹/kg)
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent / "sample_quotes"
FONT_DIRS = [
    "/System/Library/Fonts/Supplemental/",          # Mac
    "/Library/Fonts/",                              # Mac
    "/usr/share/fonts/truetype/dejavu/",            # Linux
    "C:/Windows/Fonts/",                            # Windows
]
FONT_FILES = {
    "regular": ["Arial.ttf", "DejaVuSans.ttf", "arial.ttf"],
    "bold": ["Arial Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"],
    "hand": ["Bradley Hand Bold.ttf", "Noteworthy.ttc", "DejaVuSans-Oblique.ttf", "ariali.ttf"],
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        for f in FONT_FILES[kind]:
            p = Path(d) / f
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def typed_quote(path: Path, seller: str, address: str, phone: str, quote_no: str, date: str,
                rows: list[tuple[str, str, str, str]], footer: list[str], pdf: bool = False):
    """A clean, typed quotation on A4-ish paper."""
    W, H = 1240, 1754
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((80, 70), seller, font=font("bold", 52), fill="#1a1a1a")
    d.text((80, 140), address, font=font("regular", 26), fill="#444")
    d.text((80, 175), phone, font=font("regular", 26), fill="#444")
    d.line((80, 225, W - 80, 225), fill="#1a1a1a", width=3)
    d.text((80, 260), "QUOTATION", font=font("bold", 40), fill="#1a1a1a")
    d.text((W - 420, 262), f"No: {quote_no}", font=font("regular", 28), fill="#1a1a1a")
    d.text((W - 420, 300), f"Date: {date}", font=font("regular", 28), fill="#1a1a1a")
    d.text((80, 330), "To: Patil Precision Fabricators, Bhosari MIDC, Pune", font=font("regular", 28), fill="#1a1a1a")

    cols = [80, 140, 560, 720, 950]
    y = 420
    d.rectangle((80, y, W - 80, y + 56), fill="#e8e8e8")
    for x, h in zip(cols, ["#", "Description", "Qty", "Rate", "Amount"]):
        d.text((x + 10, y + 12), h, font=font("bold", 28), fill="#1a1a1a")
    y += 56
    for i, (desc, qty, rate, amount) in enumerate(rows, 1):
        for x, v in zip(cols, [str(i), desc, qty, rate, amount]):
            d.text((x + 10, y + 16), v, font=font("regular", 27), fill="#1a1a1a")
        y += 64
        d.line((80, y, W - 80, y), fill="#cccccc", width=2)
    y += 40
    for line in footer:
        d.text((80, y), line, font=font("regular", 27), fill="#1a1a1a")
        y += 42
    d.text((W - 420, H - 200), f"For {seller}", font=font("regular", 26), fill="#1a1a1a")
    d.text((W - 420, H - 120), "Authorised Signatory", font=font("regular", 24), fill="#666")

    if pdf:
        img.save(path, "PDF", resolution=150)
    else:
        img.save(path)


def handwritten_photo(path: Path):
    """A handwritten quote on lined paper, photographed slightly crooked."""
    random.seed(7)
    W, H = 1100, 1400
    paper = Image.new("RGB", (W, H), "#fbf8ef")
    d = ImageDraw.Draw(paper)
    for y in range(160, H, 62):
        d.line((0, y, W, y), fill="#c9d8ef", width=2)
    d.line((110, 0, 110, H), fill="#f0b4b4", width=2)
    ink = "#1d2f6f"
    hand = lambda s: font("hand", s)
    lines = [
        (hand(46), "SHARMA STEEL TRADERS"),
        (hand(30), "Pune  -  Ph 98220 11111"),
        (hand(32), "Date 16/11/26"),
        (hand(34), "Patil ji - rates as discussed:"),
        (hand(34), "1) SS 304 sheet 1.5mm - 200 kg"),
        (hand(34), "     @ Rs 274 /kg"),
        (hand(34), "2) MS CR sheet 2 mm - 1 ton"),
        (hand(34), "     @ Rs 71,500 / MT"),
        (hand(34), "GST 18% extra.  Transport free"),
        (hand(34), "Delivery 3 din me"),
    ]
    y = 105
    for f, text in lines:
        d.text((140 + random.randint(-6, 6), y), text, font=f, fill=ink)
        y += 124 if f.size >= 46 else 124
    # Turn it into a "phone photo": rotate, add shadow, slight blur and noise
    photo = Image.new("RGB", (W + 200, H + 200), "#8a8f96")
    photo.paste(paper, (100, 100))
    photo = photo.rotate(-3.5, resample=Image.BICUBIC, fillcolor="#8a8f96")
    photo = photo.filter(ImageFilter.GaussianBlur(1.1))
    px = photo.load()
    for _ in range(60000):
        x, y = random.randrange(photo.width), random.randrange(photo.height)
        r, g, b = px[x, y]
        n = random.randint(-18, 18)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    photo.convert("RGB").save(path, quality=80)


def main():
    OUT.mkdir(exist_ok=True)

    # 1. Sharma, typed: MS sheet +11.8%, MS bar +12.0%  -> OVERPRICED
    typed_quote(OUT / "1_sharma_steel_overpriced.png",
                "Sharma Steel Traders", "Plot 14, Bhosari MIDC, Pune 411026", "Ph: +91 98220 11111",
                "SST/2026/418", "16-11-2026",
                [("MS CRCA Sheet 2mm", "500 kg", "72.00", "36,000.00"),
                 ("MS Round Bar EN8 20mm", "300 kg", "75.50", "22,650.00")],
                ["Rates per kg, GST @18% extra.", "Delivery: within 3 days. Payment: 30 days."])

    # 2. Om Sai, typed: same items, ~2.5% above market -> FAIR
    typed_quote(OUT / "2_om_sai_fair.png",
                "Om Sai Metals", "Gat No. 221, Chakan Road, Pune", "Ph: +91 98220 22222",
                "OSM-1127", "16/11/2026",
                [("CR Sheet 2 mm (CRCA)", "500 kg", "66.00", "33,000.00"),
                 ("EN8 Round 20 mm", "300 kg", "68.90", "20,670.00")],
                ["All rates per kg + GST 18%.", "Valid for 7 days."])

    # 3. Bharat Alloys, PDF: aluminium and copper slightly BELOW market -> GOOD DEAL
    typed_quote(OUT / "3_bharat_alloys_good_deal.pdf",
                "Bharat Alloys & Co.", "Kalbadevi Road, Mumbai 400002", "Ph: +91 98200 33333",
                "BA/Q/7731", "16 Nov 2026",
                [("Aluminium Rod 6061-T6", "200 kg", "279.00", "55,800.00"),
                 ("Copper Wire ETP 2.5mm", "100 kg", "820.00", "82,000.00")],
                ["Prices per kg, exclusive of GST.", "Ex-godown Mumbai."], pdf=True)

    # 4. Shree Polymers: priced PER TONNE with Indian commas (tests unit conversion) -> FAIR
    typed_quote(OUT / "4_shree_polymers_per_tonne.png",
                "Shree Polymers", "J-Block, Bhosari MIDC, Pune", "Ph: +91 98220 44444",
                "SP/25-26/093", "16.11.2026",
                [("PP Granules (Injection)", "2 MT", "1,16,000/MT", "2,32,000.00")],
                ["Rate per Metric Tonne, GST extra.", "Bags of 25 kg."])

    # 5. Sharma, handwritten phone photo, mixed units, Hinglish -> OVERPRICED
    handwritten_photo(OUT / "5_sharma_handwritten_photo.jpg")

    print(f"✅ Wrote {len(list(OUT.iterdir()))} sample quotes to {OUT}")


if __name__ == "__main__":
    main()
