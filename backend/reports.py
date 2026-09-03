"""Month-end owner report pack: colour-coded PDFs plus PNG images for WhatsApp.

Four reports, every one sorted floor -> flat number:
  1. Water usage charges — as per meter readings
  2. Total water purchases for the month
  3. Recurring entries monthly report
  4. Water reconciliation — owner statement
"""

import io
import zipfile

import fitz  # pymupdf, used to rasterise pages for WhatsApp images
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import xlsx as X
from engine import PAYMENT_STATUS_LABELS as STATUS_LABELS

NAVY = colors.HexColor("#1F3864")
BLUE = colors.HexColor("#2F5597")
TOTAL_BG = colors.HexColor("#C9D7EE")
GREY = colors.HexColor("#B9C4D4")
RED = colors.HexColor("#C00000")
GREEN = colors.HexColor("#1F7A3D")

REPORTS = ("meters", "purchases", "recurring", "reconciliation")
REPORT_TITLES = {
    "meters": "Water usage charges — as per meter readings",
    "purchases": "Total water purchases for the month",
    "recurring": "Recurring entries — monthly report",
    "reconciliation": "Water reconciliation — owner statement",
}


def _hex(tint):
    return colors.HexColor(f"#{tint}")


def _table(head, rows, *, widths=None, fills=None, signed_col=None, total=False, group=None):
    data = ([group] if group else []) + [head] + rows
    off = 1 if group else 0
    tbl = Table(data, repeatRows=1 + off, colWidths=widths, hAlign="LEFT")
    style = [("GRID", (0, off), (-1, -1), 0.4, GREY),
             ("BACKGROUND", (0, off), (-1, off), NAVY),
             ("TEXTCOLOR", (0, off), (-1, off), colors.white),
             ("FONTNAME", (0, off), (-1, off), "Helvetica-Bold"),
             ("FONTSIZE", (0, 0), (-1, -1), 7.5),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 4),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("ALIGN", (4, 1 + off), (-1, -1), "RIGHT")]
    if group:
        # the group band: one merged cap over the columns it covers
        first = next(i for i, v in enumerate(group) if v)
        last = max(i for i, v in enumerate(group) if v is not None and v != "") if any(group) else first
        span_end = first
        for i in range(first + 1, len(group)):
            if group[i] == "":
                span_end = i
            else:
                break
        style += [("SPAN", (first, 0), (span_end, 0)),
                  ("BACKGROUND", (first, 0), (span_end, 0), BLUE),
                  ("TEXTCOLOR", (first, 0), (span_end, 0), colors.white),
                  ("FONTNAME", (first, 0), (span_end, 0), "Helvetica-Bold"),
                  ("ALIGN", (first, 0), (span_end, 0), "CENTER"),
                  ("GRID", (first, 0), (span_end, 0), 0.4, GREY)]
        del last
    for i, tint in enumerate(fills or [], start=1 + off):
        if tint:
            style.append(("BACKGROUND", (0, i), (-1, i), _hex(tint)))
    if total:
        style += [("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), TOTAL_BG),
                  ("FONTNAME", (0, len(data) - 1), (-1, len(data) - 1), "Helvetica-Bold")]
    if signed_col is not None:
        for i, r in enumerate(rows, start=1 + off):
            v = r[signed_col]
            if isinstance(v, (int, float)) and v:
                style.append(("TEXTCOLOR", (signed_col, i), (signed_col, i), RED if v > 0 else GREEN))
    tbl.setStyle(TableStyle(style))
    return tbl


def _legend(pairs):
    rows = [[k, v] for k, v in pairs]
    tbl = Table(rows, hAlign="LEFT", colWidths=[95 * mm, 45 * mm])
    tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GREY),
                             ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                             ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    return tbl


def _money(v):
    return f"{float(v or 0):,.2f}"


