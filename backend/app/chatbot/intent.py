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
    META = "meta"             # "what can you do", "how do I use this" (in scope)
    OUT_OF_SCOPE = "out_of_scope"  # architecture/model questions, general knowledge
    CLARIFY = "clarify"       # incident-flavored but too vague -> ask, don't guess
    INCIDENT = "incident"     # -> run the retrieval + resolution pipeline


# Gate 1 — scope check. Questions about how the assistant itself is built, and
# general-knowledge / unrelated-coding / creative requests, are out of scope: the
# assistant answers about incidents only. Note this is narrower than META: "how
# do I use this?" is in scope, "what model are you?" is not.
_OUT_OF_SCOPE = re.compile(
    r"(?i)("
    r"\b(what|which)\s+(model|llm|ai|architecture|framework|version)\b|"
    r"\b(are|were)\s+you\s+(built|trained|made|created|fine[\s-]?tuned)\b|"
    r"\bhow\s+(were|are)\s+you\s+(built|trained|made|created)\b|"
    r"\byour\s+(training|architecture|model|weights|parameters|source\s+code|prompt)\b|"
    r"\b(gpt|claude|llama|openai|anthropic|ollama)\b|"
    r"\bwrite\s+(me\s+)?(a\s+)?(poem|song|story|essay|joke)\b|"
    r"\b(who|what)\s+(won|is\s+the\s+(capital|president|weather))\b|"
    r"\btranslate\s+(this|the following)\b|"
    r"\bwhat('?s| is)\s+the\s+weather\b"
    r")"
)


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
# Gratitude with a short tail: "thanks, that helped", "ok cool, got it — bye".
# Without this the message falls through to INCIDENT and the assistant answers
# a thank-you by searching the corpus and citing an unrelated report.
# Deliberately capped in length so "thanks, now the DB is down" still routes to
# the incident path rather than being dismissed as chatter.
_SMALLTALK_TAIL = re.compile(
    r"^(thanks?|thank\s*you|thx|ty|cheers|perfect|great|awesome|nice)\b"
    r"[\s,!.–—-]*(that|this|it)?\s*"
    r"(helped|helps|worked|works|did\s+it|was\s+it|makes\s+sense|"
    r"is\s+(great|perfect|clear))\b[\s!.?]*$",
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


# Vague inputs that name a *symptom class* but no specifics to diagnose.
_VAGUE_PHRASES = re.compile(
    r"(?i)^(it('?s| is)?\s+broken( again)?|broken( again)?|not working|"
    r"doesn'?t work|it failed|failed again|same (problem|issue|error)( again)?|"
    r"error|an error|some error|health[\s-]*check[\s-]*error|"
    r"help( me)?|something('?s| is) wrong|it'?s down|down again|"
    r"issue|problem|bug|crash(ed)?)\s*[.!?]*$"
)

# Concrete signals that make an incident diagnosable: error codes, identifiers,
# file paths, service/tech names, quoted messages.
_SPECIFIC_SIGNAL = re.compile(
    r"(?i)("
    r"inc\d+|"                                   # incident id
    r"\b\d{3}\b|"                                 # HTTP-ish status code
    r"exit\s*code|exit\s*\d+|"                    # exit codes
    r"[/\\][\w.\-/\\]+\.\w+|"                     # file path
    r"\b\w+\.(yml|yaml|json|xml|conf|log|py|java|js|ts|sh|sql)\b|"  # filename
    r"\b(sqlstate|errno|econn|timeout|handshake|servfail|nxdomain|oomkilled|"
    r"crashloopbackoff|deadlock|401|403|500|502|503|504)\b|"        # error tokens
    r"\b(kafka|kubernetes|k8s|docker|nginx|haproxy|postgres|redis|tls|ssl|dns|"
    r"vpn|jwt|oauth|saml|ldap|prometheus|helm|istio|db|api|ci|cd|pod|node|"
    r"server|service|database|network|disk|memory|cpu|cert|queue|cluster)\b|"  # tech names
    r"\"[^\"]{6,}\"|'[^']{6,}'"                   # a quoted message/snippet
    r")"
)


def _meaningful_words(text: str) -> int:
    from .security import injection_scan  # noqa: F401 (kept local; light)
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text.lower())
    stop = {"the", "and", "for", "was", "were", "have", "has", "not", "but",
            "this", "that", "with", "you", "your", "from", "how", "why", "what",
            "there", "again", "some", "any", "please", "help", "error", "issue",
            "problem", "broken", "working", "down", "failed", "wrong", "thing"}
    return len({w for w in words if w not in stop})


