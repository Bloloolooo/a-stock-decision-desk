import { useEffect, useMemo, useState } from "react";
import { createChart, ColorType, type IChartApi, type UTCTimestamp } from "lightweight-charts";

import { api } from "./api";
import type { MarketStatus, PortfolioSummary, Position, PriceBar, RiskAdvice, ScreenerResult } from "./types";

const emptySummary: PortfolioSummary = {
  total_assets: 0,
  cash: 0,
  position_market_value: 0,
  floating_pnl: 0,
  today_pnl: 0,
  updated_at: new Date().toISOString(),
};

function yuan(value: number) {
  return `¥${value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function pct(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${yuan(value)}`;
}

export default function App() {
  const [tab, setTab] = useState<"home" | "screener" | "review" | "settings">("home");
  const [selectedSymbol, setSelectedSymbol] = useState("300308");
  const [period, setPeriod] = useState("daily");
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary);
  const [positions, setPositions] = useState<Position[]>([]);
  const [bars, setBars] = useState<PriceBar[]>([]);
  const [risk, setRisk] = useState<RiskAdvice | null>(null);
  const [trend, setTrend] = useState<ScreenerResult[]>([]);
  const [rebound, setRebound] = useState<ScreenerResult[]>([]);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [status, setStatus] = useState("加载中");

  const reloadPortfolio = () => {
    return Promise.all([api.summary(), api.positions()])
      .then(([summaryData, positionData]) => {
        setSummary(summaryData);
        setPositions(positionData);
      });
  };

  const reloadMarket = () => {
    setStatus("刷新行情中");
    return Promise.all([api.bars(selectedSymbol, period), api.risk(selectedSymbol), api.marketStatus()])
      .then(([barData, riskData, marketStatusData]) => {
        setBars(barData);
        setRisk(riskData);
        setMarketStatus(marketStatusData);
        setStatus(`${marketStatusData.description}已更新`);
      })
      .catch(() => setStatus("行情刷新失败"));
  };

  useEffect(() => {
    Promise.all([api.summary(), api.positions(), api.screener("trend"), api.screener("rebound"), api.marketStatus()])
      .then(([summaryData, positionData, trendData, reboundData, marketStatusData]) => {
        setSummary(summaryData);
        setPositions(positionData);
        setTrend(trendData);
        setRebound(reboundData);
        setMarketStatus(marketStatusData);
        setStatus(`${marketStatusData.description}已更新`);
      })
      .catch(() => setStatus("后端未连接，等待数据"));
  }, []);

  useEffect(() => {
    reloadMarket();
  }, [selectedSymbol, period]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>A 股决策台</h1>
          <p>本地 Web 工具 · 手动持仓 · 规则因子 · 风控建议</p>
        </div>
        <nav className="tabs">
          <button className={tab === "home" ? "active" : ""} onClick={() => setTab("home")}>主页</button>
          <button className={tab === "screener" ? "active" : ""} onClick={() => setTab("screener")}>选股雷达</button>
          <button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>策略回看</button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>设置</button>
        </nav>
        <div className="data-status">{status}</div>
      </header>

      {tab === "home" && (
        <HomePage
          summary={summary}
          positions={positions}
          bars={bars}
          risk={risk}
          selectedSymbol={selectedSymbol}
          period={period}
          onSelectSymbol={setSelectedSymbol}
          onPeriodChange={setPeriod}
          onPortfolioChange={reloadPortfolio}
          onRefreshMarket={reloadMarket}
          marketStatus={marketStatus}
        />
      )}
      {tab === "screener" && (
        <ScreenerPage
          trend={trend}
          rebound={rebound}
          onOpen={(symbol) => {
            setSelectedSymbol(symbol);
            setTab("home");
          }}
        />
      )}
      {tab === "review" && <Placeholder title="策略回看" text="这里会展示历史榜单、候选后续表现和交易备注复盘。" />}
      {tab === "settings" && <Placeholder title="设置" text="这里会配置数据源、风险参数、指标参数和本地备份。" />}
    </div>
  );
}

