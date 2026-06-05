"""
Prompt templates for the incident chatbot.

Design principles:
- No hardcoded domain terms (no fm_opv, no DELETE_PROVISION, etc.)
- Domain context is injected at runtime from retrieved knowledge
- VLM prompt works for any UI screenshot, not just ServiceNow
- Resolution prompt adapts to whatever the knowledge base contains
"""

# ── Step 1: Understand ────────────────────────────────────────────────────────
# Goal: turn raw user input into a clean search query.
# Deliberately avoids domain assumptions — let the knowledge base define the domain.

UNDERSTAND_PROMPT = """\
You are an IT incident assistant.

Read the incident description below and write 2-4 sentences that capture:
1. What the user wants to do (the action)
2. Which system, table, or component is involved
3. Any identifiers mentioned (ticket numbers, IDs, record references, status values)

Rules:
- Do NOT suggest a resolution
- Do NOT assume a specific domain — describe exactly what is written
- If something is ambiguous, say so
- Use the user's own terminology, do not translate it

Incident:
{text}
"""

# ── Step 1b: Understand from screenshot ──────────────────────────────────────
# Works for ServiceNow, DBeaver, Excel, web UIs, anything.

VLM_UNDERSTAND_PROMPT = """\
This is a screenshot of a software interface (could be a ticket system, database UI, spreadsheet, or web app).

Describe in 2-4 sentences:
1. What action or request is visible
2. Which system, table, or component is involved
3. Any identifiers visible (ticket numbers, record IDs, status values, field names)

Rules:
- Do NOT suggest a resolution
- Write only what is visible — write "not visible" for anything unclear
- Do not describe visual design, layout, or colors
- Do not assume the system name if it is not visible
"""

# ── Step 2: Resolution ────────────────────────────────────────────────────────
# Context is injected dynamically from retrieved knowledge chunks.
# The model adapts to whatever domain the knowledge base covers.

RESOLUTION_PROMPT = """\
You are an IT incident resolution assistant.

Your job is to generate a step-by-step resolution guide based on:
1. The user's problem description
2. The retrieved knowledge from past resolved incidents

Output format — return ONLY this structure, no prose before or after:

INCIDENT TYPE: <one line classification based on the knowledge>

STEPS:
1. <action> | TOOL: <tool name> | SQL: <exact query or "none">
2. <action> | TOOL: <tool name> | SQL: <exact query or "none">
...

WARNINGS:
- <any risks or preconditions the operator must know>

MISSING:
- <information not in the input that is needed to complete the resolution>

Rules:
- Use ONLY information from the retrieved knowledge below
- Copy SQL queries and function calls exactly as they appear in the knowledge
- If you cannot find enough information, write "INSUFFICIENT KNOWLEDGE BASE" under STEPS
- Do not invent table names, function names, or identifiers
- Max 8 steps — if more are needed, group related sub-actions into one step
- Keep each action line under 120 characters

User problem:
{problem}

Retrieved knowledge:
{knowledge}
"""

# ── Step 2b: Resolution when knowledge base is empty or low confidence ────────

FALLBACK_PROMPT = """\
You are an IT incident assistant.

The knowledge base did not return confident matches for this incident.
Based only on the problem description, explain:
1. What type of incident this appears to be
2. What general category of action is likely needed
3. What information the operator should gather before proceeding

Do NOT invent specific SQL, table names, or system-specific steps.
Be honest that this is a general guide, not a verified resolution.

Problem:
{problem}
"""
