"""
routers/reports.py — HTTP surface for report CRUD.

One-to-one translation of the report endpoints from the original Express
server.ts. The router is thin: it parses/validates requests, calls ReportService
or the HTML renderer, and maps domain exceptions to HTTP status codes. All file
handling lives in app.reports.service; all rendering in app.reports.html_export.

Endpoint parity with server.ts:
  POST   /api/reports                     save or update  (409 on duplicate)
  GET    /api/reports                      list, newest first
  GET    /api/reports/content/{filename}   fetch parsed JSON  (404 if missing)
  GET    /api/reports/download/{filename}  download raw file
  GET    /api/download?filename=           download (query-param variant)
  GET    /api/html?filename=               standalone HTML export
  DELETE /api/delete/{filename}            delete json+md pair
  DELETE /api/delete?incident_id=          delete latest for an incident
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.reports.html_export import render_report_html
from app.reports.service import (
    DuplicateReportError,
    InvalidFilenameError,
    ReportNotFoundError,
    ReportService,
)
from app.shared.schema import (
    ReportListResponse,
    SaveReportRequest,
    SaveReportResponse,
)

router = APIRouter(tags=["reports"])


def get_service(request: Request) -> ReportService:
    """Resolve the ReportService created in the app lifespan (see main.py)."""
    return request.app.state.report_service


# ── save / update ─────────────────────────────────────────────────────────────


@router.post("/api/reports", response_model=SaveReportResponse)
def save_report(
    body: SaveReportRequest,
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    try:
        result = service.save(
            report=body.report,
            markdown=body.markdown,
            editing_filename=body.editingFilename,
        )
        return JSONResponse(result)
    except DuplicateReportError as exc:
        # Matches the TS 409 body: { incident_id, message }.
        return JSONResponse(
            status_code=409,
            content={"incident_id": exc.incident_id, "message": str(exc)},
        )
    except OSError:
        raise HTTPException(status_code=500, detail="Failed to save report")


# ── list ──────────────────────────────────────────────────────────────────────


@router.get("/api/reports", response_model=ReportListResponse)
def list_reports(service: ReportService = Depends(get_service)) -> ReportListResponse:
    return ReportListResponse(reports=service.list_reports())


# ── read content ──────────────────────────────────────────────────────────────


@router.get("/api/reports/content/{filename}")
def get_report_content(
    filename: str,
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    try:
        return JSONResponse(service.get_content(filename))
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report file not found")
    except InvalidFilenameError:
        raise HTTPException(status_code=400, detail="Invalid filename")


# ── download ──────────────────────────────────────────────────────────────────


@router.get("/api/reports/download/{filename}")
def download_report(
    filename: str,
    service: ReportService = Depends(get_service),
) -> FileResponse:
    return _download(filename, service)


@router.get("/api/download")
def download_report_query(
    filename: str = Query(...),
    service: ReportService = Depends(get_service),
) -> FileResponse:
    return _download(filename, service)


def _download(filename: str, service: ReportService) -> FileResponse:
    try:
        path = service.resolve_path(filename)
        return FileResponse(path, filename=filename)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report file not found")
    except InvalidFilenameError:
        raise HTTPException(status_code=400, detail="Invalid filename")


# ── HTML export ───────────────────────────────────────────────────────────────


@router.get("/api/html")
def export_html(
    filename: str = Query(...),
    service: ReportService = Depends(get_service),
) -> HTMLResponse:
    try:
        report = service.get_content(filename)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report file not found")
    except InvalidFilenameError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    html = render_report_html(report)
    incident_id = (report.get("metadata") or {}).get("incident_id") or "export"
    return HTMLResponse(
        content=html,
        headers={
            "Content-Disposition": f'attachment; filename="report-{incident_id}.html"',
        },
    )


# ── delete ────────────────────────────────────────────────────────────────────


@router.delete("/api/delete/{filename}")
def delete_report(
    filename: str,
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    return _delete(service, filename=filename)


@router.delete("/api/delete")
def delete_report_by_incident(
    incident_id: str | None = Query(default=None),
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    return _delete(service, incident_id=incident_id)


def _delete(
    service: ReportService,
    filename: str | None = None,
    incident_id: str | None = None,
) -> JSONResponse:
    try:
        service.delete(filename=filename, incident_id=incident_id)
        return JSONResponse(
            {"success": True, "message": "Report deleted successfully"}
        )
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found")
    except InvalidFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
