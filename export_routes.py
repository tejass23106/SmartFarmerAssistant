"""Admin exports: PDF summary report and Excel workbook. Both read the database at request time."""
import io
from datetime import datetime

from flask import send_file, session

from utils.activity import log_activity
from utils.analytics import build as build_analytics
from utils.database import get_db
from utils.helpers import role_required


def _pdf(data, when):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    green = colors.HexColor("#1b6b3e")
    def table(head, body):
        t = Table([head] + body if body else [head, ["-"] * len(head)], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), green), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c9d8c9")), ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f8f1")])]))
        return t
    tot = data["totals"]
    story = [Paragraph("Smart Farmer Assistant - Admin summary", ss["Title"]),
             Paragraph(f"Generated {when} from the live database.", ss["Normal"]), Spacer(1, 6),
             table(["Measure", "Value"], [[k.replace("_", " ").capitalize(), str(v)] for k, v in tot.items()]), Spacer(1, 10),
             Paragraph("Disease detections by result", ss["Heading3"]),
             table(["Disease", "Count"], [[str(a), str(b)] for a, b in data["charts"]["diseases"]]), Spacer(1, 8),
             Paragraph("Most recommended crops", ss["Heading3"]),
             table(["Crop", "Times recommended"], [[str(a), str(b)] for a, b in data["charts"]["rec_crops"]]), Spacer(1, 8),
             Paragraph("Disease reports by crop", ss["Heading3"]),
             table(["Crop", "Reports"], [[str(a), str(b)] for a, b in data["charts"]["rep_crop"]]), Spacer(1, 8),
             Paragraph("Recent disease reports", ss["Heading3"]),
             table(["#", "Date", "Farmer", "Crop", "Disease", "Status"],
                   [[str(r["id"]), r["report_date"], r["full_name"], r["crop_name"], r["disease_name"], r["status"]]
                    for r in data["recent_reports"]])]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                      title="Smart Farmer Assistant - Admin summary").build(story)
    return buf.getvalue()


def _xlsx(conn, when):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1B6B3E")

    def sheet(title, headers, rows):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
        for r in rows:
            ws.append(list(r))
        ws.freeze_panes = "A2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(42, max(10, max(len(str(c.value or "")) for c in col) + 2))
        return ws

    data = build_analytics(conn)
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Smart Farmer Assistant - summary", f"generated {when}"])
    for k, v in data["totals"].items():
        summary.append([k.replace("_", " ").capitalize(), v])
    sheet("Reports", ["ID", "Report date", "Farmer", "Email", "Crop", "Disease", "Location", "Status", "Confidence %"],
          [(r["id"], r["report_date"], r["full_name"], r["email"], r["crop_name"], r["disease_name"], r["location"], r["status"],
            r["confidence"]) for r in conn.execute(
              "SELECT r.*, u.full_name, u.email FROM disease_reports r JOIN users u ON u.id=r.user_id ORDER BY r.id LIMIT 50000")])
    sheet("Farmers", ["ID", "Name", "Email", "Phone", "Location", "Active", "Registered", "Last login", "Reports"],
          [(r["id"], r["full_name"], r["email"], r["phone"], r["location"], "yes" if r["is_active"] else "no", r["created_at"],
            r["last_login"], r["n"]) for r in conn.execute(
              "SELECT u.*, (SELECT COUNT(*) FROM disease_reports d WHERE d.user_id=u.id) n FROM users u WHERE role='farmer' ORDER BY u.id")])
    sheet("Predictions", ["ID", "Farmer", "Crop", "Disease", "Confidence %", "Created"],
          [(r["id"], r["full_name"], r["crop_name"], r["disease_name"], r["confidence"], r["created_at"]) for r in conn.execute(
              "SELECT p.*, u.full_name FROM predictions p JOIN users u ON u.id=p.user_id ORDER BY p.id LIMIT 50000")])
    sheet("Recommendations", ["ID", "Farmer", "Mode", "Best crop", "Score %", "Season", "Created"],
          [(r["id"], r["full_name"], r["mode"], r["top_crop"], r["top_score"], r["season"], r["created_at"]) for r in conn.execute(
              "SELECT r.*, u.full_name FROM recommendations r JOIN users u ON u.id=r.user_id ORDER BY r.id LIMIT 50000")])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def register(app):

    @app.route("/admin/export/pdf")
    @role_required("admin")
    def admin_export_pdf():
        when = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        try:
            data = build_analytics(conn)
            log_activity(conn, session["user_id"], "admin", "export", "pdf")
            conn.commit()
        finally:
            conn.close()
        return send_file(io.BytesIO(_pdf(data, when)), mimetype="application/pdf", as_attachment=True,
                         download_name=f"smart_farmer_summary_{datetime.now():%Y%m%d}.pdf")

    @app.route("/admin/export/excel")
    @role_required("admin")
    def admin_export_excel():
        when = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        try:
            content = _xlsx(conn, when)
            log_activity(conn, session["user_id"], "admin", "export", "excel")
            conn.commit()
        finally:
            conn.close()
        return send_file(io.BytesIO(content), as_attachment=True,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         download_name=f"smart_farmer_data_{datetime.now():%Y%m%d}.xlsx")