function HomePage(props: {
  summary: PortfolioSummary;
  positions: Position[];
  bars: PriceBar[];
  risk: RiskAdvice | null;
  selectedSymbol: string;
  period: string;
  onSelectSymbol: (symbol: string) => void;
  onPeriodChange: (period: string) => void;
  onPortfolioChange: () => Promise<void>;
  onRefreshMarket: () => Promise<void>;
  marketStatus: MarketStatus | null;
}) {
  const selectedPosition = props.positions.find((position) => position.symbol === props.selectedSymbol);
  const [cashValue, setCashValue] = useState(String(Math.round(props.summary.cash)));
  const [positionForm, setPositionForm] = useState({
    symbol: "",
    quantity: "",
    average_cost: "",
  });
  const [formStatus, setFormStatus] = useState("");

  useEffect(() => {
    setCashValue(String(Math.round(props.summary.cash)));
  }, [props.summary.cash]);

  const saveCash = async () => {
    await api.updateCash(Number(cashValue));
    await props.onPortfolioChange();
    setFormStatus("现金已更新");
  };

  const savePosition = async () => {
    await api.upsertPosition({
      symbol: positionForm.symbol.trim(),
      quantity: Number(positionForm.quantity),
      average_cost: Number(positionForm.average_cost),
    });
    await props.onPortfolioChange();
    props.onSelectSymbol(positionForm.symbol.trim());
    setPositionForm({ symbol: "", quantity: "", average_cost: "" });
    setFormStatus("持仓已保存");
  };

  return (
    <>
      <section className="metrics-grid">
        <Metric label="总资产" value={yuan(props.summary.total_assets)} />
        <Metric label="可用现金" value={yuan(props.summary.cash)} />
        <Metric label="持仓市值" value={yuan(props.summary.position_market_value)} />
        <Metric label="持仓盈亏" value={signed(props.summary.floating_pnl)} tone={props.summary.floating_pnl >= 0 ? "up" : "down"} />
        <Metric label="今日盈亏" value={signed(props.summary.today_pnl)} tone={props.summary.today_pnl >= 0 ? "up" : "down"} />
      </section>

      <main className="home-grid">
        <aside className="panel watchlist">
          <div className="panel-title">
            <h2>持仓 / 自选</h2>
            <button>+ 添加</button>
          </div>
          <div className="stock-list">
            {props.positions.map((position) => (
              <button
                key={position.symbol}
                className={`stock-row ${props.selectedSymbol === position.symbol ? "selected" : ""}`}
                onClick={() => props.onSelectSymbol(position.symbol)}
              >
                <span>
                  <strong>{position.name}</strong>
                  <small>{position.symbol} · 持 {position.quantity} 股</small>
                </span>
                <span className={position.floating_pnl >= 0 ? "up" : "down"}>
                  {pct(position.floating_pnl_pct)}
                </span>
              </button>
            ))}
          </div>
          <div className="entry-form">
            <h3>账户录入</h3>
            <label>
              可用现金
              <input value={cashValue} onChange={(event) => setCashValue(event.target.value)} inputMode="decimal" />
            </label>
            <button onClick={saveCash}>保存现金</button>
            <h3>持仓录入</h3>
            <label>
              代码
              <input value={positionForm.symbol} onChange={(event) => setPositionForm({ ...positionForm, symbol: event.target.value })} placeholder="300308" />
            </label>
            <label>
              数量
              <input value={positionForm.quantity} onChange={(event) => setPositionForm({ ...positionForm, quantity: event.target.value })} inputMode="numeric" />
            </label>
            <label>
              买入均价
              <input value={positionForm.average_cost} onChange={(event) => setPositionForm({ ...positionForm, average_cost: event.target.value })} inputMode="decimal" />
            </label>
            <button onClick={savePosition} disabled={!positionForm.symbol || !positionForm.quantity || !positionForm.average_cost}>
              保存持仓
            </button>
            <span className="entry-hint">名称会根据代码自动匹配。</span>
            {formStatus && <p>{formStatus}</p>}
          </div>
        </aside>

        <section className="panel chart-panel">
          <div className="chart-header">
            <div>
              <h2>{props.risk?.name ?? selectedPosition?.name ?? props.selectedSymbol} <span>{props.selectedSymbol}</span></h2>
              <p>现价 {props.risk?.current_price.toFixed(2) ?? "--"} · 成本 {selectedPosition?.average_cost.toFixed(2) ?? "--"} · 数据源 {props.marketStatus?.description ?? "--"}</p>
            </div>
            <div className="chart-actions">
              <div className="periods">
                {["intraday", "5d", "daily", "weekly", "monthly"].map((item) => (
                  <button key={item} className={props.period === item ? "active" : ""} onClick={() => props.onPeriodChange(item)}>
                    {periodLabel(item)}
                  </button>
                ))}
              </div>
              <button className="refresh-button" onClick={props.onRefreshMarket}>刷新行情</button>
            </div>
          </div>
          <KLineChart bars={props.bars} />
          <div className="position-strip">
            <MiniStat label="买入成本" value={selectedPosition ? `${selectedPosition.average_cost.toFixed(2)} · ${selectedPosition.quantity} 股` : "无持仓"} />
            <MiniStat label="浮动盈亏" value={selectedPosition ? `${signed(selectedPosition.floating_pnl)} · ${pct(selectedPosition.floating_pnl_pct)}` : "--"} tone={selectedPosition && selectedPosition.floating_pnl >= 0 ? "up" : "down"} />
            <MiniStat label="止损参考" value={props.risk ? `${props.risk.stop_loss_price.toFixed(2)} · 风险 ${yuan(props.risk.single_stock_risk)}` : "--"} />
            <MiniStat label="建议仓位" value={props.risk ? `${(props.risk.suggested_min_ratio * 100).toFixed(0)}-${(props.risk.suggested_max_ratio * 100).toFixed(0)}%` : "--"} />
          </div>
        </section>

        <aside className="advisor">
          <section className="panel">
            <h2>风控建议</h2>
            <p>{props.risk?.message ?? "等待风控建议。"}</p>
          </section>
          <section className="panel">
            <h2>信号来源</h2>
            <ul className="signals">
              {(props.risk?.signal_sources ?? ["等待数据"]).map((signal) => <li key={signal}>{signal}</li>)}
            </ul>
          </section>
          <details className="panel advice-drawer">
            <summary>操作建议</summary>
            <p>当前最大可加仓金额：{props.risk ? yuan(props.risk.max_buy_amount) : "--"}。跌破止损线后优先减仓，任何操作都应结合盘中成交量确认。</p>
          </details>
        </aside>
      </main>
    </>
  );
}

