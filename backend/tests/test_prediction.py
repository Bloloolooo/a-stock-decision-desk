import subprocess
from types import SimpleNamespace

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
    service = PredictionService()

    status = service.update_settings(enabled=True, model_name="NeoQuasar/Kronos-small")

    assert status.enabled is True
    assert status.model_name == "NeoQuasar/Kronos-small"
    assert status.install_status == "manual_required"
    assert status.install_commands


def test_prediction_install_endpoint_reports_manual_required(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    service = PredictionService()

    status = service.install_async()

    assert status.install_status == "manual_required"
    assert "自动安装已取消" in (status.last_error or "")


def test_prediction_check_environment_marks_ready(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(PredictionService, "_assert_runtime_usable", lambda self, model_name: None)
    monkeypatch.setattr(PredictionService, "_runtime_ready", lambda self: True)
    service = PredictionService()
    service.update_settings(enabled=True, model_name="NeoQuasar/Kronos-small")

    status = service.check_environment()

    assert status.install_status == "ready"
    assert status.ready is True


def test_prediction_check_environment_ready_even_when_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(PredictionService, "_assert_runtime_usable", lambda self, model_name: None)
    monkeypatch.setattr(PredictionService, "_runtime_ready", lambda self: True)
    service = PredictionService()

    status = service.check_environment()

    assert status.enabled is False
    assert status.install_status == "ready"
    assert status.ready is True


def test_prediction_venv_failure_reports_actionable_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "VENV_PATH", tmp_path / ".venv")
    monkeypatch.setattr(PredictionService, "_python_candidates", lambda self: [["python"]])
    monkeypatch.setattr(PredictionService, "_python_version", lambda self, command: (3, 11, 9))

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
    monkeypatch.setattr(PredictionService, "_python_version", lambda self, command: (3, 11, 9))

    def fake_run(command, **kwargs):
        python_path = venv_path / ("Scripts/python.exe" if prediction_module.os.name == "nt" else "bin/python")
        python_path.parent.mkdir(parents=True, exist_ok=True)
        python_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    service._ensure_venv()

    assert service._venv_python_path().exists()


def test_prediction_preflight_reports_missing_git(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "RUNTIME_PATH", tmp_path / ".kronos_runtime")
    monkeypatch.setattr(prediction_module.shutil, "which", lambda command: None)
    monkeypatch.setattr(prediction_module.PredictionService, "_check_dns", lambda self: None)
    service = PredictionService()

    try:
        service._preflight_install()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing Git failure")

    assert "未找到 Git" in message
    assert "PATH" in message


def test_prediction_preflight_reports_low_disk(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "RUNTIME_PATH", tmp_path / ".kronos_runtime")
    monkeypatch.setattr(prediction_module.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024))
    service = PredictionService()

    try:
        service._preflight_install()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected low disk failure")

    assert "磁盘空间不足" in message
    assert "建议至少预留" in message


def test_prediction_preflight_reports_dns_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "RUNTIME_PATH", tmp_path / ".kronos_runtime")
    monkeypatch.setattr(prediction_module.shutil, "which", lambda command: "/usr/bin/git")

    def fake_getaddrinfo(host, port):
        raise OSError("dns failed")

    monkeypatch.setattr(prediction_module.socket, "getaddrinfo", fake_getaddrinfo)
    service = PredictionService()

    try:
        service._preflight_install()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected DNS failure")

    assert "DNS 解析异常" in message
    assert "HTTPS_PROXY" in message


def test_prediction_preflight_reports_permission_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "RUNTIME_PATH", tmp_path / ".kronos_runtime")
    monkeypatch.setattr(prediction_module.shutil, "which", lambda command: "/usr/bin/git")
    monkeypatch.setattr(prediction_module.PredictionService, "_check_dns", lambda self: None)
    service = PredictionService()

    def fake_write_text(self, *args, **kwargs):
        raise PermissionError("access denied")

    monkeypatch.setattr(prediction_module.Path, "write_text", fake_write_text)

    try:
        service._preflight_install()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected permission failure")

    assert "运行目录不可写" in message
    assert "权限" in message


def test_prediction_python_version_rejects_unsupported(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(prediction_module, "VENV_PATH", tmp_path / ".venv")
    monkeypatch.setattr(PredictionService, "_python_candidates", lambda self: [["python"]])
    monkeypatch.setattr(PredictionService, "_python_version", lambda self, command: (3, 13, 0))
    service = PredictionService()

    try:
        service._ensure_venv()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected unsupported Python failure")

    assert "Python 3.13" in message
    assert "Python 3.10/3.11/3.12" in message


def test_prediction_repo_recovery_removes_partial_clone(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    repo_path = tmp_path / "Kronos"
    repo_path.mkdir()
    stale_file = repo_path / "partial.txt"
    stale_file.write_text("broken", encoding="utf-8")
    monkeypatch.setattr(prediction_module, "REPO_PATH", repo_path)
    service = PredictionService()

    def fake_run(command, timeout, stage="执行安装命令"):
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "requirements.txt").write_text("pandas\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(service, "_run_install_command", fake_run)

    service._ensure_kronos_repo()

    assert not stale_file.exists()
    assert (repo_path / "requirements.txt").exists()


def test_prediction_model_download_failure_has_proxy_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))

    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="Failed to establish a new connection to huggingface.co")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    try:
        service._prepare_model_cache("python")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected HuggingFace access failure")

    assert "HuggingFace" in message
    assert "HTTPS_PROXY" in message


def test_prediction_dependency_conflict_has_version_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))

    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="ResolutionImpossible: conflicting dependencies")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    try:
        service._install_python_dependencies("python")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected dependency conflict failure")

    assert "依赖解析冲突" in message
    assert "Python 3.10/3.11" in message


def test_prediction_repairs_missing_pip_with_ensurepip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    calls: list[list[str]] = []
    pip_checks = {"count": 0}

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["python", "-m", "pip"] and command[3:] == ["--version"]:
            pip_checks["count"] += 1
            if pip_checks["count"] == 1:
                raise subprocess.CalledProcessError(1, command, stderr="No module named pip")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    service._install_python_dependencies("python")

    assert ["python", "-m", "ensurepip", "--upgrade"] in calls
    assert ["python", "-m", "pip", "install", "--upgrade", "pip"] in calls


def test_prediction_missing_pip_reports_windows_repair_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))

    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="No module named pip")

    monkeypatch.setattr(prediction_module.subprocess, "run", fake_run)
    service = PredictionService()

    try:
        service._install_python_dependencies("python")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing pip failure")

    assert "缺少 pip" in message
    assert "ensurepip" in message
    assert "完整 Python" in message
