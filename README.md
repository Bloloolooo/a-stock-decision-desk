# A 股本地决策台

个人本地使用的 A 股短线/波段 Web 工具。第一版聚焦账户概览、手动持仓、专业走势页面、风控建议和两类选股雷达。

## 目录

- `backend/`: FastAPI API、SQLite、指标、风控和选股服务。
- `frontend/`: React + TypeScript + Vite 前端。
- `docs/`: 设计规格和实施计划。

## 本地启动

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

默认数据库为 `backend/stock_tool.sqlite3`。这个文件只保存在本机，不提交到仓库。

默认行情源使用 Tencent/Sina 公开行情，避免 AkShare 在部分 macOS/Python 环境下触发 `mini_racer` 原生库崩溃。要强制使用离线示例数据：

```bash
cd backend
MARKET_DATA_PROVIDER=sample .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

如确需使用 AkShare，可显式开启：

```bash
cd backend
ENABLE_AKSHARE=1 .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

然后打开 Vite 输出的本地地址。前端默认访问 `http://localhost:8000/api`。

## 当前边界

- 不接券商账户。
- 不自动下单。
- 不做实时机器学习训练。
- 外部行情源后续通过 `MarketDataProvider` 接入；当前先提供可运行的示例数据。