def has_incident_signal(text: str) -> bool:
    """True when the text contains concrete, diagnosable incident content.

    Used to tell a message that is ONLY an injection attempt from a genuine
    incident that happens to contain injection-like phrasing: the latter still
    deserves an answer (with a security note), the former is refused.
    """
    return bool(_SPECIFIC_SIGNAL.search(text or ""))


def is_ambiguous(text: str, has_history: bool = False) -> bool:
    """True when an incident-flavored input is too low-context to diagnose safely.

    Conservative bias (we prefer to answer over falsely blocking): only flag as
    ambiguous when there is NO concrete signal (error code, id, file, tech name,
    quoted message) AND the input is a known vague phrase or nearly empty of
    content words. A specific input is never flagged. Follow-ups in an ongoing
    conversation are not flagged — prior turns supply the missing context.
    """
    t = (text or "").strip()
    if has_history:
        return False                      # a follow-up; earlier turns give context
    if _SPECIFIC_SIGNAL.search(t):
        return False                      # has something concrete to work with
    if _VAGUE_PHRASES.match(t):
        return True                       # "it's broken again", "error", ...
    # Almost no content words at all -> not enough to ground a diagnosis.
    return _meaningful_words(t) < 2


def classify(text: str, has_image: bool = False, has_history: bool = False) -> Intent:
    """Route a turn. An image always implies an incident (analyze the screenshot).

    `has_history` = there are prior turns in this conversation; follow-ups are
    then never treated as too-vague (earlier turns supply the context).
    """
    if has_image:
        return Intent.INCIDENT

    t = (text or "").strip()
    if not t:
        return Intent.INCIDENT  # empty text but no image is handled upstream

    # Gate 1 — scope. Questions about the assistant's own construction, and
    # general-knowledge requests, are refused before anything else, even if they
    # happen to contain incident-sounding words.
    if _OUT_OF_SCOPE.search(t):
        return Intent.OUT_OF_SCOPE

    # A clear incident signal wins over any chatty surface form — BUT if it's
    # incident-flavored yet too vague, ask for clarification instead of guessing.
    if _INCIDENT_HINT.search(t):
        return Intent.CLARIFY if is_ambiguous(t, has_history) else Intent.INCIDENT

    if _GREETING.match(t):
        return Intent.GREETING
    if _SMALLTALK.match(t) or _SMALLTALK_TAIL.match(t):
        return Intent.SMALLTALK
    if _META.search(t):
        return Intent.META

    # A bare vague trouble word ("broken", "not working", "something's wrong")
    # is a help request with no content — clarify rather than treat as chatter.
    if not has_history and _VAGUE_PHRASES.match(t):
        return Intent.CLARIFY

    # Very short, no incident hint, ends without a question -> likely chatter.
    if len(t) <= 12 and not t.endswith("?"):
        return Intent.SMALLTALK

    # Longer free text with no incident hint and little substance -> clarify.
    if is_ambiguous(t, has_history):
        return Intent.CLARIFY

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
    Intent.OUT_OF_SCOPE: (
        "I'm built specifically to help with IT incident reports and resolutions — "
        "I don't have information outside that scope. If you've got an incident, "
        "error message, or procedure you're troubleshooting, I'm glad to help with that."
    ),
    Intent.CLARIFY: (
        "I don't have enough detail to diagnose this safely yet, and I won't "
        "guess at a root cause. Could you share any of the following?\n"
        "• the exact error message or code (e.g. HTTP 503, exit 137, a stack trace)\n"
        "• which service or component is affected\n"
        "• what changed just before it started (a deploy, config change, etc.)\n"
        "• a screenshot or log snippet\n"
        "Even one of these lets me search the reports and give a grounded answer."
    ),
}


def canned_reply(intent: Intent) -> str:
    return _REPLIES.get(intent, _META_REPLY)
