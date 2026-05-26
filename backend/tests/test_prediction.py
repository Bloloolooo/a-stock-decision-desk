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
