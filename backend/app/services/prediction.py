from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
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


def _command_text(command: list[str]) -> str:
    return " ".join(command)


class PredictionService:
    def __init__(self) -> None:
        init_db()
        self._install_lock = threading.Lock()

    def status(self) -> PredictionStatus:
        settings = self.settings()
        ready = settings.enabled and settings.install_status == "ready" and self._runtime_ready()
        return PredictionStatus(**settings.model_dump(), runtime_path=str(RUNTIME_PATH), ready=ready)

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
            connection.execute(
                """
                UPDATE prediction_settings
                SET enabled = ?, model_name = ?, tokenizer_name = ?, install_status = ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (1 if enabled else 0, model, DEFAULT_TOKENIZER, install_status),
            )
        if enabled and not self.status().ready:
            self.install_async()
        return self.status()

    def install_async(self) -> PredictionStatus:
        settings = self.settings()
        if settings.install_status == "ready" and self._runtime_ready():
            return self.status()
        if not self._install_lock.acquire(blocking=False):
            return self.status()
        self._set_install_status("installing", None)
        thread = threading.Thread(target=self._install, daemon=True)
        thread.start()
        return self.status()

    def predict(self, symbol: str, horizon: int = 20) -> PredictionResult:
        status = self.status()
        if not status.enabled:
            raise RuntimeError("预测功能尚未启用")
        if not status.ready:
            raise RuntimeError("Kronos 运行环境尚未就绪")
        history = market_data.bars(symbol=symbol, period="daily")[-120:]
        forecast = self._run_kronos(symbol=symbol, history=history, horizon=max(1, min(horizon, 60)))
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
            RUNTIME_PATH.mkdir(parents=True, exist_ok=True)
            if not REPO_PATH.exists():
                subprocess.run(
                    ["git", "clone", "--depth", "1", "https://github.com/shiyu-coder/Kronos.git", str(REPO_PATH)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
            self._ensure_venv()
            python = self._venv_python()
            self._run_install_command([python, "-m", "pip", "install", "--upgrade", "pip"], timeout=300)
            self._run_install_command(
                [python, "-m", "pip", "install", "-r", str(REPO_PATH / "requirements.txt")],
                timeout=1200,
            )
            self._write_runner()
            self._set_install_status("ready", None)
        except Exception as exc:
            self._set_install_status("failed", str(exc)[-500:])
        finally:
            self._install_lock.release()

    def _ensure_venv(self) -> None:
        python_path = self._venv_python_path()
        if VENV_PATH.exists() and python_path.exists():
            return
        if VENV_PATH.exists() and not python_path.exists():
            shutil.rmtree(VENV_PATH, ignore_errors=True)
        errors: list[str] = []
        for command in self._python_candidates():
            create_command = [
                *command,
                "-m",
                "venv",
                *(["--copies"] if os.name == "nt" else []),
                str(VENV_PATH),
            ]
            try:
                self._run_install_command(create_command, timeout=300)
                if python_path.exists():
                    return
                errors.append(f"{_command_text(create_command)} 执行完成但未生成 {python_path}")
            except Exception as exc:
                shutil.rmtree(VENV_PATH, ignore_errors=True)
                errors.append(str(exc))
        raise RuntimeError(
            "Kronos Python 虚拟环境创建失败。"
            "Windows 上可先安装完整 Python 3.10/3.11/3.12，并设置环境变量 KRONOS_PYTHON 指向 python.exe 后重试。"
            f"最近错误：{errors[-1] if errors else '没有可用 Python'}"
        )

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

    def _run_install_command(self, command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise RuntimeError(f"命令不存在：{_command_text(command)}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"命令超时：{_command_text(command)}") from exc
        except subprocess.CalledProcessError as exc:
            stdout = (exc.stdout or "").strip()
            stderr = (exc.stderr or "").strip()
            detail = stderr or stdout or "无输出"
            if os.name == "nt" and exc.returncode in {3221225786, -1073741510}:
                detail = f"{detail}；Windows 返回码 3221225786 通常表示 Python 进程被中断、被安全软件拦截或解释器启动异常。"
            raise RuntimeError(f"命令失败：{_command_text(command)}；返回码 {exc.returncode}；{detail[-800:]}") from exc

    def _run_kronos(self, symbol: str, history: list[PriceBar], horizon: int) -> list[PriceBar]:
        self._write_runner()
        payload = {
            "symbol": symbol,
            "model_name": self.settings().model_name,
            "tokenizer_name": DEFAULT_TOKENIZER,
            "horizon": horizon,
            "history": [bar.model_dump(mode="json") for bar in history],
        }
        process = subprocess.run(
            [self._venv_python(), str(RUNNER_PATH)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=900,
            check=True,
        )
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
        return REPO_PATH.exists() and VENV_PATH.exists() and self._venv_python_path().exists()

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