def build_sections(which, stmt, month_label, tankers, flat_name, dmy, styles):
    """Return the flowables for one report. Rows are already floor -> flat sorted by the engine."""
    t = stmt["totals"]
    flats_pal = X.Palette(X.OWNER_TINTS)   # one colour per flat, shared by its meters
    payers = X.Palette(X.PAYER_TINTS)
    out = [Paragraph(f"<para align=center><b>{REPORT_TITLES[which]} — {stmt['property']['name']}</b></para>",
                     styles["Heading2"]),
           Paragraph(f"<para align=center>For the month of {month_label}</para>", styles["Normal"]),
           Spacer(1, 10)]

    if which == "meters":
        combined = {}
        for m in stmt["meters"]:
            combined[m.get("flat_id")] = round(combined.get(m.get("flat_id"), 0) + float(m.get("charge") or 0), 2)
        head = ["S.No", "Floor", "House", "Owner", "Meter number", "Starting\nunit", "Ending\nunit",
                "Consumed\nunits", "Water\ncharges", "Total\nAmount"]
        rows, fills = [], []
        seen = set()
        for i, m in enumerate(stmt["meters"], start=1):
            fid = m.get("flat_id")
            first = fid not in seen
            seen.add(fid)
            rows.append([i, (m.get("floor", "") or "—") if first else "", m.get("flat_number", "") if first else "",
                         m.get("owner_name", "") if first else "",
                         m.get("label", ""), _money(m.get("opening")),
                         "—" if m.get("closing") is None else _money(m.get("closing")),
                         _money(m.get("consumption")), _money(m.get("charge")),
                         _money(combined.get(fid)) if first else ""])
            fills.append(flats_pal.tint(fid, f"Flat {m.get('flat_number')}"))
        rows.append(["", "", "", "", "TOTAL", "", "", _money(t["total_consumed"]), _money(t["metered_charges"]), ""])
        out += [_table(head, rows, fills=fills, total=True), Spacer(1, 10),
                _legend([("Total lorries this month", t["tanker_count"]),
                         ("Total water received (L)", _money(t["total_litres"])),
                         ("Total water cost (lorry + tips)", _money(t["total_water_spend"])),
                         ("Cost per litre of water", f"{t['avg_cost_per_litre']:.4f}"),
                         ("Total units consumed (as per meter)", _money(t["total_consumed"])),
                         ("Total water charges (metered)", _money(t["metered_charges"])),
                         ("Total non-metered consumption (L)", _money(t["reserve_litres"])),
                         ("Total non-metered cost", _money(t["reserve_value"])),
                         (f"Non-metered cost split between {t['flat_count']} houses — per house share",
                          _money(t["reserve_share"]))])]

    elif which == "purchases":
        head = ["S.No", "Booking\ndate", "Delivery\ndate", "Supplier", "Sump (L)", "Syntex (L)", "Total (L)",
                "Lorry\namount", "Tips", "Total\ncost", "Cost / L", "Lorry paid by", "Tips paid by"]
        rows, fills = [], []
        used = set()
        for i, tk in enumerate(tankers, start=1):
            litres = float(tk.get("qty_sump", 0) or 0) + float(tk.get("qty_syntex", 0) or 0)
            tips = float(tk.get("tips_amount", 0) or 0)
            cost = float(tk.get("amount", 0) or 0) + tips
            payer = flat_name.get(tk.get("payer_flat_id"), "—")
            tips_payer = flat_name.get(tk.get("tips_payer_flat_id") or tk.get("payer_flat_id"), "—")
            rows.append([i, dmy(tk.get("booking_date")), dmy(tk.get("date")), tk.get("supplier", ""),
                         _money(tk.get("qty_sump")), _money(tk.get("qty_syntex")), _money(litres),
                         _money(tk.get("amount")), _money(tips), _money(cost),
                         f"{(cost / litres if litres else 0):.4f}",
                         f"{payer} ({tk.get('payer_type', '')})",
                         f"{tips_payer} ({tk.get('tips_payer_type') or tk.get('payer_type', '')})" if tips else "—"])
            payers.fill(tk.get("payer_flat_id"), f"Flat {payer}")
            used.add(tk.get("payer_flat_id"))
            fills.append(payers.tint(tk.get("payer_flat_id"), f"Flat {payer}"))
        rows.append(["", "", "", "TOTAL", "", "", _money(t["total_litres"]),
                     _money(t["total_water_spend"] - t["total_tips"]), _money(t["total_tips"]),
                     _money(t["total_water_spend"]), f"{t['avg_cost_per_litre']:.4f}", "", ""])
        out += [_table(head, rows, fills=fills, total=True), Spacer(1, 10),
                _legend([("Total expense for the month", _money(t["total_water_spend"])),
                         ("Split between (no. of houses)", t["flat_count"]),
                         ("Expense per head",
                          _money(t["total_water_spend"] / (t["flat_count"] or 1)))])]

    elif which == "recurring":
        head = ["S.No", "Type", "Description", "Person", "Amount", "Fronted by", "As", "Date"]
        rows, fills = [], []
        used = set()
        items = stmt.get("recurring_items", [])
        for i, c in enumerate(items, start=1):
            payer = flat_name.get(c.get("payer_flat_id"), "—")
            rows.append([i, str(c.get("charge_type", "")).title(), c.get("description", "") or "—",
                         c.get("person_name", "") or "—", _money(c.get("amount")), payer,
                         str(c.get("payer_type", "")).title(), dmy(c.get("date"))])
            payers.fill(c.get("payer_flat_id"), f"Flat {payer}")
            used.add(c.get("payer_flat_id"))
            fills.append(payers.tint(c.get("payer_flat_id"), f"Flat {payer}"))
        rows.append(["", "TOTAL", "", "", _money(t["recurring_total"]), "", "", ""])
        out += [_table(head, rows, fills=fills, total=True), Spacer(1, 10),
                _legend([("Total recurring expense", _money(t["recurring_total"])),
                         ("Split between (no. of houses)", t["flat_count"]),
                         ("Expense per head (recurring)", _money(t["recurring_share"]))])]

    else:  # reconciliation
        head = ["S.No", "Flat\nNo.", "Floor", "Owner", "Metered", "Non-Metered\n(in storage)",
                "Total Water\ncost", "Flat-\nspecific", "Misc", "Total\namount", "Bal brought\nforward",
                "Advance payment\npaid by", "Amount\npaid", "Balance to\npay / receive",
                "Date of\npayment", "Paid\nby", "Status"]
        widths = [8 * mm, 10 * mm, 11 * mm, 28 * mm, 15 * mm, 18 * mm, 16 * mm, 14 * mm, 13 * mm,
                  16 * mm, 17 * mm, 21 * mm, 15 * mm, 18 * mm, 16 * mm, 10 * mm, 20 * mm]
        rows, fills = [], []
        for i, r in enumerate(stmt["rows"], start=1):
            rows.append([i, r["flat_number"], r.get("floor", "") or "—", r["owner_name"],
                         _money(r["water_own_cost"]), _money(r["reserve_share"]), _money(r["water_cost"]),
                         _money(r.get("flat_specific", 0)),
                         _money(r["recurring_share"] + r["maintenance_share"]), _money(r["base_cost"]),
                         _money(r["carry_in"]), _money(r["contributions"]), _money(r["received"]),
                         _money(r["net"]), dmy(r.get("last_paid_on")),
                         str(r.get("last_paid_by") or "").title() or "—",
                         STATUS_LABELS.get(r.get("payment_status"), "Pending")])
            fills.append(flats_pal.tint(r["flat_id"], f"Flat {r['flat_number']}"))
        rows.append(["", "", "", "TOTAL", _money(t["total_water_spend"] - t["reserve_value"]),
                     _money(t["reserve_value"]), _money(t["total_water_spend"]),
                     _money(t["flat_specific_total"]),
                     _money(t["recurring_total"] + t["maintenance_total"]), _money(t["billable_total"]),
                     _money(t["total_carry_in"]), _money(t["total_contributions"]),
                     _money(t["total_received"]), _money(t["net_position"]), "", "", ""])
        out += [_table(head, rows, widths=widths, fills=fills, total=True,
                       group=[None, None, None, None, "Water Charges", "", "",
                              None, None, None, None, None, None, None, None, None, None]),
                Spacer(1, 10),
                _legend([("Total expense for the month", _money(t["billable_total"])),
                         ("Split between (no. of houses)", t["flat_count"]),
                         ("Expense per head", _money(t["billable_total"] / (t["flat_count"] or 1))),
                         ("Total receivable (owes)", _money(t["total_owes"])),
                         ("Total payable (owed to owners)", _money(t["total_owed"])),
                         ("Net position", _money(t["net_position"]))])]

    return out


