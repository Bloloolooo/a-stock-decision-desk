from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
from textwrap import dedent

from app.db import get_connection, init_db
from app.schemas import PredictionResult, PredictionSettings, PredictionStatus, PriceBar
from app.services.market_data import market_data


RUNTIME_PATH = Path(__file__).resolve().parents[2] / ".kronos_runtime"
REPO_PATH = RUNTIME_PATH / "Kronos"
VENV_PATH = RUNTIME_PATH / ".venv"
RUNNER_PATH = RUNTIME_PATH / "predict_once.py"
DEFAULT_MODEL = "NeoQuasar/Kronos-small"
DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
MIN_RUNTIME_FREE_BYTES = 8 * 1024 * 1024 * 1024
PYTHON_VERSION_MIN = (3, 10)
PYTHON_VERSION_MAX = (3, 12)
NETWORK_TARGETS = (
    ("GitHub", "github.com", 443),
    ("PyPI", "pypi.org", 443),
    ("HuggingFace", "huggingface.co", 443),
)


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _is_network_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "could not resolve",
            "dns",
            "failed to establish",
            "network is unreachable",
            "connection refused",
            "connection reset",
            "connection timed out",
            "timed out",
            "proxy",
            "ssl",
            "tls",
            "certificate",
            "temporary failure",
            "name or service not known",
        )
    )


def _format_bytes(size: int) -> str:
    return f"{size / 1024 / 1024 / 1024:.1f}GB"


