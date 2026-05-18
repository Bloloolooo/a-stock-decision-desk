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
uvicorn app.main:app --reload --port 8000
```

默认数据库为 `backend/stock_tool.sqlite3`。这个文件只保存在本机，不提交到仓库。

默认行情源优先使用 AkShare 真实行情，失败时回退到示例数据。要强制使用离线示例数据：

```bash
cd backend
MARKET_DATA_PROVIDER=sample .venv/bin/uvicorn app.main:app --reload --port 8000
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
