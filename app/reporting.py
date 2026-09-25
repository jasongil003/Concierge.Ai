from __future__ import annotations

from io import BytesIO
import json
import re
import time
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


SHEET_NAMES = [
    "Executive Summary", "Guest Activity", "AI Performance", "Service Requests",
    "Department Performance", "Top Guest Questions", "Recommendations", "Raw Data",
]


def _cell_ref(column: int, row: int) -> str:
    letters = ""
    number = column
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _sheet_xml(rows: list[list[Any]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, 1):
        cells: list[str] = []
        for column_index, value in enumerate(row, 1):
            reference = _cell_ref(column_index, row_index)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{reference}"><v>{value}</v></c>')
            else:
                text = escape("" if value is None else str(value))
                style = ' s="1"' if row_index == 1 else ""
                cells.append(f'<c r="{reference}" t="inlineStr"{style}><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>"


def build_xlsx(sheets: dict[str, list[list[Any]]]) -> bytes:
    output = BytesIO()
    names = [name for name in SHEET_NAMES if name in sheets]
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(names) + 1)) + "</Types>")
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1)) + "</sheets></workbook>")
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(names) + 1)) + f'<Relationship Id="rId{len(names)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0"/><xf fontId="1" fillId="0" borderId="0" applyFont="1"/></cellXfs></styleSheet>')
        for index, name in enumerate(names, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheets[name]))
    return output.getvalue()


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(title: str, subtitle: str, sections: list[tuple[str, list[str]]]) -> bytes:
    lines: list[tuple[str, int]] = [(title, 18), (subtitle, 9), ("", 9)]
    for heading, values in sections:
        lines.append((heading, 12))
        for value in values:
            clean = re.sub(r"\s+", " ", str(value)).strip()
            while len(clean) > 92:
                split = clean.rfind(" ", 0, 92)
                split = split if split > 30 else 92
                lines.append((clean[:split], 9))
                clean = clean[split:].strip()
            lines.append((clean, 9))
        lines.append(("", 7))
    pages = [lines[index:index + 55] for index in range(0, len(lines), 55)] or [[]]
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects.append(f'<< /Type /Pages /Kids [{" ".join(f"{item} 0 R" for item in page_ids)}] /Count {len(page_ids)} >>'.encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page_index, page in enumerate(pages):
        content_id = page_ids[page_index] + 1
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        y = 750
        commands = ["BT"]
        for text, size in page:
            commands.append(f"/F1 {size} Tf 46 {y} Td ({_pdf_escape(text)}) Tj")
            y_delta = 20 if size >= 12 else 14
            commands.append(f"-46 -{y_delta} Td")
            y -= y_delta
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return output.getvalue()


class ReportService:
    def workbook(self, property_name: str, analytics: dict[str, Any], recommendations: list[str]) -> bytes:
        summary = analytics["summary"]
        raw = analytics.get("raw_requests", [])
        sheets = {
            "Executive Summary": [["Property", property_name], ["Period", analytics["period"]], ["Generated", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())], [], ["Metric", "Value"], *[[key.replace("_", " ").title(), value] for key, value in summary.items()]],
            "Guest Activity": [["Timestamp", "Requests"], *[[time.strftime("%Y-%m-%d %H:%M", time.gmtime(item["timestamp"])), item["value"]] for item in analytics["request_volume"]]],
            "AI Performance": [["Metric", "Value"], *[[key.replace("_", " ").title(), value] for key, value in analytics["ai"].items() if key != "provider_usage"], [], ["Provider", "Responses"], *[[key, value] for key, value in analytics["ai"]["provider_usage"].items()]],
            "Service Requests": [["Request ID", "Request type", "Description", "Department", "Status", "Priority", "Created", "Updated"], *[[item.get("request_id"), item.get("request_type"), item.get("description"), item.get("department"), item.get("status"), item.get("priority"), item.get("created_at"), item.get("updated_at")] for item in raw]],
            "Department Performance": [["Department", "Requests"], *[[item["name"], item["value"]] for item in analytics["requests_by_department"]]],
            "Top Guest Questions": [["Question", "Count"], *[[item["question"], item["count"]] for item in analytics["top_questions"]]],
            "Recommendations": [["Recommendation"], *[[item] for item in recommendations]],
            "Raw Data": [["Dataset", "JSON"], ["analytics", json.dumps(analytics, default=str, separators=(",", ":"))]],
        }
        return build_xlsx(sheets)

    def management_pdf(self, property_name: str, analytics: dict[str, Any], alerts: list[dict[str, Any]], recommendations: list[str]) -> bytes:
        summary = analytics["summary"]
        sections = [
            ("Executive summary", [f"Guests assisted: {summary['guests_assisted']}. AI conversations: {summary['ai_conversations']}. Service requests: {summary['service_requests']}."]),
            ("Guest engagement", [f"Request change versus the previous period: {summary['request_change_percent'] if summary['request_change_percent'] is not None else 'Not enough prior data'}%.", *[f"{item['question']} ({item['count']})" for item in analytics["top_questions"][:5]]]),
            ("Service performance", [f"Open requests: {summary['open_requests']}. Overdue: {summary['overdue_requests']}. SLA performance: {summary['sla_performance_percent']}%. Average resolution: {summary['average_resolution_seconds'] or 'Unavailable'} seconds.", *[f"{item['name']}: {item['value']} request(s)" for item in analytics["requests_by_department"]]]),
            ("AI performance", [f"Provider requests: {analytics['ai']['requests']}. Errors: {analytics['ai']['errors']}. Average latency: {analytics['ai']['average_latency_ms'] or 'Unavailable'} ms. Fallback rate: {summary['fallback_rate_percent']}%. Estimated cloud cost: unavailable unless verified provider pricing and billable usage are configured."]),
            ("Operational issues", [alert["title"] + ": " + alert["evidence"] for alert in alerts] or ["No active threshold-based alerts were detected for this period."]),
            ("Important trends", [f"Service-request change versus the previous comparable period: {summary['request_change_percent']}%." if summary["request_change_percent"] is not None else "A prior comparable request baseline is not available.", *[f"Busiest interval {time.strftime('%Y-%m-%d %H:%M', time.gmtime(item['timestamp']))}: {item['requests']} request(s)." for item in analytics.get("busiest_periods", [])[:3]]]),
            ("Recommendations", recommendations or ["Continue monitoring operational trends; no evidence-backed recommendation is currently available."]),
        ]
        return build_pdf(f"{property_name} Management Report", f"Reporting period: {analytics['period']} · Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", sections)