class PredictionService:
    def __init__(self) -> None:
        init_db()
        self._install_lock = threading.Lock()

    def status(self) -> PredictionStatus:
        settings = self.settings()
        ready = settings.install_status == "ready" and self._runtime_ready()
        return PredictionStatus(
            **settings.model_dump(),
            runtime_path=str(RUNTIME_PATH),
            ready=ready,
            install_commands=self.install_commands(settings.model_name),
            environment_checks=self._environment_check_lines(),
        )

    def settings(self) -> PredictionSettings:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT enabled, model_name, tokenizer_name, install_status, last_error, installed_at, updated_at
                FROM prediction_settings WHERE id = 1
                """
            ).fetchone()
        if not row:
            return PredictionSettings(
                enabled=False,
                model_name=DEFAULT_MODEL,
                tokenizer_name=DEFAULT_TOKENIZER,
                install_status="not_installed",
                updated_at=datetime.now(),
            )
        return PredictionSettings(
            enabled=bool(row["enabled"]),
            model_name=row["model_name"],
            tokenizer_name=row["tokenizer_name"],
            install_status=row["install_status"],
            last_error=row["last_error"],
            installed_at=datetime.fromisoformat(row["installed_at"]) if row["installed_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def update_settings(self, enabled: bool, model_name: str = DEFAULT_MODEL) -> PredictionStatus:
        model = model_name.strip() or DEFAULT_MODEL
        with get_connection() as connection:
            current = self.settings()
            install_status = current.install_status
            if not enabled:
                install_status = "not_installed" if install_status == "installing" else install_status
            elif install_status in {"not_installed", "installing", "failed"}:
                install_status = "manual_required"
            connection.execute(
                """
                UPDATE prediction_settings
                SET enabled = ?, model_name = ?, tokenizer_name = ?, install_status = ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (1 if enabled else 0, model, DEFAULT_TOKENIZER, install_status),
            )
        return self.status()

    def install_commands(self, model_name: str = DEFAULT_MODEL) -> list[str]:
        model = model_name.strip() or DEFAULT_MODEL
        if os.name == "nt":
            return [
                "cd backend",
                r"py -3.11 -m venv .kronos_runtime\.venv",
                r".kronos_runtime\.venv\Scripts\python.exe -m ensurepip --upgrade",
                r".kronos_runtime\.venv\Scripts\python.exe -m pip install --upgrade pip",
                r"git clone --depth 1 https://github.com/shiyu-coder/Kronos.git .kronos_runtime\Kronos",
                r".kronos_runtime\.venv\Scripts\python.exe -m pip install -r .kronos_runtime\Kronos\requirements.txt",
                (
                    r".kronos_runtime\.venv\Scripts\python.exe -c "
                    f"\"from huggingface_hub import snapshot_download; snapshot_download({model!r}); snapshot_download({DEFAULT_TOKENIZER!r})\""
                ),
            ]
        return [
            "cd backend",
            "python3.11 -m venv .kronos_runtime/.venv",
            ".kronos_runtime/.venv/bin/python -m ensurepip --upgrade",
            ".kronos_runtime/.venv/bin/python -m pip install --upgrade pip",
            "git clone --depth 1 https://github.com/shiyu-coder/Kronos.git .kronos_runtime/Kronos",
            ".kronos_runtime/.venv/bin/python -m pip install -r .kronos_runtime/Kronos/requirements.txt",
            (
                ".kronos_runtime/.venv/bin/python -c "
                f"\"from huggingface_hub import snapshot_download; snapshot_download({model!r}); snapshot_download({DEFAULT_TOKENIZER!r})\""
            ),
        ]

    def check_environment(self) -> PredictionStatus:
        settings = self.settings()
        try:
            self._assert_runtime_usable(settings.model_name)
        except RuntimeError as exc:
            self._set_install_status("failed", str(exc)[-500:])
            return self.status()
        self._set_install_status("ready", None)
        return self.status()

    def install_async(self) -> PredictionStatus:
        self._set_install_status(
            "manual_required",
            "自动安装已取消。请按设置页的命令手动安装 Kronos 后点击“检查环境”。",
        )
        return self.status()

    def predict(self, symbol: str, horizon: int = 20) -> PredictionResult:
        status = self.status()
        if not status.enabled:
            raise RuntimeError("预测功能尚未启用")
        if not status.ready:
            raise RuntimeError("Kronos 运行环境尚未就绪")
        history = market_data.bars(symbol=symbol, period="daily")[-120:]
        try:
            forecast = self._run_kronos(symbol=symbol, history=history, horizon=max(1, min(horizon, 60)))
        except RuntimeError as exc:
            self._set_install_status("ready", str(exc)[-500:])
            raise
        start_close = history[-1].close
        end_close = forecast[-1].close if forecast else start_close
        expected_change = (end_close / start_close - 1) * 100 if start_close else 0.0
        return PredictionResult(
            symbol=symbol,
            name=market_data.name(symbol),
            model_name=status.model_name,
            horizon=len(forecast),
            history=history[-80:],
            forecast=forecast,
            expected_change_pct=round(expected_change, 2),
            generated_at=datetime.now(),
            message="Kronos 模型预测结果，仅供研究和辅助观察，不构成交易建议。",
        )

    def _install(self) -> None:
        try:
            self._set_install_status("installing", None)
            self._preflight_install()
            self._ensure_kronos_repo()
            self._ensure_venv()
            python = self._venv_python()
            self._install_python_dependencies(python)
            self._write_runner()
            self._prepare_model_cache(python)
            self._set_install_status("ready", None)
        except Exception as exc:
            self._set_install_status("failed", str(exc)[-500:])
        finally:
            self._install_lock.release()

    def _preflight_install(self) -> None:
        runtime_parent = RUNTIME_PATH.parent
        usage = shutil.disk_usage(runtime_parent)
        if usage.free < MIN_RUNTIME_FREE_BYTES:
            raise RuntimeError(
                "Kronos 安装前检查失败：磁盘空间不足。"
                f"当前可用 {_format_bytes(usage.free)}，建议至少预留 {_format_bytes(MIN_RUNTIME_FREE_BYTES)}。"
            )
        try:
            RUNTIME_PATH.mkdir(parents=True, exist_ok=True)
            probe = RUNTIME_PATH / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(
                "Kronos 安装前检查失败：运行目录不可写。"
                f"请检查 {RUNTIME_PATH} 的权限，或把项目移动到有写入权限的位置。原始错误：{exc}"
            ) from exc
        if not shutil.which("git"):
            raise RuntimeError("Kronos 安装前检查失败：未找到 Git。请先安装 Git，并确认 git 命令已加入 PATH。")
        self._check_dns()

    def _check_dns(self) -> None:
        failed: list[str] = []
        for label, host, _port in NETWORK_TARGETS:
            try:
                socket.getaddrinfo(host, None)
            except OSError as exc:
                failed.append(f"{label}({host})：{exc}")
        if failed:
            raise RuntimeError(
                "Kronos 安装前检查失败：DNS 解析异常。"
                "请检查网络、DNS、代理或防火墙设置；公司/校园网络可能需要配置 HTTPS_PROXY/HTTP_PROXY。"
                f"失败项：{'；'.join(failed)}"
            )

    def _ensure_kronos_repo(self) -> None:
        if self._repo_ready():
            return
        if REPO_PATH.exists():
            shutil.rmtree(REPO_PATH, ignore_errors=True)
        self._run_install_command(
            ["git", "clone", "--depth", "1", "https://github.com/shiyu-coder/Kronos.git", str(REPO_PATH)],
            timeout=600,
            stage="下载 Kronos 源码",
        )

    def _repo_ready(self) -> bool:
        return REPO_PATH.exists() and (REPO_PATH / "requirements.txt").exists()

    def _install_python_dependencies(self, python: str) -> None:
        self._ensure_pip(python)
        self._run_install_command([python, "-m", "pip", "install", "--upgrade", "pip"], timeout=300, stage="升级 pip")
        self._run_install_command(
            [python, "-m", "pip", "install", "-r", str(REPO_PATH / "requirements.txt")],
            timeout=1200,
            stage="安装 Kronos 依赖",
        )

    def _prepare_model_cache(self, python: str) -> None:
        script = (
            "from huggingface_hub import snapshot_download\n"
            f"snapshot_download({self.settings().model_name!r})\n"
            f"snapshot_download({DEFAULT_TOKENIZER!r})\n"
            "print('ok')\n"
        )
        self._run_install_command(
            [python, "-c", script],
            timeout=300,
            stage="下载 HuggingFace 模型",
        )

    def _ensure_venv(self) -> None:
        python_path = self._venv_python_path()
        if VENV_PATH.exists() and python_path.exists():
            return
        if VENV_PATH.exists() and not python_path.exists():
            shutil.rmtree(VENV_PATH, ignore_errors=True)
        errors: list[str] = []
        for command in self._python_candidates():
            try:
                version = self._python_version(command)
            except Exception as exc:
                errors.append(str(exc))
                continue
            if not self._python_version_supported(version):
                errors.append(
                    f"{_command_text(command)} 是 Python {version[0]}.{version[1]}，"
                    "Kronos 依赖建议使用 Python 3.10、3.11 或 3.12。"
                )
                continue
            create_command = [
                *command,
                "-m",
                "venv",
                *(["--copies"] if os.name == "nt" else []),
                str(VENV_PATH),
            ]
            try:
                self._run_install_command(create_command, timeout=300, stage="创建 Python 虚拟环境")
                if python_path.exists():
                    return
                errors.append(f"{_command_text(create_command)} 执行完成但未生成 {python_path}")
            except Exception as exc:
                shutil.rmtree(VENV_PATH, ignore_errors=True)
                errors.append(str(exc))
        raise RuntimeError(
            "Kronos Python 虚拟环境创建失败。"
            "请安装完整 Python 3.10/3.11/3.12；Windows 上可设置环境变量 KRONOS_PYTHON 指向 python.exe 后重试。"
            f"最近错误：{errors[-1] if errors else '没有可用 Python'}"
        )

    def _ensure_pip(self, python: str) -> None:
        if self._pip_ready(python):
            return
        try:
            self._run_install_command(
                [python, "-m", "ensurepip", "--upgrade"],
                timeout=300,
                stage="修复 pip",
            )
        except RuntimeError as exc:
            raise RuntimeError(
                "Kronos pip 修复失败：当前虚拟环境缺少 pip，且 ensurepip 无法自动补齐。"
                "请在 Windows 上安装完整 Python 3.10/3.11/3.12，并勾选 pip；"
                "也可以先执行 py -3.11 -m ensurepip --upgrade，或设置 KRONOS_PYTHON 指向完整 python.exe 后重试。"
                f"原始错误：{exc}"
            ) from exc
        if not self._pip_ready(python):
            raise RuntimeError(
                "Kronos pip 修复失败：ensurepip 执行完成后仍无法运行 python -m pip。"
                "建议删除 backend/.kronos_runtime/.venv 后重试，或改用完整 Python 3.10/3.11。"
            )

    def _pip_ready(self, python: str) -> bool:
        try:
            subprocess.run(
                [python, "-m", "pip", "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return True
        except (FileNotFoundError, subprocess.SubprocessError):
            return False

    def _python_version(self, command: list[str]) -> tuple[int, int, int]:
        check_command = [
            *command,
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
        ]
        try:
            completed = subprocess.run(check_command, check=True, capture_output=True, text=True, timeout=20)
        except FileNotFoundError as exc:
            raise RuntimeError(f"命令不存在：{_command_text(command)}") from exc
        except subprocess.SubprocessError as exc:
            raise RuntimeError(f"无法检查 Python 版本：{_command_text(command)}；{exc}") from exc
        try:
            version_text = completed.stdout.strip().splitlines()[-1]
            major, minor, patch = version_text.split(".", maxsplit=2)
            return int(major), int(minor), int(patch)
        except (IndexError, ValueError) as exc:
            raise RuntimeError(f"无法解析 Python 版本：{_command_text(command)}；输出：{completed.stdout!r}") from exc

    def _python_version_supported(self, version: tuple[int, int, int]) -> bool:
        major_minor = version[:2]
        return PYTHON_VERSION_MIN <= major_minor <= PYTHON_VERSION_MAX

    def _python_candidates(self) -> list[list[str]]:
        candidates: list[list[str]] = []
        configured = os.getenv("KRONOS_PYTHON", "").strip()
        if configured:
            candidates.append([configured])
        candidates.append([sys.executable])
        if os.name == "nt":
            candidates.extend([["py", "-3.11"], ["py", "-3.10"], ["py", "-3.12"], ["python"]])
        else:
            candidates.extend([["python3.11"], ["python3.10"], ["python3"]])
        unique: list[list[str]] = []
        seen: set[str] = set()
        for command in candidates:
            key = "\0".join(command)
            if key not in seen:
                seen.add(key)
                unique.append(command)
        return unique

    def _run_install_command(
        self,
        command: list[str],
        timeout: int,
        stage: str = "执行安装命令",
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:
            if command and command[0] == "git":
                raise RuntimeError(f"{stage}失败：未找到 Git。请先安装 Git，并确认 git 命令已加入 PATH。") from exc
            raise RuntimeError(f"{stage}失败：命令不存在：{_command_text(command)}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{stage}超时：{_command_text(command)}。"
                "如果正在下载依赖或模型，请检查网络稳定性、代理、防火墙或安全软件拦截。"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stdout = (exc.stdout or "").strip()
            stderr = (exc.stderr or "").strip()
            detail = stderr or stdout or "无输出"
            hint = self._install_failure_hint(stage, detail, exc.returncode)
            raise RuntimeError(
                f"{stage}失败：{_command_text(command)}；返回码 {exc.returncode}；{detail[-800:]}{hint}"
            ) from exc

    def _install_failure_hint(self, stage: str, detail: str, returncode: int) -> str:
        hints: list[str] = []
        lowered = detail.lower()
        if os.name == "nt" and returncode in {3221225786, -1073741510}:
            hints.append("Windows 返回码 3221225786 通常表示 Python 进程被中断、被安全软件拦截或解释器启动异常。")
        if _is_network_error(detail) or stage in {"下载 Kronos 源码", "安装 Kronos 依赖", "下载 HuggingFace 模型"}:
            hints.append(
                "请检查网络、DNS、代理、防火墙或安全软件；需要代理时可设置 HTTPS_PROXY/HTTP_PROXY 后重试。"
            )
        if "no space left" in lowered or "not enough space" in lowered or "errno 28" in lowered:
            hints.append(f"磁盘空间可能不足，建议至少预留 {_format_bytes(MIN_RUNTIME_FREE_BYTES)}。")
        if "permission denied" in lowered or "access is denied" in lowered or "errno 13" in lowered:
            hints.append(f"目录权限可能不足，请确认 {RUNTIME_PATH} 可写，或把项目移动到有写入权限的位置。")
        if "no module named pip" in lowered or "ensurepip" in lowered or stage in {"升级 pip", "修复 pip"}:
            hints.append(
                "当前 Python/虚拟环境缺少 pip。Windows 上请安装完整 Python 并勾选 pip，"
                "或执行 py -3.11 -m ensurepip --upgrade 后重试。"
            )
        if "resolutionimpossible" in lowered or "dependency conflict" in lowered or "conflicting dependencies" in lowered:
            hints.append("Kronos 依赖解析冲突，建议换 Python 3.10/3.11，或删除 .kronos_runtime 后重新安装。")
        if "huggingface" in lowered or "model" in lowered or "401" in lowered or "403" in lowered:
            hints.append("HuggingFace 模型访问失败，请确认网络可访问 huggingface.co，必要时配置 HF_TOKEN 或镜像/代理。")
        return f"；建议：{'；'.join(dict.fromkeys(hints))}" if hints else ""

    def _environment_check_lines(self) -> list[str]:
        checks = [
            f"运行目录：{RUNTIME_PATH}",
            f"Kronos 源码：{'已找到' if self._repo_ready() else '未找到'}",
            f"虚拟环境 Python：{'已找到' if self._venv_python_path().exists() else '未找到'}",
        ]
        if self._venv_python_path().exists():
            checks.append(f"pip：{'可用' if self._pip_ready(self._venv_python()) else '不可用'}")
        return checks

    def _assert_runtime_usable(self, model_name: str) -> None:
        if not self._repo_ready():
            raise RuntimeError(f"未找到 Kronos 源码或 requirements.txt：{REPO_PATH}")
        if not self._venv_python_path().exists():
            raise RuntimeError(f"未找到虚拟环境 Python：{self._venv_python_path()}")
        python = self._venv_python()
        if not self._pip_ready(python):
            raise RuntimeError("虚拟环境 pip 不可用。请先执行安装命令中的 ensurepip 和 pip upgrade。")
        script = (
            "import sys\n"
            "from huggingface_hub import snapshot_download\n"
            f"sys.path.insert(0, {str(REPO_PATH)!r})\n"
            "import pandas\n"
            "from model import Kronos, KronosTokenizer, KronosPredictor\n"
            f"snapshot_download({model_name!r}, local_files_only=True)\n"
            f"snapshot_download({DEFAULT_TOKENIZER!r}, local_files_only=True)\n"
            "print('ok')\n"
        )
        try:
            subprocess.run([python, "-c", script], check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "无输出").strip()
            hint = self._install_failure_hint("检查 Kronos 环境", detail, exc.returncode)
            raise RuntimeError(f"Kronos 环境检查失败：{detail[-800:]}{hint}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Kronos 环境检查超时。请确认虚拟环境和模型缓存可用。") from exc

    def _run_kronos(self, symbol: str, history: list[PriceBar], horizon: int) -> list[PriceBar]:
        self._write_runner()
        payload = {
            "symbol": symbol,
            "model_name": self.settings().model_name,
            "tokenizer_name": DEFAULT_TOKENIZER,
            "horizon": horizon,
            "history": [bar.model_dump(mode="json") for bar in history],
        }
        try:
            process = subprocess.run(
                [self._venv_python(), str(RUNNER_PATH)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=900,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Kronos 预测超时。模型首次下载可能较慢，请检查 HuggingFace 网络、代理或防火墙。") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "无输出").strip()
            hint = self._install_failure_hint("运行 Kronos 模型", detail, exc.returncode)
            raise RuntimeError(f"Kronos 预测失败：返回码 {exc.returncode}；{detail[-800:]}{hint}") from exc
        rows = json.loads(process.stdout)
        now = datetime.now()
        return [
            PriceBar(
                symbol=symbol,
                period="forecast",
                trade_date=date.fromisoformat(row["trade_date"]),
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0)),
                amount=float(row.get("amount", 0)),
                turnover_rate=None,
                adjust="forecast",
                updated_at=now,
            )
            for row in rows
        ]

    def _runtime_ready(self) -> bool:
        return self._repo_ready() and VENV_PATH.exists() and self._venv_python_path().exists()

    def _venv_python_path(self) -> Path:
        return VENV_PATH / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def _venv_python(self) -> str:
        return str(self._venv_python_path())

    def _set_install_status(self, status: str, error: str | None) -> None:
        installed_at = "datetime('now')" if status == "ready" else "installed_at"
        with get_connection() as connection:
            connection.execute(
                f"""
                UPDATE prediction_settings
                SET install_status = ?, last_error = ?, installed_at = {installed_at}, updated_at = datetime('now')
                WHERE id = 1
                """,
                (status, error),
            )

    def _write_runner(self) -> None:
        RUNTIME_PATH.mkdir(parents=True, exist_ok=True)
        RUNNER_PATH.write_text(
            dedent(
                f"""
                import json
                import sys
                from pathlib import Path

                import pandas as pd

                sys.path.insert(0, {str(REPO_PATH)!r})
                from model import Kronos, KronosTokenizer, KronosPredictor

                payload = json.loads(sys.stdin.read())
                history = payload["history"]
                df = pd.DataFrame(history)
                df["timestamp"] = pd.to_datetime(df["timestamp"].where(df["timestamp"].str.contains(" "), df["trade_date"]))
                x_df = df[["open", "high", "low", "close", "volume", "amount"]].tail(512).reset_index(drop=True)
                x_timestamp = df["timestamp"].tail(512).reset_index(drop=True)
                last_ts = x_timestamp.iloc[-1]
                y_timestamp = pd.bdate_range(last_ts + pd.Timedelta(days=1), periods=payload["horizon"])

                tokenizer = KronosTokenizer.from_pretrained(payload["tokenizer_name"])
                model = Kronos.from_pretrained(payload["model_name"])
                predictor = KronosPredictor(model, tokenizer, max_context=512)
                pred = predictor.predict(
                    df=x_df,
                    x_timestamp=x_timestamp,
                    y_timestamp=pd.Series(y_timestamp),
                    pred_len=payload["horizon"],
                    T=1.0,
                    top_p=0.9,
                    sample_count=1,
                )
                pred = pred.reset_index(drop=True)
                rows = []
                for index, ts in enumerate(y_timestamp):
                    row = pred.iloc[index]
                    rows.append({{
                        "trade_date": ts.date().isoformat(),
                        "timestamp": ts.date().isoformat(),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row.get("volume", 0)),
                        "amount": float(row.get("amount", 0)),
                    }})
                print(json.dumps(rows))
                """
            ),
            encoding="utf-8",
        )


prediction_service = PredictionService()
