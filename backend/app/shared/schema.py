"""
schema.py — the shared incident-report contract.

This is the Python mirror of frontend/src/types.ts. It is the single source of
truth on the backend for the {metadata, blocks[]} report format that the
generator writes and the chatbot ingests. Keep this file in sync with types.ts;
any block field added on one side must be added on the other.

Design notes:
  - Blocks are a discriminated union keyed on `type` (Pydantic uses the literal
    `type` field as the discriminator), matching the TS ContentBlock union.
  - ReportMetadata allows arbitrary extra string fields to reproduce the TS
    `[key: string]: string` index signature (custom metadata fields the UI adds).
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# ── Blocks ────────────────────────────────────────────────────────────────────


class BaseBlock(BaseModel):
    id: str
    title: str | None = None


class HeadingBlock(BaseBlock):
    type: Literal["heading"]
    level: Literal[1, 2, 3, 4]
    content: str


class ParagraphBlock(BaseBlock):
    # content is Quill Delta JSON string, or plain text for backward compat.
    type: Literal["paragraph"]
    content: str


class ListBlock(BaseBlock):
    type: Literal["list"]
    ordered: bool
    items: list[str]
    # When set, the UI renders this list as a labelled description box.
    label: str | None = None


class IncidentExampleBlock(BaseBlock):
    type: Literal["incident_example"]
    incident_id: str
    link: str | None = None


# Items inside a CodeBlock are themselves a small union (snippet | description).


class CodeSnippet(BaseModel):
    id: str
    type: Literal["code"]
    title: str
    header: str
    language: str
    content: str


class CodeDescription(BaseModel):
    id: str
    type: Literal["description"]
    title: str
    content: str  # Quill HTML


CodeItem = Annotated[
    Union[CodeSnippet, CodeDescription],
    Field(discriminator="type"),
]


class CodeBlock(BaseBlock):
    type: Literal["code"]
    items: list[CodeItem]


class ImageBlock(BaseBlock):
    type: Literal["image"]
    data_url: str
    caption: str


class TableBlock(BaseBlock):
    type: Literal["table"]
    headers: list[str]
    rows: list[list[str]]


ContentBlock = Annotated[
    Union[
        HeadingBlock,
        ParagraphBlock,
        ListBlock,
        IncidentExampleBlock,
        CodeBlock,
        ImageBlock,
        TableBlock,
    ],
    Field(discriminator="type"),
]

# ── Metadata & Report ─────────────────────────────────────────────────────────


class ReportMetadata(BaseModel):
    # `extra="allow"` reproduces the TS `[key: string]: string` index signature,
    # so custom metadata fields added in the UI round-trip through the backend.
    model_config = ConfigDict(extra="allow")

    incident_id: str
    title: str
    caller: str
    category: str
    subcategory: str
    date: str


class IncidentReport(BaseModel):
    metadata: ReportMetadata
    blocks: list[ContentBlock]


# ── API request/response models (not in types.ts; the frontend fetch payloads) ─


class SaveReportRequest(BaseModel):
    """Body of POST /api/reports (mirrors the Express handler's req.body)."""

    report: IncidentReport
    markdown: str
    editingFilename: str | None = None


class SaveReportResponse(BaseModel):
    success: bool
    isUpdating: bool
    jsonUrl: str
    mdUrl: str
    jsonFilename: str
    mdFilename: str


class ReportListItem(BaseModel):
    filename: str
    metadata: ReportMetadata
    timestamp: float  # epoch ms, matching the TS stats.mtimeMs


class ReportListResponse(BaseModel):
    reports: list[ReportListItem]
