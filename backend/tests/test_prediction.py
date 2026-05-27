import subprocess

import app.services.prediction as prediction_module
from app.services.prediction import PredictionService


def test_prediction_defaults_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    service = PredictionService()

    status = service.status()

    assert status.enabled is False
    assert status.ready is False
    assert status.install_status == "not_installed"


def test_prediction_enable_starts_install_without_blocking(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    started = {"value": False}

    def fake_install(self):
        started["value"] = True
        return self.status()

    monkeypatch.setattr(prediction_module.PredictionService, "install_async", fake_install)
    service = PredictionService()

    status = service.update_settings(enabled=True, model_name="NeoQuasar/Kronos-small")

    assert started["value"] is True
    assert status.enabled is True
    assert status.model_name == "NeoQuasar/Kronos-small"


def test_prediction_venv_failure_reports_actionable_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "VENV_PATH", tmp_path / ".venv")
    monkeypatch.setattr(PredictionService, "_python_candidates", lambda self: [["python"]])

    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(3221225786, command, stderr="venv failed")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    try:
        service._ensure_venv()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected venv creation failure")

    assert "Kronos Python 虚拟环境创建失败" in message
    assert "KRONOS_PYTHON" in message
    assert "3221225786" in message


def test_prediction_ensure_venv_accepts_generated_python(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    venv_path = tmp_path / ".venv"
    monkeypatch.setattr(prediction_module, "VENV_PATH", venv_path)
    monkeypatch.setattr(PredictionService, "_python_candidates", lambda self: [["python"]])

    def fake_run(command, **kwargs):
        python_path = venv_path / ("Scripts/python.exe" if prediction_module.os.name == "nt" else "bin/python")
        python_path.parent.mkdir(parents=True, exist_ok=True)
        python_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    service._ensure_venv()

    assert service._venv_python_path().exists()
