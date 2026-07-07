"""
reports/html_export.py — render a stored report to a standalone HTML document.

Faithful port of the `/api/html` handler in the original server.ts. Produces the
same inline-styled, self-contained HTML the frontend expects for download.

Kept separate from the router and from service.py because it is pure rendering:
report dict in, HTML string out. No I/O, no framework.
"""

from __future__ import annotations

from html import escape

_STANDARD_FIELDS = {
    "incident_id",
    "title",
    "caller",
    "category",
    "subcategory",
    "date",
}

_PAGE_STYLE = """
    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; color: #333; }
    h1 { color: #1f2937; border-bottom: 3px solid #3b82f6; padding-bottom: 10px; }
    h2 { color: #374151; margin-top: 30px; }
    h3 { color: #6b7280; }
    .metadata { background: #f3f4f6; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    .metadata-item { margin: 8px 0; }
    .metadata-label { font-weight: bold; color: #1f2937; }
    img { max-width: 100%; height: auto; margin: 15px 0; border: 1px solid #d1d5db; border-radius: 5px; }
    code { background: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
    pre { background: #1f2937; color: #e5e7eb; padding: 15px; border-radius: 5px; overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; margin: 15px 0; }
    th, td { border: 1px solid #d1d5db; padding: 12px; text-align: left; }
    th { background: #f3f4f6; font-weight: bold; }
    blockquote { border-left: 4px solid #3b82f6; padding-left: 15px; margin-left: 0; color: #6b7280; }
    ul, ol { margin: 10px 0; }
    .page-break { page-break-after: always; margin: 30px 0; }
"""

_TITLE_H3 = '<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">{}</h3>'


def _title_heading(block: dict) -> str:
    title = block.get("title")
    return _TITLE_H3.format(escape(title)) if title else ""


def _render_code_block(block: dict) -> str:
    out = ""
    for item in block.get("items", []):
        if item.get("type") == "code":
            code = (
                '<div style="background: #111827; padding: 1rem; border-radius: 0.375rem; '
                'margin: 1rem 0; border: 1px solid #374151; overflow-x: auto;">'
            )
            if item.get("title"):
                code += (
                    '<h2 style="background: #2563eb; color: white; padding: 0.5rem; '
                    'margin: -1rem -1rem 0.5rem -1rem; border-radius: 0.375rem 0.375rem 0 0; '
                    f'font-size: 0.875rem;">{escape(item["title"])}</h2>'
                )
            if item.get("header"):
                code += (
                    '<h3 style="color: white; margin: 0 0 0.5rem 0; font-size: 1rem;">'
                    f'{escape(item["header"])}</h3>'
                )
            code += (
                '<div style="font-size: 0.75rem; color: #9ca3af; margin-bottom: 0.5rem;">'
                f'Language: {escape(item.get("language") or "text")}</div>'
            )
            content = (item.get("content") or "").replace("<", "&lt;").replace(">", "&gt;")
            code += (
                '<pre style="margin: 0;"><code style="color: #4ade80; '
                f'font-family: monospace; font-size: 0.875rem;">{content}</code></pre></div>'
            )
            out += code
        elif item.get("type") == "description":
            desc = (
                '<div style="margin: 1rem 0; border: 1px solid #e5e7eb; '
                'border-radius: 0.375rem; overflow: hidden;">'
            )
            if item.get("title"):
                desc += (
                    '<h2 style="background: #a855f7; color: white; padding: 0.5rem; '
                    f'margin: 0; font-size: 0.875rem;">{escape(item["title"])}</h2>'
                )
            desc += (
                '<div style="padding: 1rem; color: #1f2937;">'
                f'{item.get("content") or ""}</div></div>'
            )
            out += desc
    return out


def render_report_html(report: dict) -> str:
    """Return a full standalone HTML document string for a report dict."""
    metadata = report.get("metadata") or {}

    custom_items = [
        (
            '<div class="metadata-item">'
            f'<span class="metadata-label">{escape(key)}:</span> {escape(str(value))}</div>'
        )
        for key, value in metadata.items()
        if key not in _STANDARD_FIELDS and value
    ]
    custom_html = (
        '<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">'
        "Custom Fields</h3>" + "".join(custom_items)
        if custom_items
        else ""
    )

    title = metadata.get("title") or "Incident Report"
    subcategory = metadata.get("subcategory")
    subcategory_html = (
        f'<div class="metadata-item"><span class="metadata-label">Subcategory:</span> '
        f"{subcategory}</div>"
        if subcategory
        else ""
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>{_PAGE_STYLE}</style>
</head>
<body>
  <h1>{title}</h1>

  <div class="metadata">
    <div class="metadata-item"><span class="metadata-label">Incident ID:</span> {metadata.get("incident_id") or "N/A"}</div>
    <div class="metadata-item"><span class="metadata-label">Caller:</span> {metadata.get("caller") or "N/A"}</div>
    <div class="metadata-item"><span class="metadata-label">Date:</span> {metadata.get("date") or "N/A"}</div>
    <div class="metadata-item"><span class="metadata-label">Category:</span> {metadata.get("category") or "N/A"}</div>
    {subcategory_html}
    {custom_html}
  </div>

  <hr />
"""

    for block in report.get("blocks", []):
        btype = block.get("type")
        if btype == "heading":
            html += _title_heading(block)
            level = block.get("level") or 2
            html += f'<h{level}>{block.get("content") or ""}</h{level}>'
        elif btype == "paragraph":
            html += _title_heading(block)
            # Quill stores paragraph content as HTML; emit it directly.
            html += f'<div class="paragraph-content">{block.get("content") or "<p></p>"}</div>'
        elif btype == "image":
            html += _title_heading(block)
            if block.get("data_url"):
                html += (
                    f'<img src="{block["data_url"]}" '
                    f'alt="{block.get("caption") or "Image"}" />'
                )
        elif btype == "code":
            html += _render_code_block(block)
        elif btype == "table":
            html += _title_heading(block)
            headers = "".join(f"<th>{h}</th>" for h in block.get("headers", []))
            html += f"<table><thead><tr>{headers}</tr></thead><tbody>"
            for row in block.get("rows", []):
                cells = "".join(f"<td>{cell}</td>" for cell in row)
                html += f"<tr>{cells}</tr>"
            html += "</tbody></table>"
        elif btype == "list":
            html += _title_heading(block)
            label = block.get("label")
            items = "".join(f"<li>{item}</li>" for item in block.get("items", []))
            if label and label.strip():
                html += f"<blockquote><strong>{label}</strong><ul>{items}</ul></blockquote>"
            else:
                tag = "ol" if block.get("ordered") else "ul"
                html += f"<{tag}>{items}</{tag}>"
        elif btype == "incident_example":
            html += _title_heading(block)
            html += (
                '<div class="incident-example" style="background: #eff6ff; padding: 1rem; '
                'border-radius: 0.375rem; border: 1px solid #bfdbfe; margin: 1rem 0;">'
                '<h3 style="margin: 0 0 0.5rem 0; color: #1e40af;">'
                f'Incident example: {block.get("incident_id") or ""}</h3>'
            )
            if block.get("link"):
                link = block["link"]
                html += (
                    f'<p style="margin: 0;"><a href="{link}" '
                    'style="color: #2563eb; text-decoration: underline;" '
                    f'target="_blank" rel="noopener noreferrer">{link}</a></p>'
                )
            html += "</div>"

    html += "</body></html>"
    return html
