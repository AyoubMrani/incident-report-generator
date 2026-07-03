"""
chatbot/intent.py — lightweight intent routing.

Before running the (expensive) retrieval + resolution pipeline, decide what the
user actually wants. "hello" should get a friendly chatbot reply, not a 20%-
confidence incident search. This is a fast rule-based classifier — no extra model
call, no latency — that recognises greetings, thanks, and meta questions ("what
can you do?") and otherwise defers to the full pipeline.

Bias: when unsure, route to the incident pipeline. Missing a greeting (and
answering an incident-style reply to "hi") is a worse failure than running a
search on something that wasn't a question — so ambiguous input goes to the
pipeline. An attached image always means "analyze this", never smalltalk.
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"
    SMALLTALK = "smalltalk"   # thanks / bye / acknowledgements
    META = "meta"             # "what can you do", "who are you", "help"
    INCIDENT = "incident"     # -> run the retrieval + resolution pipeline


_GREETING = re.compile(
    r"^(hi|hii+|hey+|hello+|yo|hiya|howdy|good\s*(morning|afternoon|evening)|"
    r"greetings|sup|wassup|salut|bonjour|salam|hola)\b[\s!.?]*$",
    re.IGNORECASE,
)
_SMALLTALK = re.compile(
    r"^(thanks?|thank\s*you|thx|ty|cheers|great|nice|cool|awesome|perfect|ok(ay)?|"
    r"got\s*it|bye+|goodbye|see\s*ya|later|no\s*thanks?)\b[\s!.?]*$",
    re.IGNORECASE,
)
_META = re.compile(
    r"(?i)\b(what\s+can\s+you\s+do|who\s+are\s+you|what\s+are\s+you|"
    r"how\s+do\s+you\s+work|what\s+is\s+this|help\s*me?\s*$|^help\b|"
    r"how\s+can\s+you\s+help|what\s+do\s+you\s+do|your\s+capabilities)\b"
)

# Words that strongly indicate a real incident/ops question — if present, always
# go to the pipeline even if the message also looks chatty.
_INCIDENT_HINT = re.compile(
    r"(?i)\b(inc\d+|incident|error|failed|failure|cleanup|clean\s*up|duplicate|"
    r"provision|port|status|sql|table|database|db|reset|restart|outage|down|"
    r"stuck|sync|coma|fm_opv|home\s*status|resolve|fix|how\s+do\s+i|how\s+to|"
    r"why\s+is|what\s+causes|rollback|recover)\b"
)


def classify(text: str, has_image: bool = False) -> Intent:
    """Route a turn. An image always implies an incident (analyze the screenshot)."""
    if has_image:
        return Intent.INCIDENT

    t = (text or "").strip()
    if not t:
        return Intent.INCIDENT  # empty text but no image is handled upstream

    # A clear incident signal wins over any chatty surface form.
    if _INCIDENT_HINT.search(t):
        return Intent.INCIDENT

    if _GREETING.match(t):
        return Intent.GREETING
    if _SMALLTALK.match(t):
        return Intent.SMALLTALK
    if _META.search(t):
        return Intent.META

    # Very short, no incident hint, ends without a question -> likely chatter.
    if len(t) <= 12 and not t.endswith("?"):
        return Intent.SMALLTALK

    return Intent.INCIDENT


# Canned, friendly replies for non-incident intents. Kept here so they're easy to
# tweak and are returned WITHOUT hitting the LLM or the KB.
_META_REPLY = (
    "I'm the NTT incident assistant. Ask me about an incident — how to resolve "
    "one, find similar past reports, or make sense of a screenshot — and I'll "
    "search the report knowledge base and walk you through the fix. You can also "
    "attach a screenshot, or paste a ticket link. What are you working on?"
)

_REPLIES: dict[Intent, str] = {
    Intent.GREETING: (
        "Hey! 👋 I'm the NTT incident assistant. Tell me what incident you're "
        "looking at — or paste a screenshot — and I'll dig through the reports "
        "and suggest a resolution."
    ),
    Intent.SMALLTALK: "You're welcome! 🙂 Ping me whenever you have an incident to look into.",
    Intent.META: _META_REPLY,
}


def canned_reply(intent: Intent) -> str:
    return _REPLIES.get(intent, _META_REPLY)
