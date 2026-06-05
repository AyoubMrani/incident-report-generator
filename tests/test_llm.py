import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from incident_chatbot.llm import VLMUnavailableError, run_vlm, vlm_availability, vlm_status


def test_vlm_status_reports_missing_package(monkeypatch):
    monkeypatch.setattr(
        "incident_chatbot.llm.importlib.util.find_spec",
        lambda name: None if name == "mlx_vlm" else __import__("importlib.util").util.find_spec(name),
    )
    status = vlm_status()
    assert status["package_installed"] is False
    assert status["ready"] is False
    assert "mlx_vlm" in status["reason"]


def test_vlm_status_package_without_weights(monkeypatch):
    monkeypatch.setattr(
        "incident_chatbot.llm.importlib.util.find_spec",
        lambda name: object() if name == "mlx_vlm" else __import__("importlib.util").util.find_spec(name),
    )
    monkeypatch.setattr("incident_chatbot.llm.os.path.isdir", lambda path: False)
    status = vlm_status()
    assert status["package_installed"] is True
    assert status["weights_present"] is False
    assert status["ready"] is False
    assert "pip install" not in status["hint"].lower()


def test_run_vlm_missing_package_raises_with_install_hint(monkeypatch):
    monkeypatch.setattr(
        "incident_chatbot.llm.vlm_status",
        lambda: {
            "package_installed": False,
            "weights_present": False,
            "ready": False,
            "reason": "mlx_vlm is not importable in this Python environment",
            "hint": "pip install mlx-vlm",
            "model_path": "/tmp/x",
        },
    )
    try:
        run_vlm("hello")
        assert False, "expected VLMUnavailableError"
    except VLMUnavailableError as exc:
        assert exc.package_installed is False
        assert "pip install" in exc.hint


def test_run_vlm_missing_weights_does_not_suggest_pip(monkeypatch):
    monkeypatch.setattr(
        "incident_chatbot.llm.vlm_status",
        lambda: {
            "package_installed": True,
            "weights_present": False,
            "ready": False,
            "reason": "MLX vision weights not found at /models/x",
            "hint": "Place converted Qwen2.5-VL weights there",
            "model_path": "/models/x",
        },
    )
    try:
        run_vlm("hello")
        assert False, "expected VLMUnavailableError"
    except VLMUnavailableError as exc:
        assert exc.package_installed is True
        assert "pip" not in exc.hint.lower()


def test_vlm_availability_wrapper():
    status = vlm_availability()
    assert "available" in status
    assert status["available"] == status.get("ready", status["available"])
