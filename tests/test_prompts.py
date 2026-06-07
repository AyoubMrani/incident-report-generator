import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from incident_chatbot.prompts import (
    FALLBACK_PROMPT,
    FALLBACK_PROMPT_REQUIRED,
    NO_IMAGE_ANALYSIS,
    RESOLUTION_PROMPT,
    RESOLUTION_PROMPT_REQUIRED,
    UNDERSTAND_PROMPT,
    UNDERSTAND_PROMPT_REQUIRED,
    VLM_UNDERSTAND_PROMPT,
    format_prompt,
)


def test_understand_prompt_text_only():
    prompt = format_prompt(
        UNDERSTAND_PROMPT,
        UNDERSTAND_PROMPT_REQUIRED,
        text="Remove duplicate OPV rows",
    )
    assert "Remove duplicate OPV rows" in prompt
    assert "{text}" not in prompt


def test_resolution_prompt_all_placeholders():
    prompt = format_prompt(
        RESOLUTION_PROMPT,
        RESOLUTION_PROMPT_REQUIRED,
        problem="retrieval query",
        image_analysis=NO_IMAGE_ANALYSIS,
        knowledge="chunk one",
    )
    assert "retrieval query" in prompt
    assert NO_IMAGE_ANALYSIS in prompt
    assert "chunk one" in prompt
    assert "{problem}" not in prompt
    assert "{image_analysis}" not in prompt
    assert "{knowledge}" not in prompt


def test_fallback_prompt_all_placeholders():
    prompt = format_prompt(
        FALLBACK_PROMPT,
        FALLBACK_PROMPT_REQUIRED,
        problem="retrieval query",
        image_analysis="Screenshot shows INC123",
    )
    assert "retrieval query" in prompt
    assert "Screenshot shows INC123" in prompt
    assert "{problem}" not in prompt
    assert "{image_analysis}" not in prompt


def test_vlm_understand_prompt_has_no_placeholders():
    assert "{" not in VLM_UNDERSTAND_PROMPT


@pytest.mark.parametrize(
    "template,required,kwargs,missing_name",
    [
        (
            RESOLUTION_PROMPT,
            RESOLUTION_PROMPT_REQUIRED,
            {"problem": "p", "knowledge": "k"},
            "image_analysis",
        ),
        (
            FALLBACK_PROMPT,
            FALLBACK_PROMPT_REQUIRED,
            {"problem": "p"},
            "image_analysis",
        ),
        (
            UNDERSTAND_PROMPT,
            UNDERSTAND_PROMPT_REQUIRED,
            {},
            "text",
        ),
    ],
)
def test_format_prompt_raises_clear_error_for_missing_vars(
    template, required, kwargs, missing_name
):
    with pytest.raises(ValueError, match=missing_name):
        format_prompt(template, required, **kwargs)
