import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { createChart, ColorType, type IChartApi, type UTCTimestamp } from "lightweight-charts";

import { api } from "./api";
import type { MarketPeriod, MarketStatus, PortfolioSummary, Position, PriceBar, RiskAdvice, ScreenerConfig, ScreenerResult, ScreenerStatus, TradeRecord } from "./types";

const emptySummary: PortfolioSummary = {
  total_assets: 0,
  cash: 0,
  position_market_value: 0,
  floating_pnl: 0,
  today_pnl: 0,
  updated_at: new Date().toISOString(),
};

const defaultPeriods: MarketPeriod[] = [
  { key: "intraday", label: "分时", description: "1 分钟线", available: true },
  { key: "5d", label: "5日", description: "近 5 日 1 分钟线", available: true },
  { key: "daily", label: "日K", description: "日线", available: true },
  { key: "weekly", label: "周K", description: "周线", available: true },
  { key: "monthly", label: "月K", description: "月线", available: true },
];

const defaultScreenerSymbols = [
  "300308",
  "300502",
  "601138",
  "300750",
  "600519",
  "002594",
  "000858",
  "600036",
  "601318",
  "600276",
  "002415",
  "000063",
  "603259",
  "600795",
  "600312",
  "603871",
];

function yuan(value: number) {
  return `¥${value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function moneyInput(value: number) {
  return Number.isFinite(value) ? value.toFixed(2) : "";
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
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [bars, setBars] = useState<PriceBar[]>([]);
  const [risk, setRisk] = useState<RiskAdvice | null>(null);
  const [trend, setTrend] = useState<ScreenerResult[]>([]);
  const [rebound, setRebound] = useState<ScreenerResult[]>([]);
  const [screenerConfig, setScreenerConfig] = useState<ScreenerConfig | null>(null);
  const [screenerStatus, setScreenerStatus] = useState<ScreenerStatus | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [periods, setPeriods] = useState<MarketPeriod[]>(defaultPeriods);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(10);
  const [status, setStatus] = useState("加载中");

  const reloadPortfolio = () => {
    return Promise.all([api.summary(), api.positions()])
      .then(([summaryData, positionData]) => {
        setSummary(summaryData);
        setPositions(positionData);
        return api.trades()
          .then(setTrades)
          .catch(() => undefined);
      });
  };

  const reloadMarket = () => {
    setStatus("刷新行情中");
    return api.bars(selectedSymbol, period)
      .then((barData) => {
        setBars(barData);
        return Promise.all([api.risk(selectedSymbol), api.marketStatus()]);
      })
      .then((result) => {
        const riskData = result[0] as RiskAdvice;
        const marketStatusData = result[1] as MarketStatus;
        setRisk(riskData);
        setMarketStatus(marketStatusData);
        setStatus(`${marketStatusData.description}已更新`);
      })
      .catch(() => setStatus("行情刷新失败"));
  };

  const reloadScreener = () => {
    return Promise.all([api.screener("trend"), api.screener("rebound"), api.screenerStatus()])
      .then(([trendData, reboundData, statusData]) => {
        setTrend(trendData);
        setRebound(reboundData);
        setScreenerStatus(statusData);
      });
  };

  const refreshScreener = () => {
    setStatus("刷新选股雷达中");
    return api.refreshScreener()
      .then((statusData) => {
        setScreenerStatus(statusData);
        return reloadScreener();
      })
      .then(() => setStatus("选股雷达已更新"))
      .catch(() => setStatus("选股雷达刷新失败"));
  };

  const saveScreenerSymbols = (symbols: string[]) => {
    return api.updateScreenerConfig(symbols)
      .then((configData) => {
        setScreenerConfig(configData);
        return refreshScreener();
      });
  };

  useEffect(() => {
    Promise.all([api.summary(), api.positions(), api.trades(), api.screenerConfig(), api.screenerStatus(), api.marketStatus(), api.marketPeriods()])
      .then(([summaryData, positionData, tradeData, configData, statusData, marketStatusData, periodData]) => {
        setSummary(summaryData);
        setPositions(positionData);
        setTrades(tradeData);
        setScreenerConfig(configData);
        setScreenerStatus(statusData);
        setMarketStatus(marketStatusData);
        setPeriods(periodData);
        setStatus(`${marketStatusData.description}已更新`);
      })
      .catch(() => setStatus("后端未连接，等待数据"));
    reloadScreener().catch(() => undefined);
  }, []);

  useEffect(() => {
    reloadMarket();
  }, [selectedSymbol, period]);

  useEffect(() => {
    if (autoRefreshSeconds <= 0) return;
    const timer = window.setInterval(() => {
      reloadMarket();
    }, autoRefreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefreshSeconds, selectedSymbol, period]);

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
          periods={periods}
          autoRefreshSeconds={autoRefreshSeconds}
          onAutoRefreshSecondsChange={setAutoRefreshSeconds}
        />
      )}
      {tab === "screener" && (
        <ScreenerPage
          trend={trend}
          rebound={rebound}
          config={screenerConfig}
          status={screenerStatus}
          onRefresh={refreshScreener}
          onSaveSymbols={saveScreenerSymbols}
          onOpen={(symbol) => {
            setSelectedSymbol(symbol);
            setTab("home");
          }}
        />
      )}
      {tab === "review" && <ReviewPage trades={trades} positions={positions} summary={summary} />}
      {tab === "settings" && (
        <SettingsPage
          marketStatus={marketStatus}
          autoRefreshSeconds={autoRefreshSeconds}
          onAutoRefreshSecondsChange={setAutoRefreshSeconds}
          screenerConfig={screenerConfig}
          screenerStatus={screenerStatus}
          onSaveScreenerSymbols={saveScreenerSymbols}
        />
      )}
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
  periods: MarketPeriod[];
  autoRefreshSeconds: number;
  onAutoRefreshSecondsChange: (seconds: number) => void;
}) {
  const selectedPosition = props.positions.find((position) => position.symbol === props.selectedSymbol);
  const symbolInputRef = useRef<HTMLInputElement>(null);
  const [cashValue, setCashValue] = useState(moneyInput(props.summary.cash));
  const [positionForm, setPositionForm] = useState({
    symbol: "",
    quantity: "",
    average_cost: "",
  });
  const [sellForm, setSellForm] = useState({
    symbol: props.selectedSymbol,
    quantity: "",
    sell_price: "",
  });
  const [fullscreen, setFullscreen] = useState(false);
  const [formStatus, setFormStatus] = useState("");

  useEffect(() => {
    setCashValue(moneyInput(props.summary.cash));
  }, [props.summary.cash]);

  useEffect(() => {
    setSellForm((current) => ({ ...current, symbol: props.selectedSymbol }));
  }, [props.selectedSymbol]);

  const saveCash = async () => {
    const cash = Number(cashValue);
    if (!Number.isFinite(cash) || cash < 0) {
      setFormStatus("现金格式有误，请输入大于等于 0 的数字。");
      return;
    }
    await api.updateCash(Number(cash.toFixed(2)));
    await props.onPortfolioChange();
    setFormStatus("现金已更新");
  };

  const savePosition = async () => {
    try {
      await api.upsertPosition({
        symbol: positionForm.symbol.trim(),
        quantity: Number(positionForm.quantity),
        average_cost: Number(positionForm.average_cost),
      });
      await props.onPortfolioChange();
      props.onSelectSymbol(positionForm.symbol.trim());
      setPositionForm({ symbol: "", quantity: "", average_cost: "" });
      setFormStatus("持仓已保存");
    } catch {
      setFormStatus("保存失败，请检查代码、数量和后端连接。");
    }
  };

  const sellPosition = async () => {
    try {
      await api.sellPosition({
        symbol: sellForm.symbol.trim(),
        quantity: Number(sellForm.quantity),
        sell_price: Number(sellForm.sell_price),
      });
      await props.onPortfolioChange();
      setSellForm({ symbol: props.selectedSymbol, quantity: "", sell_price: "" });
      setFormStatus("卖出已记录");
    } catch {
      setFormStatus("卖出失败，请检查持仓数量和后端连接。");
    }
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
            <button onClick={() => symbolInputRef.current?.focus()}>+ 添加</button>
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
              <input ref={symbolInputRef} value={positionForm.symbol} onChange={(event) => setPositionForm({ ...positionForm, symbol: event.target.value })} placeholder="300308" />
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
            <h3>卖出记录</h3>
            <label>
              代码
              <input value={sellForm.symbol} onChange={(event) => setSellForm({ ...sellForm, symbol: event.target.value })} placeholder="300308" />
            </label>
            <label>
              卖出数量
              <input value={sellForm.quantity} onChange={(event) => setSellForm({ ...sellForm, quantity: event.target.value })} inputMode="numeric" />
            </label>
            <label>
              卖出价格
              <input value={sellForm.sell_price} onChange={(event) => setSellForm({ ...sellForm, sell_price: event.target.value })} inputMode="decimal" />
            </label>
            <button onClick={sellPosition} disabled={!sellForm.symbol || !sellForm.quantity || !sellForm.sell_price}>
              记录卖出
            </button>
          </div>
        </aside>

        <section className="panel chart-panel">
          <StockTabs positions={props.positions} selectedSymbol={props.selectedSymbol} onSelectSymbol={props.onSelectSymbol} />
          <div className="chart-header">
            <div>
              <h2>{props.risk?.name ?? selectedPosition?.name ?? props.selectedSymbol} <span>{props.selectedSymbol}</span></h2>
              <p>现价 {props.risk?.current_price.toFixed(2) ?? "--"} · 成本 {selectedPosition?.average_cost.toFixed(2) ?? "--"} · 数据源 {props.marketStatus?.description ?? "--"}</p>
            </div>
            <div className="chart-actions">
              <div className="periods">
                {props.periods.map((item) => (
                  <button key={item.key} className={props.period === item.key ? "active" : ""} disabled={!item.available} onClick={() => props.onPeriodChange(item.key)}>
                    <span>{item.label}</span>
                    <small>{item.description}</small>
                  </button>
                ))}
              </div>
              <div className="refresh-controls">
                <select value={props.autoRefreshSeconds} onChange={(event) => props.onAutoRefreshSecondsChange(Number(event.target.value))}>
                  <option value={5}>5 秒</option>
                  <option value={10}>10 秒</option>
                  <option value={30}>30 秒</option>
                  <option value={60}>60 秒</option>
                  <option value={0}>暂停</option>
                </select>
                <button className="refresh-button" onClick={props.onRefreshMarket}>刷新行情</button>
                <button className="refresh-button" onClick={() => setFullscreen(true)}>全屏</button>
              </div>
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
            <ul className="signals">
              {(props.risk?.action_suggestions ?? ["等待数据"]).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </details>
        </aside>
      </main>
      {fullscreen && (
        <div className="fullscreen-chart" role="dialog" aria-modal="true">
          <div className="fullscreen-top">
            <StockTabs positions={props.positions} selectedSymbol={props.selectedSymbol} onSelectSymbol={props.onSelectSymbol} />
            <button className="close-button" onClick={() => setFullscreen(false)}>退出全屏</button>
          </div>
          <div className="fullscreen-toolbar">
            <div>
              <h2>{props.risk?.name ?? selectedPosition?.name ?? props.selectedSymbol} <span>{props.selectedSymbol}</span></h2>
              <p>现价 {props.risk?.current_price.toFixed(2) ?? "--"} · {props.marketStatus?.description ?? "--"}</p>
            </div>
            <div className="periods">
              {props.periods.map((item) => (
                <button key={item.key} className={props.period === item.key ? "active" : ""} disabled={!item.available} onClick={() => props.onPeriodChange(item.key)}>
                  <span>{item.label}</span>
                  <small>{item.description}</small>
                </button>
              ))}
            </div>
          </div>
          <KLineChart bars={props.bars} mode="fullscreen" />
        </div>
      )}
    </>
  );
}

function StockTabs(props: { positions: Position[]; selectedSymbol: string; onSelectSymbol: (symbol: string) => void }) {
  const hasSelectedPosition = props.positions.some((position) => position.symbol === props.selectedSymbol);
  return (
    <div className="stock-tabs">
      {!hasSelectedPosition && (
        <button className="active" onClick={() => props.onSelectSymbol(props.selectedSymbol)}>
          <span>{props.selectedSymbol}</span>
          <small>当前查看</small>
        </button>
      )}
      {props.positions.map((position) => (
        <button
          key={position.symbol}
          className={props.selectedSymbol === position.symbol ? "active" : ""}
          onClick={() => props.onSelectSymbol(position.symbol)}
        >
          <span>{position.name}</span>
          <small>{position.symbol}</small>
        </button>
      ))}
    </div>
  );
}

function chinaMarketTime(bar: PriceBar): UTCTimestamp | string {
  if (!bar.timestamp.includes(" ")) {
    return bar.trade_date;
  }
  const match = bar.timestamp.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!match) {
    return bar.trade_date;
  }
  const [, year, month, day, hour, minute, second = "00"] = match;
  return Math.floor(
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    ) / 1000,
  ) as UTCTimestamp;
}

function KLineChart({ bars, mode = "normal" }: { bars: PriceBar[]; mode?: "normal" | "fullscreen" }) {
  const chartData = useMemo(
    () => bars.map((bar) => ({
      time: chinaMarketTime(bar),
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
      data-mode={mode}
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

function normalizeSymbols(symbols: string[]) {
  const seen = new Set<string>();
  return symbols
    .map((symbol) => symbol.replace(/\D/g, ""))
    .filter((symbol) => {
      if (symbol.length !== 6 || seen.has(symbol)) return false;
      seen.add(symbol);
      return true;
    });
}

function ScreenerPage(props: {
  trend: ScreenerResult[];
  rebound: ScreenerResult[];
  config: ScreenerConfig | null;
  status: ScreenerStatus | null;
  onRefresh: () => Promise<void>;
  onSaveSymbols: (symbols: string[]) => Promise<void>;
  onOpen: (symbol: string) => void;
}) {
  const [view, setView] = useState<"lists" | "manage">("lists");
  const [newSymbol, setNewSymbol] = useState("");
  const [manageStatus, setManageStatus] = useState("");
  const allRows = [...props.trend, ...props.rebound];
  const generatedAt = allRows[0]?.generated_at ? new Date(allRows[0].generated_at).toLocaleString("zh-CN", { hour12: false }) : "--";
  const passCount = allRows.filter((row) => row.risk_status === "通过").length;
  const strongCount = props.trend.filter((row) => row.score >= 75).length;
  const reboundCount = props.rebound.filter((row) => row.score >= 70).length;
  const cacheAge = props.status?.cache_age_seconds == null ? "--" : `${props.status.cache_age_seconds} 秒`;
  const configuredSymbols = props.config?.symbols ?? [];
  const activeSymbols = props.status?.symbols ?? (configuredSymbols.length > 0 ? configuredSymbols : defaultScreenerSymbols);
  const isUsingDefaultPool = configuredSymbols.length === 0;

  const saveSymbols = async (symbols: string[], message: string) => {
    const normalized = normalizeSymbols(symbols);
    await props.onSaveSymbols(normalized);
    setManageStatus(message);
  };

  const addSymbol = async () => {
    const symbol = newSymbol.replace(/\D/g, "");
    if (symbol.length !== 6) {
      setManageStatus("请输入 6 位股票代码。");
      return;
    }
    const base = isUsingDefaultPool ? activeSymbols : configuredSymbols;
    await saveSymbols([...base, symbol], "股票池已新增并刷新。");
    setNewSymbol("");
  };

  const removeSymbol = async (symbol: string) => {
    const base = isUsingDefaultPool ? activeSymbols : configuredSymbols;
    await saveSymbols(base.filter((item) => item !== symbol), "股票池已删除并刷新。");
  };

  const resetPool = async () => {
    await props.onSaveSymbols([]);
    setManageStatus("已恢复默认核心池。");
  };

  return (
    <main className="screener-grid">
      <aside className="panel filters">
        <h2>筛选条件</h2>
        <Filter label="市场" value="沪深 A 股核心池" />
        <Filter label="周期" value="短线 / 波段" />
        <Filter label="策略" value="趋势追强 + 超跌修复" />
        <Filter label="流动性" value="5日均额 > 3000 万" />
        <Filter label="风险过滤" value="开启" />
        <Filter label="股票池" value={`${props.status?.pool_size ?? 0} 只`} />
        <Filter label="缓存年龄" value={cacheAge} />
        <div className="filter-note">当前先扫描核心股票池，基于真实日 K 计算涨跌幅、均线、回撤、量能和风险状态。下一步可升级为盘后全 A 股缓存扫描。</div>
        <div className="side-actions">
          <button className="primary-action" onClick={props.onRefresh}>刷新扫描</button>
          <button className="secondary-action" onClick={() => setView("manage")}>管理股票池</button>
        </div>
      </aside>
      <section className="screener-main">
        <div className="subtabs">
          <button className={view === "lists" ? "active" : ""} onClick={() => setView("lists")}>榜单</button>
          <button className={view === "manage" ? "active" : ""} onClick={() => setView("manage")}>管理</button>
        </div>
        <div className="market-pulse">
          <Metric label="扫描结果" value={`${allRows.length} 条`} />
          <Metric label="风险通过" value={`${passCount} 条`} />
          <Metric label="强趋势" value={`${strongCount} 只`} tone={strongCount > 0 ? "up" : undefined} />
          <Metric label="反弹候选" value={`${reboundCount} 只`} tone={reboundCount > 0 ? "up" : undefined} />
          <Metric label="生成时间" value={generatedAt} />
        </div>
        {view === "lists" ? (
          <div className="lists-grid">
            <ResultList title="趋势追强榜" subtitle="找正在走强的行业龙头和趋势候选" rows={props.trend} onOpen={props.onOpen} />
            <ResultList title="超跌反弹榜" subtitle="找跌幅充分但出现企稳迹象的候选" rows={props.rebound} onOpen={props.onOpen} />
          </div>
        ) : (
          <section className="panel pool-manager">
            <div className="panel-title">
              <div>
                <h2>股票池管理</h2>
                <p>{isUsingDefaultPool ? "当前使用默认核心池。删除任意代码后会转为自定义股票池。" : "当前使用自定义股票池。"}</p>
              </div>
              <button onClick={resetPool}>恢复默认</button>
            </div>
            <div className="pool-add">
              <input value={newSymbol} onChange={(event) => setNewSymbol(event.target.value)} placeholder="输入 6 位代码" inputMode="numeric" />
              <button className="primary-action" onClick={addSymbol}>添加</button>
            </div>
            <div className="pool-list">
              {activeSymbols.map((symbol) => (
                <div className="pool-item" key={symbol}>
                  <strong>{symbol}</strong>
                  <button onClick={() => removeSymbol(symbol)}>删除</button>
                </div>
              ))}
            </div>
            {manageStatus && <p>{manageStatus}</p>}
          </section>
        )}
      </section>
    </main>
  );
}

function ResultList(props: { title: string; subtitle: string; rows: ScreenerResult[]; onOpen: (symbol: string) => void }) {
  const [showFactors, setShowFactors] = useState(false);
  return (
    <section className="panel result-list">
      <div className="panel-title">
        <div>
          <h2>{props.title}</h2>
          <p>{props.subtitle}</p>
        </div>
        <button onClick={() => setShowFactors((current) => !current)}>{showFactors ? "收起因子" : "查看因子"}</button>
      </div>
      <table>
        <thead>
          <tr><th>股票</th><th>评分</th><th>涨跌</th><th>原因</th><th>风险</th><th>动作</th></tr>
        </thead>
        <tbody>
          {props.rows.map((row) => (
            <Fragment key={row.symbol}>
              <tr>
                <td><strong>{row.name}</strong><small>{row.symbol}</small></td>
                <td className="score">{row.score}</td>
                <td className={row.change_pct >= 0 ? "up" : "down"}>{row.change_pct >= 0 ? "+" : ""}{row.change_pct.toFixed(2)}%</td>
                <td>{row.reason}</td>
                <td>{row.risk_status}</td>
                <td><button className="link-button" onClick={() => props.onOpen(row.symbol)}>看走势</button></td>
              </tr>
              {showFactors && (
                <tr className="factor-row">
                  <td colSpan={6}>
                    <div className="factor-grid">
                      {row.factors.map((item) => (
                        <div className="factor-chip" key={`${row.symbol}-${item.name}`}>
                          <span>{item.name}</span>
                          <strong>{item.value}</strong>
                          <small className={item.contribution >= 0 ? "up" : "down"}>{item.contribution >= 0 ? "+" : ""}{item.contribution}</small>
                          <em>{item.status}</em>
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {props.rows.length === 0 && (
            <tr><td colSpan={6}>暂无符合条件的候选。</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function ReviewPage(props: { trades: TradeRecord[]; positions: Position[]; summary: PortfolioSummary }) {
  const buyAmount = props.trades.filter((trade) => trade.side === "buy").reduce((sum, trade) => sum + trade.amount, 0);
  const sellAmount = props.trades.filter((trade) => trade.side === "sell").reduce((sum, trade) => sum + trade.amount, 0);
  const activePositionCount = props.positions.length;

  return (
    <main className="review-grid">
      <section className="panel review-summary">
        <Metric label="交易记录" value={`${props.trades.length} 笔`} />
        <Metric label="当前持仓" value={`${activePositionCount} 只`} />
        <Metric label="累计买入" value={yuan(buyAmount)} />
        <Metric label="累计卖出" value={yuan(sellAmount)} />
        <Metric label="当前浮盈" value={signed(props.summary.floating_pnl)} tone={props.summary.floating_pnl >= 0 ? "up" : "down"} />
      </section>
      <section className="panel trade-table">
        <div className="panel-title">
          <div>
            <h2>交易回看</h2>
            <p>先把买卖记录跑通，后续可以叠加信号触发、策略版本和复盘标签。</p>
          </div>
        </div>
        <table>
          <thead>
            <tr><th>时间</th><th>股票</th><th>方向</th><th>数量</th><th>价格</th><th>金额</th><th>备注</th></tr>
          </thead>
          <tbody>
            {props.trades.map((trade) => (
              <tr key={trade.id}>
                <td>{new Date(trade.created_at).toLocaleString("zh-CN", { hour12: false })}</td>
                <td><strong>{trade.name}</strong><small>{trade.symbol}</small></td>
                <td className={trade.side === "buy" ? "up" : "down"}>{trade.side === "buy" ? "买入" : "卖出"}</td>
                <td>{trade.quantity}</td>
                <td>{trade.price.toFixed(2)}</td>
                <td>{yuan(trade.amount)}</td>
                <td>{trade.note || "--"}</td>
              </tr>
            ))}
            {props.trades.length === 0 && (
              <tr><td colSpan={7}>暂无交易记录。</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}

function SettingsPage(props: {
  marketStatus: MarketStatus | null;
  autoRefreshSeconds: number;
  onAutoRefreshSecondsChange: (seconds: number) => void;
  screenerConfig: ScreenerConfig | null;
  screenerStatus: ScreenerStatus | null;
  onSaveScreenerSymbols: (symbols: string[]) => Promise<void>;
}) {
  const [symbolsText, setSymbolsText] = useState((props.screenerConfig?.symbols ?? []).join(", "));
  const [settingsStatus, setSettingsStatus] = useState("");

  useEffect(() => {
    setSymbolsText((props.screenerConfig?.symbols ?? []).join(", "));
  }, [props.screenerConfig]);

  const saveSymbols = async () => {
    const symbols = symbolsText.split(/[\s,，]+/).map((symbol) => symbol.trim()).filter(Boolean);
    try {
      await props.onSaveScreenerSymbols(symbols);
      setSettingsStatus("股票池已保存并刷新。");
    } catch {
      setSettingsStatus("保存失败，请检查股票代码。");
    }
  };

  return (
    <main className="settings-grid">
      <section className="panel settings-card">
        <h2>行情与刷新</h2>
        <label>
          自动刷新
          <select value={props.autoRefreshSeconds} onChange={(event) => props.onAutoRefreshSecondsChange(Number(event.target.value))}>
            <option value={5}>5 秒</option>
            <option value={10}>10 秒</option>
            <option value={30}>30 秒</option>
            <option value={60}>60 秒</option>
            <option value={0}>暂停</option>
          </select>
        </label>
        <MiniStat label="当前数据源" value={props.marketStatus?.description ?? "等待连接"} />
        <MiniStat label="底层提供方" value={props.marketStatus?.provider ?? "--"} />
      </section>
      <section className="panel settings-card">
        <h2>风险参数</h2>
        <div className="settings-static">
          <MiniStat label="单票建议仓位" value="25%-35%" />
          <MiniStat label="单次账户风险" value="1.2%" />
          <MiniStat label="凯利折扣" value="0.25 分数凯利" />
          <MiniStat label="默认止损" value="现价下方 5.2%" />
        </div>
      </section>
      <section className="panel settings-card">
        <h2>选股雷达</h2>
        <label>
          扫描股票池
          <textarea value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} rows={8} placeholder="300308, 300502, 601138" />
        </label>
        <button className="primary-action" onClick={saveSymbols}>保存并刷新</button>
        <MiniStat label="当前股票池" value={`${props.screenerStatus?.pool_size ?? 0} 只`} />
        <MiniStat label="最近耗时" value={props.screenerStatus?.last_duration_seconds == null ? "--" : `${props.screenerStatus.last_duration_seconds} 秒`} />
        {settingsStatus && <p>{settingsStatus}</p>}
      </section>
    </main>
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
