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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from app.auth.dependencies import current_user, require_analyst
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

# Authentication is applied at the *router*, not per endpoint.
#
# Before this phase the whole reports surface was unauthenticated: an audit of
# every route found `DELETE /api/delete/{filename}` returning 200 with no token,
# so anyone who could reach the port could destroy incident records. Declaring
# the dependency here means a future endpoint is protected by default and has to
# opt *out* deliberately, rather than being exposed by omission.
#
# Reads require any authenticated user; writes are narrowed to analyst/admin on
# the individual routes below, since viewer is a read-only role.
router = APIRouter(tags=["reports"], dependencies=[Depends(current_user)])


def get_service(request: Request) -> ReportService:
    """Resolve the ReportService created in the app lifespan (see main.py)."""
    return request.app.state.report_service


# ── save / update ─────────────────────────────────────────────────────────────


@router.post(
    "/api/reports",
    response_model=SaveReportResponse,
    # Creating and editing reports is a writer action; viewer is read-only.
    dependencies=[Depends(require_analyst)],
)
def save_report(
    body: SaveReportRequest,
    request: Request,
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    try:
        result = service.save(
            report=body.report,
            markdown=body.markdown,
            editing_filename=body.editingFilename,
        )
        # A saved report should be answerable immediately. Re-index in the
        # background so the writer isn't made to wait for embedding.
        chatbot = getattr(request.app.state, "chatbot", None)
        if chatbot is not None:
            return JSONResponse(result, background=BackgroundTask(chatbot.refresh))
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
) -> Response:
    return _download(filename, service)


@router.get("/api/download")
def download_report_query(
    filename: str = Query(...),
    service: ReportService = Depends(get_service),
) -> Response:
    return _download(filename, service)


# Content types by extension. Reports are only ever .json or .md; anything else
# downloads as a generic attachment rather than being guessed at.
_CONTENT_TYPES = {
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
}


def _download(filename: str, service: ReportService) -> Response:
    """Stream a report's bytes.

    Reads through the service rather than handing a path to FileResponse: the
    bytes may live in object storage, where there is no local path. The
    Content-Disposition header keeps the browser's "save as" behaviour that
    FileResponse(filename=...) provided.
    """
    try:
        data = service.read_bytes(filename)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report file not found")
    except InvalidFilenameError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    suffix = filename[filename.rfind(".") :] if "." in filename else ""
    return Response(
        content=data,
        media_type=_CONTENT_TYPES.get(suffix, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@router.delete("/api/delete/{filename}", dependencies=[Depends(require_analyst)])
def delete_report(
    filename: str,
    request: Request,
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    return _delete(service, request, filename=filename)


@router.delete("/api/delete", dependencies=[Depends(require_analyst)])
def delete_report_by_incident(
    request: Request,
    incident_id: str | None = Query(default=None),
    service: ReportService = Depends(get_service),
) -> JSONResponse:
    return _delete(service, request, incident_id=incident_id)


def _delete(
    service: ReportService,
    request: Request,
    filename: str | None = None,
    incident_id: str | None = None,
) -> JSONResponse:
    try:
        service.delete(filename=filename, incident_id=incident_id)
        # Drop the deleted report from the index so it can no longer be cited.
        chatbot = getattr(request.app.state, "chatbot", None)
        body = {"success": True, "message": "Report deleted successfully"}
        if chatbot is not None:
            return JSONResponse(body, background=BackgroundTask(chatbot.refresh))
        return JSONResponse(body)
    except ReportNotFoundError:
        raise HTTPException(status_code=404, detail="Report not found")
    except InvalidFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
