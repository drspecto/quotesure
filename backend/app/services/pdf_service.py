"""Makes a professional quotation PDF the owner can send to the customer."""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import models

# The default PDF fonts have no ₹ symbol (it prints as a black box), so we write "Rs."


def _money(x: float) -> str:
    return f"Rs. {x:,.2f}"


def quotation_pdf(q: models.Quotation, factory_name: str) -> bytes:
    """Returns the PDF file as bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(factory_name, styles["Title"]))
    story.append(Paragraph("QUOTATION", styles["Heading2"]))
    story.append(Spacer(1, 4 * mm))

    info = [
        ["Quotation No.", f"Q-{q.id:04d}"],
        ["Date", q.created_at.strftime("%d %b %Y")],
        ["Valid until", q.valid_until.strftime("%d %b %Y") if q.valid_until else "-"],
        ["Customer", q.customer_name],
    ]
    info_table = Table(info, colWidths=[40 * mm, 110 * mm])
    info_table.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    story.append(info_table)
    story.append(Spacer(1, 8 * mm))

    unit_price = q.quoted_price / q.quantity
    items = [
        ["Item", "Material", "Qty", "Unit price", "Amount"],
        [q.part_name, f"{q.material.name} {q.material.grade}", f"{q.quantity:,}",
         _money(unit_price), _money(q.quoted_price)],
        ["", "", "", "Total", _money(q.quoted_price)],
    ]
    items_table = Table(items, colWidths=[40 * mm, 45 * mm, 18 * mm, 30 * mm, 37 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
        ("LINEABOVE", (3, -1), (-1, -1), 1, colors.black),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10 * mm))

    terms = [
        "Prices are exclusive of GST.",
        f"Raw material is priced at {_money(q.material_price_used)}/kg. "
        "Prices are valid only until the date above because raw material prices change; "
        "after that the quotation will be revised.",
        "Payment terms: as agreed.",
    ]
    story.append(Paragraph("Terms", styles["Heading4"]))
    for t in terms:
        story.append(Paragraph(f"&bull; {t}", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