function KLineChart({ bars }: { bars: PriceBar[] }) {
  const chartData = useMemo(
    () => bars.map((bar) => ({
      time: bar.trade_date as unknown as UTCTimestamp,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    })),
    [bars],
  );

  return (
    <div
      className="chart-canvas"
      ref={(container) => {
        if (!container || chartData.length === 0) return;
        container.replaceChildren();
        const chart: IChartApi = createChart(container, {
          layout: { background: { type: ColorType.Solid, color: "#0f1724" }, textColor: "#9aa8bd" },
          grid: { vertLines: { color: "#1c2940" }, horzLines: { color: "#1c2940" } },
          rightPriceScale: { borderColor: "#253145" },
          timeScale: { borderColor: "#253145", timeVisible: true },
          crosshair: { mode: 1 },
          width: container.clientWidth,
          height: container.clientHeight,
        });
        const candleSeries = chart.addCandlestickSeries({
          upColor: "#d94b42",
          downColor: "#14a06f",
          borderUpColor: "#d94b42",
          borderDownColor: "#14a06f",
          wickUpColor: "#d94b42",
          wickDownColor: "#14a06f",
        });
        candleSeries.setData(chartData);
        chart.timeScale().fitContent();
      }}
    />
  );
}

function ScreenerPage(props: { trend: ScreenerResult[]; rebound: ScreenerResult[]; onOpen: (symbol: string) => void }) {
  return (
    <main className="screener-grid">
      <aside className="panel filters">
        <h2>筛选条件</h2>
        <Filter label="市场" value="沪深 A 股" />
        <Filter label="周期" value="短线 / 波段" />
        <Filter label="行业" value="全部" />
        <Filter label="流动性" value="成交额 > 3 亿" />
        <Filter label="风险过滤" value="开启" />
        <div className="filter-note">排除 ST、停牌、退市风险、流动性过低和连续一字板不可交易标的。</div>
      </aside>
      <section className="screener-main">
        <div className="market-pulse">
          <Metric label="今日强势行业" value="算力 / CPO" />
          <Metric label="涨停家数" value="61" tone="up" />
          <Metric label="跌停家数" value="9" tone="down" />
          <Metric label="市场情绪" value="偏强" />
        </div>
        <div className="lists-grid">
          <ResultList title="趋势追强榜" subtitle="找正在走强的行业龙头和趋势候选" rows={props.trend} onOpen={props.onOpen} />
          <ResultList title="超跌反弹榜" subtitle="找跌幅充分但出现企稳迹象的候选" rows={props.rebound} onOpen={props.onOpen} />
        </div>
      </section>
    </main>
  );
}

function ResultList(props: { title: string; subtitle: string; rows: ScreenerResult[]; onOpen: (symbol: string) => void }) {
  return (
    <section className="panel result-list">
      <div className="panel-title">
        <div>
          <h2>{props.title}</h2>
          <p>{props.subtitle}</p>
        </div>
        <button>查看因子</button>
      </div>
      <table>
        <thead>
          <tr><th>股票</th><th>评分</th><th>涨跌</th><th>原因</th><th>动作</th></tr>
        </thead>
        <tbody>
          {props.rows.map((row) => (
            <tr key={row.symbol}>
              <td><strong>{row.name}</strong><small>{row.symbol}</small></td>
              <td className="score">{row.score}</td>
              <td className={row.change_pct >= 0 ? "up" : "down"}>{row.change_pct >= 0 ? "+" : ""}{row.change_pct.toFixed(2)}%</td>
              <td>{row.reason}</td>
              <td><button className="link-button" onClick={() => props.onOpen(row.symbol)}>看走势</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" | false }) {
  return (
    <div className="mini-stat">
      <span>{label}</span>
      <strong className={tone || undefined}>{value}</strong>
    </div>
  );
}

function Filter({ label, value }: { label: string; value: string }) {
  return (
    <div className="filter-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <section className="panel placeholder">
      <h2>{title}</h2>
      <p>{text}</p>
    </section>
  );
}

function periodLabel(period: string) {
  const labels: Record<string, string> = {
    intraday: "分时",
    "5d": "5日",
    daily: "日K",
    weekly: "周K",
    monthly: "月K",
  };
  return labels[period] ?? period;
}