def build_pdf(stmt, month_label, tankers, flat_name, dmy, which=("all",), cover=True):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"SocietyHub — {stmt['property']['name']} — {month_label}")
    styles = getSampleStyleSheet()
    wanted = REPORTS if "all" in which else [w for w in REPORTS if w in which]
    story = []

    if cover and len(wanted) > 1:
        t = stmt["totals"]
        story += [Spacer(1, 40),
                  Paragraph(f"<b>{stmt['property']['name']}</b>", styles["Title"]),
                  Paragraph(f"Month-end owner report pack · {month_label}", styles["Heading2"]),
                  Spacer(1, 16),
                  _legend([("Reports in this pack", len(wanted)),
                           ("Houses", t["flat_count"]),
                           ("Water purchased (L)", _money(t["total_litres"])),
                           ("Total water cost", _money(t["total_water_spend"])),
                           ("Recurring charges", _money(t["recurring_total"])),
                           ("One-time / repairs", _money(t["maintenance_total"])),
                           ("Total billed to houses", _money(t["billable_total"])),
                           ("Collected", _money(t["total_received"])),
                           ("Net outstanding", _money(t["net_position"]))]),
                  Spacer(1, 16),
                  Paragraph("Each owner's flat carries its own colour so a line can be traced at a glance.",
                            styles["Normal"])]

    for w in wanted:
        if story:
            story.append(PageBreak())
        story += build_sections(w, stmt, month_label, tankers, flat_name, dmy, styles)

    doc.build(story)
    buf.seek(0)
    return buf


def pdf_to_png(pdf_bytes: bytes, dpi: int = 130) -> io.BytesIO:
    """Stack every page into one tall PNG — easy to send on WhatsApp."""
    from PIL import Image
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    imgs = []
    for page in d:
        pix = page.get_pixmap(dpi=dpi)
        imgs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    width = max(i.width for i in imgs)
    height = sum(i.height for i in imgs)
    sheet = Image.new("RGB", (width, height), "white")
    y = 0
    for i in imgs:
        sheet.paste(i, (0, y))
        y += i.height
    out = io.BytesIO()
    sheet.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def build_zip(files) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    buf.seek(0)
    return buf
