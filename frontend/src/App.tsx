import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { createChart, ColorType, LineStyle, type IChartApi, type MouseEventParams, type Time, type UTCTimestamp } from "lightweight-charts";

import { api } from "./api";
import type { BacktestRequest, BacktestResult, DecisionCenter, MarketPeriod, MarketSettings, MarketStatus, PortfolioSummary, Position, PredictionResult, PredictionStatus, PriceBar, RiskAdvice, ScreenerConfig, ScreenerResult, ScreenerStatus, TradeRecord, WatchItem } from "./types";

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

function parseNumberInput(value: string) {
  return Number(value.trim().replace(/,/g, "").replace(/，/g, "").replace(/。/g, "."));
}

function pct(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${yuan(value)}`;
}

export default function App() {
  const [tab, setTab] = useState<"home" | "screener" | "prediction" | "review" | "settings">("home");
  const [selectedSymbol, setSelectedSymbol] = useState("300308");
  const [period, setPeriod] = useState("daily");
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary);
  const [positions, setPositions] = useState<Position[]>([]);
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [bars, setBars] = useState<PriceBar[]>([]);
  const [risk, setRisk] = useState<RiskAdvice | null>(null);
  const [balanced, setBalanced] = useState<ScreenerResult[]>([]);
  const [trend, setTrend] = useState<ScreenerResult[]>([]);
  const [rebound, setRebound] = useState<ScreenerResult[]>([]);
  const [screenerConfig, setScreenerConfig] = useState<ScreenerConfig | null>(null);
  const [screenerStatus, setScreenerStatus] = useState<ScreenerStatus | null>(null);
  const [predictionStatus, setPredictionStatus] = useState<PredictionStatus | null>(null);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [marketSettings, setMarketSettings] = useState<MarketSettings | null>(null);
  const [decision, setDecision] = useState<DecisionCenter | null>(null);
  const [periods, setPeriods] = useState<MarketPeriod[]>(defaultPeriods);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(10);
  const [status, setStatus] = useState("加载中");

  const reloadPortfolio = () => {
    return Promise.all([api.summary(), api.positions(), api.watchlist()])
      .then(([summaryData, positionData, watchData]) => {
        setSummary(summaryData);
        setPositions(positionData);
        setWatchlist(watchData);
        return api.trades()
          .then(setTrades)
          .catch(() => undefined);
      });
  };

  const reloadMarket = () => {
    setStatus("刷新行情中");
    return api.dashboard(selectedSymbol, period)
      .then((dashboard) => {
        setBars(dashboard.bars);
        setRisk(dashboard.risk);
        setDecision(dashboard.decision);
        setMarketStatus(dashboard.market_status);
        setStatus(`${dashboard.market_status.description}已更新`);
      })
      .catch(() => setStatus("行情刷新失败"));
  };

  const reloadScreener = () => {
    return Promise.all([api.screener("balanced"), api.screener("trend"), api.screener("rebound"), api.screenerStatus()])
      .then(([balancedData, trendData, reboundData, statusData]) => {
        setBalanced(balancedData);
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

  const renamePosition = (symbol: string, name: string) => {
    setStatus("更新股票标签名中");
    return api.updatePositionName(symbol, name)
      .then(() => reloadPortfolio())
      .then(() => setStatus("股票标签名已更新"))
      .catch((error) => {
        setStatus("股票标签名更新失败");
        throw error;
      });
  };

  const addWatchItem = (symbol: string, tags = "观察") => {
    const normalized = symbol.replace(/\D/g, "");
    if (normalized.length !== 6) return Promise.reject(new Error("请输入 6 位股票代码"));
    setStatus("加入自选观察中");
    return api.addWatchItem({ symbol: normalized, tags })
      .then(() => reloadPortfolio())
      .then(() => setStatus("已加入自选观察"))
      .catch((error) => {
        setStatus("加入自选观察失败");
        throw error;
      });
  };

  const deleteWatchItem = (symbol: string) => {
    setStatus("移除自选观察中");
    return api.deleteWatchItem(symbol)
      .then(setWatchlist)
      .then(() => setStatus("已移除自选观察"))
      .catch((error) => {
        setStatus("移除自选观察失败");
        throw error;
      });
  };

  const reloadPredictionStatus = () => api.predictionStatus().then(setPredictionStatus);

  const saveMarketSettings = (provider: string, tushareToken: string) => {
    setStatus("保存数据源设置中");
    return api.updateMarketSettings(provider, tushareToken)
      .then((settingsData) => {
        setMarketSettings(settingsData);
        return Promise.all([api.marketStatus(), reloadMarket()]);
      })
      .then(([marketStatusData]) => {
        setMarketStatus(marketStatusData);
        setStatus("数据源设置已更新");
      })
      .catch((error) => {
        setStatus("数据源设置保存失败");
        throw error;
      });
  };

  const savePredictionSettings = (enabled: boolean, modelName: string) => {
    setStatus(enabled ? "预测功能已启用，请手动安装并检查环境" : "预测功能已关闭");
    return api.updatePredictionSettings(enabled, modelName)
      .then((statusData) => {
        setPredictionStatus(statusData);
        setStatus(enabled ? "预测设置已保存" : "预测功能已关闭");
        return statusData;
      })
      .catch((error) => {
        setStatus("预测设置保存失败");
        throw error;
      });
  };

  const checkPredictionEnvironment = () => {
    setStatus("检查 Kronos 环境中");
    return api.checkPrediction()
      .then((statusData) => {
        setPredictionStatus(statusData);
        setStatus(statusData.ready ? "Kronos 环境检查通过" : "Kronos 环境检查未通过");
        return statusData;
      })
      .catch((error) => {
        setStatus("Kronos 环境检查失败");
        throw error;
      });
  };

  const runPrediction = (symbol: string, horizon: number) => {
    setStatus("生成 K 线预测中");
    return api.prediction(symbol, horizon)
      .then((result) => {
        setPrediction(result);
        setStatus("预测已更新");
      })
      .catch((error: Error) => setStatus(error.message || "预测生成失败"));
  };

  const runBacktest = (payload: BacktestRequest) => {
    setStatus("正在回测策略");
    return api.runBacktest(payload)
      .then((result) => {
        setBacktest(result);
        setStatus("回测完成");
      })
      .catch((error: Error) => setStatus(error.message));
  };

  useEffect(() => {
    Promise.all([api.summary(), api.positions(), api.watchlist(), api.marketPeriods()])
      .then(([summaryData, positionData, watchData, periodData]) => {
        setSummary(summaryData);
        setPositions(positionData);
        setWatchlist(watchData);
        setPeriods(periodData);
        setStatus("基础数据已加载");
      })
      .catch(() => setStatus("后端未连接，等待数据"));
    api.trades().then(setTrades).catch(() => undefined);
    api.screenerConfig().then(setScreenerConfig).catch(() => undefined);
    api.screenerStatus().then(setScreenerStatus).catch(() => undefined);
    api.predictionStatus().then(setPredictionStatus).catch(() => undefined);
    api.marketStatus().then(setMarketStatus).catch(() => undefined);
    api.marketSettings().then(setMarketSettings).catch(() => undefined);
    reloadScreener().catch(() => undefined);
    const predictionTimer = window.setInterval(() => {
      reloadPredictionStatus().catch(() => undefined);
    }, 5000);
    const screenerTimer = window.setInterval(() => {
      api.screenerStatus()
        .then((statusData) => {
          setScreenerStatus(statusData);
          if (statusData.scan_status === "running" || statusData.scan_status === "ready") {
            reloadScreener().catch(() => undefined);
          }
        })
        .catch(() => undefined);
    }, 4000);
    return () => {
      window.clearInterval(predictionTimer);
      window.clearInterval(screenerTimer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      reloadMarket();
    }, 300);
    return () => window.clearTimeout(timer);
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
          <h1>决策台</h1>
          <p>本地 Web 工具 · 手动持仓 · 规则因子 · 风控建议</p>
        </div>
        <nav className="tabs">
          <button className={tab === "home" ? "active" : ""} onClick={() => setTab("home")}>主页</button>
          <button className={tab === "screener" ? "active" : ""} onClick={() => setTab("screener")}>选股雷达</button>
          <button className={tab === "prediction" ? "active" : ""} onClick={() => setTab("prediction")}>预测</button>
          <button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>策略回看</button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>设置</button>
        </nav>
        <div className="data-status">{status}</div>
      </header>

      {tab === "home" && (
        <HomePage
          summary={summary}
          positions={positions}
          watchlist={watchlist}
          bars={bars}
          risk={risk}
          decision={decision}
          selectedSymbol={selectedSymbol}
          period={period}
          onSelectSymbol={setSelectedSymbol}
          onPeriodChange={setPeriod}
          onPortfolioChange={reloadPortfolio}
          onRenamePosition={renamePosition}
          onAddWatchItem={addWatchItem}
          onDeleteWatchItem={deleteWatchItem}
          onRefreshMarket={reloadMarket}
          marketStatus={marketStatus}
          periods={periods}
          autoRefreshSeconds={autoRefreshSeconds}
          onAutoRefreshSecondsChange={setAutoRefreshSeconds}
          onPredict={() => setTab("prediction")}
        />
      )}
      {tab === "screener" && (
        <ScreenerPage
          trend={trend}
          balanced={balanced}
          rebound={rebound}
          config={screenerConfig}
          status={screenerStatus}
          onRefresh={refreshScreener}
          onSaveSymbols={saveScreenerSymbols}
          onOpen={(symbol) => {
            setSelectedSymbol(symbol);
            setTab("home");
          }}
          onWatch={(symbol) => addWatchItem(symbol, "雷达")}
        />
      )}
      {tab === "review" && <ReviewPage trades={trades} positions={positions} summary={summary} selectedSymbol={selectedSymbol} result={backtest} onRun={runBacktest} />}
      {tab === "prediction" && (
        <PredictionPage
          selectedSymbol={selectedSymbol}
          status={predictionStatus}
          result={prediction}
          onRun={runPrediction}
          onOpenSettings={() => setTab("settings")}
        />
      )}
      {tab === "settings" && (
        <SettingsPage
          marketStatus={marketStatus}
          autoRefreshSeconds={autoRefreshSeconds}
          onAutoRefreshSecondsChange={setAutoRefreshSeconds}
          screenerConfig={screenerConfig}
          screenerStatus={screenerStatus}
          onSaveScreenerSymbols={saveScreenerSymbols}
          marketSettings={marketSettings}
          onSaveMarketSettings={saveMarketSettings}
          predictionStatus={predictionStatus}
          onSavePredictionSettings={savePredictionSettings}
          onCheckPredictionEnvironment={checkPredictionEnvironment}
        />
      )}
    </div>
  );
}

function HomePage(props: {
  summary: PortfolioSummary;
  positions: Position[];
  watchlist: WatchItem[];
  bars: PriceBar[];
  risk: RiskAdvice | null;
  decision: DecisionCenter | null;
  selectedSymbol: string;
  period: string;
  onSelectSymbol: (symbol: string) => void;
  onPeriodChange: (period: string) => void;
  onPortfolioChange: () => Promise<void>;
  onRenamePosition: (symbol: string, name: string) => Promise<void>;
  onAddWatchItem: (symbol: string, tags?: string) => Promise<void>;
  onDeleteWatchItem: (symbol: string) => Promise<void>;
  onRefreshMarket: () => Promise<void>;
  marketStatus: MarketStatus | null;
  periods: MarketPeriod[];
  autoRefreshSeconds: number;
  onAutoRefreshSecondsChange: (seconds: number) => void;
  onPredict: () => void;
}) {
  const selectedPosition = props.positions.find((position) => position.symbol === props.selectedSymbol);
  const symbolInputRef = useRef<HTMLInputElement>(null);
  const tradeLevels = useMemo(() => {
    const buyPrice = validPrice(props.decision?.support_price);
    const sellPrice = validPrice(props.decision?.resistance_price);
    const stopPrice = validPrice(props.risk?.stop_loss_price);
    return [
      buyPrice ? { key: "buy" as const, label: "建议买入", price: buyPrice, color: "#4ea4ff" } : null,
      sellPrice ? { key: "sell" as const, label: "建议卖出", price: sellPrice, color: "#f0b84f" } : null,
      stopPrice ? { key: "stop" as const, label: "止损参考", price: stopPrice, color: "#14a06f" } : null,
    ].filter((item): item is TradeLevel => item !== null);
  }, [props.decision?.resistance_price, props.decision?.support_price, props.risk?.stop_loss_price]);
  const [cashValue, setCashValue] = useState(moneyInput(props.summary.cash));
  const [positionForm, setPositionForm] = useState({
    symbol: "",
    quantity: "",
    average_cost: "",
  });
  const [quoteSymbol, setQuoteSymbol] = useState(props.selectedSymbol);
  const [sellForm, setSellForm] = useState({
    symbol: props.selectedSymbol,
    quantity: "",
    sell_price: "",
  });
  const [fullscreen, setFullscreen] = useState(false);
  const [formStatus, setFormStatus] = useState("");
  const [tradeSubmitting, setTradeSubmitting] = useState<"buy" | "sell" | null>(null);

  useEffect(() => {
    setCashValue(moneyInput(props.summary.cash));
  }, [props.summary.cash]);

  useEffect(() => {
    setSellForm((current) => ({ ...current, symbol: props.selectedSymbol }));
    setQuoteSymbol(props.selectedSymbol);
  }, [props.selectedSymbol]);

  useEffect(() => {
    if (!fullscreen) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [fullscreen]);

  const saveCash = async () => {
    const cash = parseNumberInput(cashValue);
    if (!Number.isFinite(cash) || cash < 0) {
      setFormStatus("现金格式有误，请输入大于等于 0 的数字。");
      return;
    }
    await api.updateCash(Number(cash.toFixed(2)));
    await props.onPortfolioChange();
    setFormStatus("现金已更新");
  };

  const savePosition = async () => {
    if (tradeSubmitting) return;
    try {
      setTradeSubmitting("buy");
      const symbol = positionForm.symbol.replace(/\D/g, "");
      const quantity = parseNumberInput(positionForm.quantity);
      const averageCost = parseNumberInput(positionForm.average_cost);
      if (symbol.length !== 6 || !Number.isInteger(quantity) || quantity <= 0 || !Number.isFinite(averageCost) || averageCost <= 0) {
        setFormStatus("买入信息有误，请输入 6 位代码、正整数数量和大于 0 的买入均价。");
        return;
      }
      const refreshCurrentSymbol = symbol === props.selectedSymbol;
      await api.upsertPosition({
        symbol,
        quantity,
        average_cost: averageCost,
      });
      await props.onPortfolioChange();
      props.onSelectSymbol(symbol);
      if (refreshCurrentSymbol) {
        await props.onRefreshMarket();
      }
      setPositionForm({ symbol: "", quantity: "", average_cost: "" });
      setFormStatus("买入已记录，现金和持仓已更新");
    } catch (error) {
      setFormStatus(error instanceof Error ? error.message : "买入失败，请检查代码、数量和后端连接。");
    } finally {
      setTradeSubmitting(null);
    }
  };

  const sellPosition = async () => {
    if (tradeSubmitting) return;
    try {
      setTradeSubmitting("sell");
      const symbol = sellForm.symbol.replace(/\D/g, "");
      const quantity = parseNumberInput(sellForm.quantity);
      const sellPrice = parseNumberInput(sellForm.sell_price);
      if (symbol.length !== 6 || !Number.isInteger(quantity) || quantity <= 0 || !Number.isFinite(sellPrice) || sellPrice <= 0) {
        setFormStatus("卖出信息有误，请输入 6 位代码、正整数数量和大于 0 的卖出价格。");
        return;
      }
      const refreshCurrentSymbol = symbol === props.selectedSymbol;
      await api.sellPosition({
        symbol,
        quantity,
        sell_price: sellPrice,
      });
      await props.onPortfolioChange();
      if (refreshCurrentSymbol) {
        await props.onRefreshMarket();
      }
      setSellForm({ symbol: props.selectedSymbol, quantity: "", sell_price: "" });
      setFormStatus("卖出已记录");
    } catch (error) {
      setFormStatus(error instanceof Error ? error.message : "卖出失败，请检查持仓数量和后端连接。");
    } finally {
      setTradeSubmitting(null);
    }
  };

  const openQuoteSymbol = () => {
    const symbol = quoteSymbol.replace(/\D/g, "");
    if (symbol.length !== 6) {
      setFormStatus("请输入 6 位股票代码后查看 K 线。");
      return;
    }
    props.onSelectSymbol(symbol);
  };

  const renamePosition = async (position: Position) => {
    const name = window.prompt(`修改 ${position.symbol} 的标签名`, position.name)?.trim();
    if (!name || name === position.name) return;
    try {
      await props.onRenamePosition(position.symbol, name);
      setFormStatus("标签名已更新");
    } catch (error) {
      setFormStatus(error instanceof Error ? error.message : "标签名更新失败。");
    }
  };

  const addQuoteToWatch = async () => {
    const symbol = quoteSymbol.replace(/\D/g, "");
    if (symbol.length !== 6) {
      setFormStatus("请输入 6 位股票代码后加入自选。");
      return;
    }
    try {
      await props.onAddWatchItem(symbol);
      setFormStatus("已加入自选观察");
    } catch (error) {
      setFormStatus(error instanceof Error ? error.message : "加入自选失败。");
    }
  };

  const removeWatch = async (symbol: string) => {
    try {
      await props.onDeleteWatchItem(symbol);
      setFormStatus("已移除自选观察");
    } catch (error) {
      setFormStatus(error instanceof Error ? error.message : "移除自选失败。");
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
            <div className="list-section-label">持仓</div>
            {props.positions.map((position) => (
              <div
                key={position.symbol}
                className={`stock-row ${props.selectedSymbol === position.symbol ? "selected" : ""}`}
              >
                <button className="stock-select" onClick={() => props.onSelectSymbol(position.symbol)}>
                  <strong>{position.name}</strong>
                  <small>{position.symbol} · 持 {position.quantity} 股</small>
                </button>
                <span className={position.floating_pnl >= 0 ? "up" : "down"}>
                  {pct(position.floating_pnl_pct)}
                </span>
                <button className="rename-button" onClick={() => renamePosition(position)}>改名</button>
              </div>
            ))}
            {props.positions.length === 0 && <p className="empty-list">暂无真实持仓。</p>}
            <div className="list-section-label">自选观察</div>
            {props.watchlist.map((item) => (
              <div
                key={item.symbol}
                className={`stock-row ${props.selectedSymbol === item.symbol ? "selected" : ""}`}
              >
                <button className="stock-select" onClick={() => props.onSelectSymbol(item.symbol)}>
                  <strong>{item.name}</strong>
                  <small>{item.symbol} · {item.tags || "观察"} · {item.last_price.toFixed(2)}</small>
                </button>
                <button className="rename-button" onClick={() => removeWatch(item.symbol)}>移除</button>
              </div>
            ))}
            {props.watchlist.length === 0 && <p className="empty-list">暂无自选观察。</p>}
          </div>
          <div className="entry-form">
            <h3>账户录入</h3>
            <label>
              可用现金
              <input value={cashValue} onChange={(event) => setCashValue(event.target.value)} inputMode="decimal" />
            </label>
            <button onClick={saveCash}>保存现金</button>
            <h3>买入记录</h3>
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
            <button onClick={savePosition} disabled={Boolean(tradeSubmitting) || !positionForm.symbol || !positionForm.quantity || !positionForm.average_cost}>
              {tradeSubmitting === "buy" ? "买入处理中" : "记录买入"}
            </button>
            <span className="entry-hint">名称会根据代码自动匹配；买入会扣减现金并重算持仓均价。</span>
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
            <button onClick={sellPosition} disabled={Boolean(tradeSubmitting) || !sellForm.symbol || !sellForm.quantity || !sellForm.sell_price}>
              {tradeSubmitting === "sell" ? "卖出处理中" : "记录卖出"}
            </button>
          </div>
        </aside>

        <section className="panel chart-panel">
          <StockTabs positions={props.positions} selectedSymbol={props.selectedSymbol} onSelectSymbol={props.onSelectSymbol} onRenamePosition={renamePosition} />
          <div className="chart-header">
            <div>
              <h2>{props.risk?.name ?? selectedPosition?.name ?? props.selectedSymbol} <span>{props.selectedSymbol}</span></h2>
              <p>现价 {props.risk?.current_price.toFixed(2) ?? "--"} · 成本 {selectedPosition?.average_cost.toFixed(2) ?? "--"} · 数据源 {props.marketStatus?.description ?? "--"}</p>
            </div>
            <div className="chart-actions">
              <div className="quote-search">
                <input
                  value={quoteSymbol}
                  onChange={(event) => setQuoteSymbol(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      openQuoteSymbol();
                    }
                  }}
                  placeholder="输入代码看K线"
                  inputMode="numeric"
                />
                <button className="refresh-button" onClick={openQuoteSymbol}>查看K线</button>
                <button className="refresh-button" onClick={addQuoteToWatch}>加入自选</button>
              </div>
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
                <button className="refresh-button" onClick={props.onPredict}>去预测</button>
              </div>
            </div>
          </div>
          <KLineChart bars={props.bars} tradeLevels={tradeLevels} />
          <div className="position-strip">
            <MiniStat label="买入成本" value={selectedPosition ? `${selectedPosition.average_cost.toFixed(2)} · ${selectedPosition.quantity} 股` : "无持仓"} />
            <MiniStat label="浮动盈亏" value={selectedPosition ? `${signed(selectedPosition.floating_pnl)} · ${pct(selectedPosition.floating_pnl_pct)}` : "--"} tone={selectedPosition && selectedPosition.floating_pnl >= 0 ? "up" : "down"} />
            <MiniStat label="建议买入" value={tradeLevels.find((item) => item.key === "buy")?.price.toFixed(2) ?? "--"} />
            <MiniStat label="建议卖出" value={tradeLevels.find((item) => item.key === "sell")?.price.toFixed(2) ?? "--"} />
            <MiniStat label="止损参考" value={props.risk ? `${props.risk.stop_loss_price.toFixed(2)} · 风险 ${yuan(props.risk.single_stock_risk)}` : "--"} />
            <MiniStat label="建议仓位" value={props.risk ? `${(props.risk.suggested_min_ratio * 100).toFixed(0)}-${(props.risk.suggested_max_ratio * 100).toFixed(0)}%` : "--"} />
          </div>
        </section>

        <aside className="advisor">
          <DecisionPanel decision={props.decision} />
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
            <StockTabs positions={props.positions} selectedSymbol={props.selectedSymbol} onSelectSymbol={props.onSelectSymbol} onRenamePosition={renamePosition} />
            <button className="close-button" onClick={() => setFullscreen(false)} title="Esc">退出全屏</button>
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
          <KLineChart bars={props.bars} mode="fullscreen" tradeLevels={tradeLevels} />
        </div>
      )}
    </>
  );
}

function StockTabs(props: {
  positions: Position[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onRenamePosition: (position: Position) => void;
}) {
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
        <div
          key={position.symbol}
          className={`stock-tab ${props.selectedSymbol === position.symbol ? "active" : ""}`}
        >
          <button className="stock-tab-main" onClick={() => props.onSelectSymbol(position.symbol)}>
            <span>{position.name}</span>
            <small>{position.symbol}</small>
          </button>
          <button className="stock-tab-rename" onClick={() => props.onRenamePosition(position)}>改名</button>
        </div>
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

function formatChartDate(bar: PriceBar) {
  return bar.timestamp.includes(" ") ? bar.timestamp.slice(0, 16) : bar.trade_date;
}

const priceFormat = { type: "price" as const, precision: 2, minMove: 0.01 };

function validPrice(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
  return value;
}

function movingAverage(values: number[], window: number) {
  return values.map((_, index) => {
    if (index + 1 < window) return null;
    const scoped = values.slice(index + 1 - window, index + 1);
    return scoped.reduce((sum, value) => sum + value, 0) / window;
  });
}

function ema(values: number[], span: number) {
  if (values.length === 0) return [];
  const alpha = 2 / (span + 1);
  const result = [values[0]];
  for (let index = 1; index < values.length; index += 1) {
    result.push(values[index] * alpha + result[index - 1] * (1 - alpha));
  }
  return result;
}

function chartMacd(values: number[]) {
  const ema12 = ema(values, 12);
  const ema26 = ema(values, 26);
  const dif = values.map((_, index) => ema12[index] - ema26[index]);
  const dea = ema(dif, 9);
  return values.map((_, index) => ({
    dif: dif[index],
    dea: dea[index],
    histogram: (dif[index] - dea[index]) * 2,
  }));
}

function chartKdj(bars: Array<{ high: number; low: number; close: number }>) {
  let k = 50;
  let d = 50;
  return bars.map((bar, index) => {
    const scoped = bars.slice(Math.max(0, index - 8), index + 1);
    const low = Math.min(...scoped.map((item) => item.low));
    const high = Math.max(...scoped.map((item) => item.high));
    const rsv = high === low ? 50 : ((bar.close - low) / (high - low)) * 100;
    k = (2 * k + rsv) / 3;
    d = (2 * d + k) / 3;
    return { k, d, j: 3 * k - 2 * d };
  });
}

function chartVolumeRatio(volumes: number[]) {
  return volumes.map((volume, index) => {
    const scoped = volumes.slice(Math.max(0, index - 5), index);
    const average = scoped.length ? scoped.reduce((sum, value) => sum + value, 0) / scoped.length : volume;
    return average ? volume / average : 1;
  });
}

function chartBollinger(values: number[], window = 20, multiplier = 2) {
  return values.map((_, index) => {
    if (index + 1 < window) return null;
    const scoped = values.slice(index + 1 - window, index + 1);
    const middle = scoped.reduce((sum, value) => sum + value, 0) / window;
    const variance = scoped.reduce((sum, value) => sum + (value - middle) ** 2, 0) / window;
    const width = Math.sqrt(variance) * multiplier;
    return { upper: middle + width, middle, lower: middle - width };
  });
}

function chartBbiBoll(values: number[], window = 11, multiplier = 2) {
  const ma3 = movingAverage(values, 3);
  const ma6 = movingAverage(values, 6);
  const ma12 = movingAverage(values, 12);
  const ma24 = movingAverage(values, 24);
  const bbi = values.map((_, index) => {
    if (ma3[index] == null || ma6[index] == null || ma12[index] == null || ma24[index] == null) return null;
    return ((ma3[index] ?? 0) + (ma6[index] ?? 0) + (ma12[index] ?? 0) + (ma24[index] ?? 0)) / 4;
  });
  return bbi.map((middle, index) => {
    if (middle == null || index + 1 < window) return null;
    const scoped = bbi.slice(Math.max(0, index - window + 1), index + 1).filter((value): value is number => value != null);
    if (scoped.length < Math.min(window, index + 1)) return null;
    const average = scoped.reduce((sum, value) => sum + value, 0) / scoped.length;
    const variance = scoped.reduce((sum, value) => sum + (value - average) ** 2, 0) / scoped.length;
    const width = Math.sqrt(variance) * multiplier;
    return { upper: middle + width, middle, lower: middle - width };
  });
}

function chartRsi(values: number[], window = 14) {
  return values.map((value, index) => {
    if (index === 0) return 50;
    const start = Math.max(1, index - window + 1);
    let gain = 0;
    let loss = 0;
    for (let cursor = start; cursor <= index; cursor += 1) {
      const change = values[cursor] - values[cursor - 1];
      if (change >= 0) gain += change;
      else loss -= change;
    }
    const length = index - start + 1;
    const avgGain = gain / length;
    const avgLoss = loss / length;
    return avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  });
}

function chartWr(bars: Array<{ high: number; low: number; close: number }>, window = 14) {
  return bars.map((bar, index) => {
    const scoped = bars.slice(Math.max(0, index - window + 1), index + 1);
    const high = Math.max(...scoped.map((item) => item.high));
    const low = Math.min(...scoped.map((item) => item.low));
    return high === low ? -50 : ((high - bar.close) / (high - low)) * -100;
  });
}

function chartPsy(values: number[], window = 12) {
  return values.map((_, index) => {
    if (index === 0) return 50;
    const start = Math.max(1, index - window + 1);
    let upDays = 0;
    for (let cursor = start; cursor <= index; cursor += 1) {
      if (values[cursor] > values[cursor - 1]) upDays += 1;
    }
    return (upDays / (index - start + 1)) * 100;
  });
}

function chartDmi(bars: Array<{ high: number; low: number; close: number }>, window = 14) {
  const tr = [0];
  const plusDm = [0];
  const minusDm = [0];
  for (let index = 1; index < bars.length; index += 1) {
    const current = bars[index];
    const previous = bars[index - 1];
    const upMove = current.high - previous.high;
    const downMove = previous.low - current.low;
    plusDm.push(upMove > downMove && upMove > 0 ? upMove : 0);
    minusDm.push(downMove > upMove && downMove > 0 ? downMove : 0);
    tr.push(Math.max(current.high - current.low, Math.abs(current.high - previous.close), Math.abs(current.low - previous.close)));
  }
  const dx: number[] = [];
  return bars.map((_, index) => {
    const start = Math.max(0, index - window + 1);
    const trSum = tr.slice(start, index + 1).reduce((sum, value) => sum + value, 0) || 1;
    const pdi = plusDm.slice(start, index + 1).reduce((sum, value) => sum + value, 0) / trSum * 100;
    const mdi = minusDm.slice(start, index + 1).reduce((sum, value) => sum + value, 0) / trSum * 100;
    const currentDx = pdi + mdi ? Math.abs(pdi - mdi) / (pdi + mdi) * 100 : 0;
    dx.push(currentDx);
    const adxWindow = dx.slice(Math.max(0, index - window + 1), index + 1);
    const adx = adxWindow.reduce((sum, value) => sum + value, 0) / adxWindow.length;
    return { pdi, mdi, adx };
  });
}

type MainChartType = "standard" | "boll" | "bbiboll";
type SubChartType = "volume" | "macd" | "kdj" | "ratio" | "rsi" | "wr" | "psy" | "dmi";
type TradeLevel = {
  key: "buy" | "sell" | "stop";
  label: string;
  price: number;
  color: string;
};
type ChartSeries =
  | ReturnType<IChartApi["addLineSeries"]>
  | ReturnType<IChartApi["addCandlestickSeries"]>
  | ReturnType<IChartApi["addHistogramSeries"]>;

function KLineChart({ bars, mode = "normal", tradeLevels = [] }: { bars: PriceBar[]; mode?: "normal" | "fullscreen"; tradeLevels?: TradeLevel[] }) {
  const [mainChart, setMainChart] = useState<MainChartType>("standard");
  const [subchart, setSubchart] = useState<SubChartType>("macd");
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const subContainerRef = useRef<HTMLDivElement | null>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const subChartRef = useRef<IChartApi | null>(null);
  const mainSeriesRef = useRef<ChartSeries[]>([]);
  const subSeriesRef = useRef<ChartSeries[]>([]);
  const isMinuteChart = bars.some((bar) => bar.timestamp.includes(" "));
  const chartData = useMemo(
    () => bars.map((bar) => ({
      time: chinaMarketTime(bar),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
      amount: bar.amount,
      raw: bar,
    })),
    [bars],
  );
  const lineData = useMemo(
    () => chartData.map((item) => ({ time: item.time, value: item.close })),
    [chartData],
  );
  const vwapData = useMemo(() => {
    let amount = 0;
    let volume = 0;
    return chartData.map((item) => {
      amount += item.amount;
      volume += item.volume;
      return { time: item.time, value: volume ? amount / volume : item.close };
    });
  }, [chartData]);
  const volumeData = useMemo(
    () => chartData.map((item) => ({
      time: item.time,
      value: item.volume,
      color: item.close >= item.open ? "rgba(218, 63, 55, 0.58)" : "rgba(22, 137, 98, 0.58)",
    })),
    [chartData],
  );
  const maData = useMemo(() => {
    const closes = chartData.map((item) => item.close);
    return [5, 10, 20, 60].map((window) => ({
      window,
      data: movingAverage(closes, window)
        .map((value, index) => value == null ? null : { time: chartData[index].time, value })
        .filter((item): item is { time: UTCTimestamp | string; value: number } => item !== null),
    }));
  }, [chartData]);
  const bollData = useMemo(() => {
    const points = chartBollinger(chartData.map((item) => item.close));
    const toSeries = (key: "upper" | "middle" | "lower") => points
      .map((point, index) => point == null ? null : { time: chartData[index].time, value: point[key] })
      .filter((item): item is { time: UTCTimestamp | string; value: number } => item !== null);
    const latest = [...points].reverse().find((point): point is { upper: number; middle: number; lower: number } => point !== null) ?? null;
    return {
      upper: toSeries("upper"),
      middle: toSeries("middle"),
      lower: toSeries("lower"),
      latest,
    };
  }, [chartData]);
  const bbiBollData = useMemo(() => {
    const points = chartBbiBoll(chartData.map((item) => item.close));
    const toSeries = (key: "upper" | "middle" | "lower") => points
      .map((point, index) => point == null ? null : { time: chartData[index].time, value: point[key] })
      .filter((item): item is { time: UTCTimestamp | string; value: number } => item !== null);
    const latest = [...points].reverse().find((point): point is { upper: number; middle: number; lower: number } => point !== null) ?? null;
    return {
      upper: toSeries("upper"),
      middle: toSeries("middle"),
      lower: toSeries("lower"),
      latest,
    };
  }, [chartData]);
  const macdData = useMemo(() => {
    const points = chartMacd(chartData.map((item) => item.close));
    return {
      dif: points.map((point, index) => ({ time: chartData[index].time, value: point.dif })),
      dea: points.map((point, index) => ({ time: chartData[index].time, value: point.dea })),
      histogram: points.map((point, index) => ({
        time: chartData[index].time,
        value: point.histogram,
        color: point.histogram >= 0 ? "rgba(218, 63, 55, 0.7)" : "rgba(22, 137, 98, 0.7)",
      })),
    };
  }, [chartData]);
  const kdjData = useMemo(() => {
    const points = chartKdj(chartData);
    return {
      k: points.map((point, index) => ({ time: chartData[index].time, value: point.k })),
      d: points.map((point, index) => ({ time: chartData[index].time, value: point.d })),
      j: points.map((point, index) => ({ time: chartData[index].time, value: point.j })),
      latest: points[points.length - 1],
    };
  }, [chartData]);
  const volumeRatioData = useMemo(() => {
    const ratios = chartVolumeRatio(chartData.map((item) => item.volume));
    return {
      bars: ratios.map((ratio, index) => ({
        time: chartData[index].time,
        value: ratio,
        color: ratio >= 1 ? "rgba(218, 63, 55, 0.7)" : "rgba(22, 137, 98, 0.7)",
      })),
      line: ratios.map((ratio, index) => ({ time: chartData[index].time, value: ratio })),
      latest: ratios[ratios.length - 1],
    };
  }, [chartData]);
  const rsiData = useMemo(() => {
    const points = chartRsi(chartData.map((item) => item.close));
    return {
      line: points.map((value, index) => ({ time: chartData[index].time, value })),
      latest: points[points.length - 1],
    };
  }, [chartData]);
  const wrData = useMemo(() => {
    const points = chartWr(chartData);
    return {
      line: points.map((value, index) => ({ time: chartData[index].time, value })),
      latest: points[points.length - 1],
    };
  }, [chartData]);
  const psyData = useMemo(() => {
    const points = chartPsy(chartData.map((item) => item.close));
    return {
      line: points.map((value, index) => ({ time: chartData[index].time, value })),
      latest: points[points.length - 1],
    };
  }, [chartData]);
  const dmiData = useMemo(() => {
    const points = chartDmi(chartData);
    return {
      pdi: points.map((point, index) => ({ time: chartData[index].time, value: point.pdi })),
      mdi: points.map((point, index) => ({ time: chartData[index].time, value: point.mdi })),
      adx: points.map((point, index) => ({ time: chartData[index].time, value: point.adx })),
      latest: points[points.length - 1],
    };
  }, [chartData]);
  const latestMacd = macdData.histogram.length
    ? {
      dif: macdData.dif[macdData.dif.length - 1].value,
      dea: macdData.dea[macdData.dea.length - 1].value,
      histogram: macdData.histogram[macdData.histogram.length - 1].value,
    }
    : null;
  const latestVolume = volumeData[volumeData.length - 1]?.value ?? 0;
  const mainChartReadout = mainChart === "boll" && bollData.latest
    ? `BOLL UP ${bollData.latest.upper.toFixed(2)}  MID ${bollData.latest.middle.toFixed(2)}  DN ${bollData.latest.lower.toFixed(2)}`
    : mainChart === "bbiboll" && bbiBollData.latest
      ? `BBI UP ${bbiBollData.latest.upper.toFixed(2)}  BBI ${bbiBollData.latest.middle.toFixed(2)}  DN ${bbiBollData.latest.lower.toFixed(2)}`
      : isMinuteChart ? "分时 + VWAP" : "K线 + MA5/10/20/60";
  const mainChartTabs: Array<{ key: MainChartType; label: string }> = [
    { key: "standard", label: "常规" },
    { key: "boll", label: "布林(BOLL)" },
    { key: "bbiboll", label: "BBIBOLL" },
  ];
  const subchartReadout = {
    volume: `成交量 ${latestVolume.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`,
    macd: latestMacd
      ? `DIF ${latestMacd.dif.toFixed(3)}  DEA ${latestMacd.dea.toFixed(3)}  MACD ${latestMacd.histogram.toFixed(3)}`
      : "MACD 暂无",
    kdj: kdjData.latest
      ? `K ${kdjData.latest.k.toFixed(1)}  D ${kdjData.latest.d.toFixed(1)}  J ${kdjData.latest.j.toFixed(1)}`
      : "KDJ 暂无",
    ratio: `量比 ${(volumeRatioData.latest ?? 1).toFixed(2)}`,
    rsi: `RSI ${(rsiData.latest ?? 50).toFixed(1)}`,
    wr: `WR ${(wrData.latest ?? -50).toFixed(1)}`,
    psy: `PSY ${(psyData.latest ?? 50).toFixed(1)}`,
    dmi: dmiData.latest ? `+DI ${dmiData.latest.pdi.toFixed(1)}  -DI ${dmiData.latest.mdi.toFixed(1)}  ADX ${dmiData.latest.adx.toFixed(1)}` : "DMI 暂无",
  } satisfies Record<SubChartType, string>;
  const subchartTabs: Array<{ key: SubChartType; label: string }> = [
    { key: "volume", label: "成交量" },
    { key: "macd", label: "MACD" },
    { key: "kdj", label: "KDJ" },
    { key: "ratio", label: "量比" },
    { key: "rsi", label: "RSI" },
    { key: "wr", label: "WR" },
    { key: "psy", label: "PSY" },
    { key: "dmi", label: "DMI" },
  ];
  const visibleTradeLevels = useMemo(
    () => tradeLevels.filter((item) => Number.isFinite(item.price) && item.price > 0),
    [tradeLevels],
  );

  useEffect(() => {
    const container = mainContainerRef.current;
    if (!container) return undefined;
    const priceScaleWidth = container.clientWidth < 560 ? 52 : 64;
    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#0f1724" }, textColor: "#9aa8bd" },
      grid: { vertLines: { color: "#1c2940" }, horzLines: { color: "#1c2940" } },
      rightPriceScale: { borderColor: "#253145", minimumWidth: priceScaleWidth, scaleMargins: { top: 0.06, bottom: 0.08 } },
      timeScale: { borderColor: "#253145", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1, vertLine: { color: "#50647f", style: LineStyle.Dashed }, horzLine: { color: "#50647f", style: LineStyle.Dashed } },
      width: container.clientWidth,
      height: container.clientHeight,
    });
    mainChartRef.current = chart;
    const resizeObserver = new ResizeObserver(() => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      chart.applyOptions({
        width,
        height,
        rightPriceScale: { minimumWidth: width < 560 ? 52 : 64 },
      });
    });
    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
      mainSeriesRef.current = [];
      mainChartRef.current = null;
      chart.remove();
    };
  }, [mode]);

  useEffect(() => {
    const container = subContainerRef.current;
    if (!container) return undefined;
    const subPriceScaleWidth = container.clientWidth < 560 ? 52 : 64;
    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#101a2a" }, textColor: "#9aa8bd" },
      grid: { vertLines: { color: "#1c2940" }, horzLines: { color: "#1c2940" } },
      rightPriceScale: { borderColor: "#253145", minimumWidth: subPriceScaleWidth, scaleMargins: { top: 0.14, bottom: 0.12 } },
      timeScale: { borderColor: "#253145", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1, vertLine: { color: "#50647f", style: LineStyle.Dashed }, horzLine: { color: "#50647f", style: LineStyle.Dashed } },
      width: container.clientWidth,
      height: container.clientHeight,
    });
    subChartRef.current = chart;
    const resizeObserver = new ResizeObserver(() => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      chart.applyOptions({
        width,
        height,
        rightPriceScale: { minimumWidth: width < 560 ? 52 : 64 },
      });
    });
    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
      subSeriesRef.current = [];
      subChartRef.current = null;
      chart.remove();
    };
  }, [mode]);

  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart) return undefined;
    mainSeriesRef.current.forEach((series) => chart.removeSeries(series));
    mainSeriesRef.current = [];
    if (chartData.length === 0) return undefined;
    let primaryPriceSeries: ChartSeries | null = null;
    if (isMinuteChart) {
      const lineSeries = chart.addLineSeries({ color: "#69a8ff", lineWidth: 2, priceScaleId: "right", priceFormat });
      lineSeries.setData(lineData);
      mainSeriesRef.current.push(lineSeries);
      primaryPriceSeries = lineSeries;
      if (mainChart === "standard") {
        const vwapSeries = chart.addLineSeries({ color: "#f0c04f", lineWidth: 1, priceScaleId: "right", priceFormat });
        vwapSeries.setData(vwapData);
        mainSeriesRef.current.push(vwapSeries);
      }
    }
    if (!isMinuteChart) {
      const candleSeries = chart.addCandlestickSeries({
        upColor: "#d94b42",
        downColor: "#14a06f",
        borderUpColor: "#d94b42",
        borderDownColor: "#14a06f",
        wickUpColor: "#d94b42",
        wickDownColor: "#14a06f",
        priceScaleId: "right",
        priceFormat,
      });
      candleSeries.setData(chartData);
      mainSeriesRef.current.push(candleSeries);
      primaryPriceSeries = candleSeries;
      if (mainChart === "standard") {
        const maColors: Record<number, string> = { 5: "#f4d35e", 10: "#8ecae6", 20: "#c084fc", 60: "#f59e0b" };
        maData.forEach((ma) => {
          const series = chart.addLineSeries({ color: maColors[ma.window], lineWidth: 1, priceFormat, priceLineVisible: false, lastValueVisible: false });
          series.setData(ma.data);
          mainSeriesRef.current.push(series);
        });
      }
    }
    if (mainChart === "boll" || mainChart === "bbiboll") {
      const activeBand = mainChart === "boll" ? bollData : bbiBollData;
      const upperSeries = chart.addLineSeries({ color: "#f0b84f", lineWidth: 1, lineStyle: LineStyle.Dashed, priceFormat, priceLineVisible: false, lastValueVisible: false });
      const middleSeries = chart.addLineSeries({ color: "#8ecae6", lineWidth: 2, priceFormat, priceLineVisible: false, lastValueVisible: false });
      const lowerSeries = chart.addLineSeries({ color: "#f0b84f", lineWidth: 1, lineStyle: LineStyle.Dashed, priceFormat, priceLineVisible: false, lastValueVisible: false });
      upperSeries.setData(activeBand.upper);
      middleSeries.setData(activeBand.middle);
      lowerSeries.setData(activeBand.lower);
      mainSeriesRef.current.push(upperSeries, middleSeries, lowerSeries);
    }
    visibleTradeLevels.forEach((item) => {
      primaryPriceSeries?.createPriceLine({
        price: item.price,
        color: item.color,
        lineWidth: 1,
        lineStyle: item.key === "stop" ? LineStyle.Dotted : LineStyle.Dashed,
        axisLabelVisible: true,
        title: item.label,
      });
    });
    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      const tooltip = tooltipRef.current;
      if (!tooltip || !param.time) return;
      const point = chartData.find((item) => item.time === param.time);
      if (!point) return;
      const changePct = point.open ? (point.close / point.open - 1) * 100 : 0;
      tooltip.innerHTML = [
        `<strong>${formatChartDate(point.raw)}</strong>`,
        `<span>开 ${point.open.toFixed(2)}</span>`,
        `<span>高 ${point.high.toFixed(2)}</span>`,
        `<span>低 ${point.low.toFixed(2)}</span>`,
        `<span>收 ${point.close.toFixed(2)}</span>`,
        `<span class="${changePct >= 0 ? "up" : "down"}">${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%</span>`,
        `<span>量 ${point.volume.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</span>`,
      ].join("");
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);
    chart.timeScale().fitContent();
    return () => chart.unsubscribeCrosshairMove(handleCrosshairMove);
  }, [bbiBollData, bollData, chartData, isMinuteChart, lineData, maData, mainChart, visibleTradeLevels, vwapData]);

  useEffect(() => {
    const chart = subChartRef.current;
    if (!chart) return;
    subSeriesRef.current.forEach((series) => chart.removeSeries(series));
    subSeriesRef.current = [];
    if (chartData.length === 0) return;
    if (subchart === "volume") {
      const series = chart.addHistogramSeries({ priceFormat: { type: "volume" }, lastValueVisible: true, priceLineVisible: false });
      series.setData(volumeData);
      subSeriesRef.current.push(series);
    }
    if (subchart === "macd") {
      const histogram = chart.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false });
      const difSeries = chart.addLineSeries({ color: "#4ea4ff", lineWidth: 2, priceLineVisible: false });
      const deaSeries = chart.addLineSeries({ color: "#f0b84f", lineWidth: 2, priceLineVisible: false });
      histogram.setData(macdData.histogram);
      difSeries.setData(macdData.dif);
      deaSeries.setData(macdData.dea);
      subSeriesRef.current.push(histogram, difSeries, deaSeries);
    }
    if (subchart === "kdj") {
      const kSeries = chart.addLineSeries({ color: "#4ea4ff", lineWidth: 2, priceLineVisible: false });
      const dSeries = chart.addLineSeries({ color: "#f0b84f", lineWidth: 2, priceLineVisible: false });
      const jSeries = chart.addLineSeries({ color: "#d879ff", lineWidth: 2, priceLineVisible: false });
      kSeries.setData(kdjData.k);
      dSeries.setData(kdjData.d);
      jSeries.setData(kdjData.j);
      subSeriesRef.current.push(kSeries, dSeries, jSeries);
    }
    if (subchart === "ratio") {
      const histogram = chart.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false });
      const line = chart.addLineSeries({ color: "#f0c04f", lineWidth: 2, priceLineVisible: false });
      histogram.setData(volumeRatioData.bars);
      line.setData(volumeRatioData.line);
      subSeriesRef.current.push(histogram, line);
    }
    if (subchart === "rsi") {
      const line = chart.addLineSeries({ color: "#4ea4ff", lineWidth: 2, priceLineVisible: false });
      line.setData(rsiData.line);
      subSeriesRef.current.push(line);
    }
    if (subchart === "wr") {
      const line = chart.addLineSeries({ color: "#d879ff", lineWidth: 2, priceLineVisible: false });
      line.setData(wrData.line);
      subSeriesRef.current.push(line);
    }
    if (subchart === "psy") {
      const line = chart.addLineSeries({ color: "#f0c04f", lineWidth: 2, priceLineVisible: false });
      line.setData(psyData.line);
      subSeriesRef.current.push(line);
    }
    if (subchart === "dmi") {
      const pdi = chart.addLineSeries({ color: "#d94b42", lineWidth: 2, priceLineVisible: false });
      const mdi = chart.addLineSeries({ color: "#14a06f", lineWidth: 2, priceLineVisible: false });
      const adx = chart.addLineSeries({ color: "#f0c04f", lineWidth: 2, priceLineVisible: false });
      pdi.setData(dmiData.pdi);
      mdi.setData(dmiData.mdi);
      adx.setData(dmiData.adx);
      subSeriesRef.current.push(pdi, mdi, adx);
    }
    chart.timeScale().fitContent();
  }, [chartData.length, dmiData, kdjData, macdData, psyData, rsiData, subchart, volumeData, volumeRatioData, wrData]);

  return (
    <div className="pro-chart" data-mode={mode}>
      <div className="chart-tooltip" ref={tooltipRef}>
        {chartData[chartData.length - 1] ? (
          <>
            <strong>{formatChartDate(chartData[chartData.length - 1].raw)}</strong>
            <span>开 {chartData[chartData.length - 1].open.toFixed(2)}</span>
            <span>高 {chartData[chartData.length - 1].high.toFixed(2)}</span>
            <span>低 {chartData[chartData.length - 1].low.toFixed(2)}</span>
            <span>收 {chartData[chartData.length - 1].close.toFixed(2)}</span>
            <span>量 {chartData[chartData.length - 1].volume.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</span>
          </>
        ) : <span>暂无行情</span>}
      </div>
      <div className="mainchart-tabs" role="tablist" aria-label="主图视图">
        {mainChartTabs.map((item) => (
          <button
            key={item.key}
            className={mainChart === item.key ? "active" : ""}
            type="button"
            onClick={() => setMainChart(item.key)}
          >
            {item.label}
          </button>
        ))}
        <span className="mainchart-readout">{mainChartReadout}</span>
      </div>
      <div
        className="chart-main-canvas"
        data-mode={mode}
        ref={mainContainerRef}
      />
      <div className="subchart-tabs" role="tablist" aria-label="副图指标">
        {subchartTabs.map((item) => (
          <button
            key={item.key}
            className={subchart === item.key ? "active" : ""}
            type="button"
            onClick={() => setSubchart(item.key)}
          >
            {item.label}
          </button>
        ))}
        <span className="subchart-readout">{subchartReadout[subchart]}</span>
      </div>
      <div
        className="chart-sub-canvas"
        data-mode={mode}
        ref={subContainerRef}
      />
      <div className="chart-legend">
        {mainChart === "boll" || mainChart === "bbiboll" ? (
          <>
            <span><i style={{ background: "#69a8ff" }} />价格</span>
            <span><i style={{ background: "#f0b84f" }} />{mainChart === "boll" ? "BOLL" : "BBIBOLL"}上/下轨</span>
            <span><i style={{ background: "#8ecae6" }} />{mainChart === "boll" ? "BOLL" : "BBI"}中轨</span>
          </>
        ) : isMinuteChart ? (
          <>
            <span><i style={{ background: "#69a8ff" }} />分时</span>
            <span><i style={{ background: "#f0c04f" }} />VWAP</span>
          </>
        ) : (
          <>
            <span><i style={{ background: "#f4d35e" }} />MA5</span>
            <span><i style={{ background: "#8ecae6" }} />MA10</span>
            <span><i style={{ background: "#c084fc" }} />MA20</span>
            <span><i style={{ background: "#f59e0b" }} />MA60</span>
          </>
        )}
        {subchart === "volume" && <span><i style={{ background: "#d94b42" }} />成交量</span>}
        {subchart === "macd" && (
          <>
            <span><i style={{ background: "#4ea4ff" }} />DIF</span>
            <span><i style={{ background: "#f0b84f" }} />DEA</span>
            <span><i style={{ background: "#d94b42" }} />MACD</span>
          </>
        )}
        {subchart === "kdj" && (
          <>
            <span><i style={{ background: "#4ea4ff" }} />K</span>
            <span><i style={{ background: "#f0b84f" }} />D</span>
            <span><i style={{ background: "#d879ff" }} />J</span>
          </>
        )}
        {subchart === "ratio" && <span><i style={{ background: "#f0c04f" }} />量比</span>}
        {subchart === "rsi" && <span><i style={{ background: "#4ea4ff" }} />RSI</span>}
        {subchart === "wr" && <span><i style={{ background: "#d879ff" }} />WR</span>}
        {subchart === "psy" && <span><i style={{ background: "#f0c04f" }} />PSY</span>}
        {subchart === "dmi" && (
          <>
            <span><i style={{ background: "#d94b42" }} />+DI</span>
            <span><i style={{ background: "#14a06f" }} />-DI</span>
            <span><i style={{ background: "#f0c04f" }} />ADX</span>
          </>
        )}
        {visibleTradeLevels.map((item) => (
          <span key={item.key} className="trade-level-legend">
            <i style={{ background: item.color }} />{item.label} {item.price.toFixed(2)}
          </span>
        ))}
      </div>
    </div>
  );
}

function DecisionPanel({ decision }: { decision: DecisionCenter | null }) {
  if (!decision) {
    return (
      <section className="panel decision-card">
        <h2>决策中心</h2>
        <p>等待指标计算。</p>
      </section>
    );
  }
  const warnings = decision.advice.warnings.length > 0 ? decision.advice.warnings : ["暂无明显风险警示。"];
  return (
    <section className="panel decision-card">
      <div className="decision-head">
        <div>
          <h2>决策中心</h2>
          <p>{decision.name} · {decision.symbol}</p>
        </div>
        <strong className={decision.advice.confidence >= 60 ? "up" : "down"}>{decision.advice.action}</strong>
      </div>
      <div className="decision-score">
        <span>置信度</span>
        <strong>{decision.advice.confidence}</strong>
        <div><i style={{ width: `${decision.advice.confidence}%` }} /></div>
      </div>
      <div className="decision-mini-grid">
        <MiniStat label="趋势" value={decision.trend_status} />
        <MiniStat label="量能" value={`${decision.volume_status} · ${decision.volume_ratio.toFixed(2)}x`} />
        <MiniStat label="MACD" value={decision.macd_status} />
        <MiniStat label="KDJ" value={decision.kdj_status} />
        <MiniStat label="DMI" value={decision.dmi_status} />
        <MiniStat label="心理线" value={decision.psy_status} />
        <MiniStat label="RSI/WR" value={`${decision.rsi_status} · ${decision.wr_status}`} />
        <MiniStat label="分时博弈" value={`${decision.intraday_game.status} · 多 ${decision.intraday_game.buy_power_pct.toFixed(1)}%`} />
        <MiniStat label="支撑/压力" value={`${decision.support_price.toFixed(2)} / ${decision.resistance_price.toFixed(2)}`} />
      </div>
      <div className="chip-list">
        <span>筹码密集区 · {decision.chip_analysis.status}</span>
        <p>{decision.chip_analysis.description}</p>
        {decision.chips.map((chip) => (
          <div className="chip-bar" key={chip.price}>
            <strong>{chip.price.toFixed(2)}</strong>
            <div><i style={{ width: `${Math.max(6, chip.volume_ratio * 100)}%` }} /></div>
          </div>
        ))}
      </div>
      <div className="indicator-matrix">
        {decision.indicator_matrix.map((item) => (
          <div className="indicator-chip" key={`${item.group}-${item.name}`}>
            <span>{item.group}</span>
            <strong>{item.name}</strong>
            <small>{item.status}</small>
            <em className={item.contribution >= 0 ? "up" : "down"}>{item.contribution >= 0 ? "+" : ""}{item.contribution}</em>
          </div>
        ))}
      </div>
      <ul className="signals compact">
        {decision.advice.reasons.slice(0, 6).map((reason) => <li key={reason}>{reason}</li>)}
        {warnings.map((warning) => <li key={warning}>{warning}</li>)}
      </ul>
    </section>
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
  balanced: ScreenerResult[];
  trend: ScreenerResult[];
  rebound: ScreenerResult[];
  config: ScreenerConfig | null;
  status: ScreenerStatus | null;
  onRefresh: () => Promise<void>;
  onSaveSymbols: (symbols: string[]) => Promise<void>;
  onOpen: (symbol: string) => void;
  onWatch: (symbol: string) => Promise<void>;
}) {
  const [view, setView] = useState<"lists" | "manage">("lists");
  const [activeList, setActiveList] = useState<"balanced" | "trend" | "rebound">("balanced");
  const [newSymbol, setNewSymbol] = useState("");
  const [manageStatus, setManageStatus] = useState("");
  const allRows = [...props.balanced, ...props.trend, ...props.rebound];
  const activeRows = activeList === "balanced" ? props.balanced : activeList === "trend" ? props.trend : props.rebound;
  const activeTitle = activeList === "balanced" ? "综合优选榜" : activeList === "trend" ? "趋势追强榜" : "超跌反弹榜";
  const activeSubtitle = activeList === "balanced"
    ? "综合趋势、位置、量能、波动和风险后的默认候选"
    : activeList === "trend"
      ? "找正在走强的行业龙头和趋势候选"
      : "找跌幅充分但出现企稳迹象的候选";
  const generatedAt = allRows[0]?.generated_at ? new Date(allRows[0].generated_at).toLocaleString("zh-CN", { hour12: false }) : "--";
  const passCount = allRows.filter((row) => row.risk_status === "通过").length;
  const strongCount = props.trend.filter((row) => row.score >= 75).length;
  const reboundCount = props.rebound.filter((row) => row.score >= 70).length;
  const cacheAge = props.status?.cache_age_seconds == null ? "--" : `${props.status.cache_age_seconds} 秒`;
  const progress = props.status?.total_count ? Math.round((props.status.processed_count / props.status.total_count) * 100) : 0;
  const isScanning = props.status?.scan_status === "running" || props.status?.scan_status === "queued";
  const coverageRate = props.status?.total_count ? Math.round(((props.status.success_count ?? 0) / props.status.total_count) * 100) : 0;
  const highBalanced = props.balanced.filter((row) => row.score >= 75).length;
  const watchGrade = highBalanced >= 8 ? "机会密集" : highBalanced >= 3 ? "局部机会" : isScanning ? "扫描中" : "机会稀疏";
  const radarSignals = [
    { label: "覆盖率", value: props.status?.total_count ? `${coverageRate}%` : "--", detail: `${props.status?.success_count ?? 0}/${props.status?.total_count ?? 0}` },
    { label: "综合高分", value: `${highBalanced} 只`, detail: "评分 >= 75" },
    { label: "市场温度", value: props.status?.market_environment ?? "未知", detail: `${(props.status?.market_factor ?? 1).toFixed(2)}x` },
    { label: "扫描用时", value: props.status?.last_duration_seconds ? `${props.status.last_duration_seconds.toFixed(1)}s` : "--", detail: props.status?.last_scan_at ? new Date(props.status.last_scan_at).toLocaleTimeString("zh-CN", { hour12: false }) : "未完成" },
  ];
  const configuredSymbols = props.config?.symbols ?? [];
  const activeSymbols = configuredSymbols.length > 0 ? configuredSymbols : [];
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
    await saveSymbols([...configuredSymbols, symbol], "观察池已新增。全市场扫描范围不受影响。");
    setNewSymbol("");
  };

  const removeSymbol = async (symbol: string) => {
    await saveSymbols(configuredSymbols.filter((item) => item !== symbol), "观察池已删除。");
  };

  const resetPool = async () => {
    await props.onSaveSymbols([]);
    setManageStatus("已清空观察池。选股雷达继续使用全市场扫描。");
  };

  return (
    <main className="screener-grid">
      <aside className="panel filters">
        <h2>筛选条件</h2>
        <Filter label="市场" value="沪深 A 股全市场" />
        <Filter label="周期" value="短线 / 波段" />
        <Filter label="策略" value="趋势追强 + 超跌修复" />
        <Filter label="流动性" value="5日均额 > 3000 万" />
        <Filter label="风险过滤" value="开启" />
        <Filter label="扫描范围" value={props.status?.scope === "full_market" ? "全市场" : props.status?.scope === "env_limited" ? "环境变量限制" : "全市场"} />
        <Filter label="扫描规模" value={`${props.status?.pool_size ?? 0} 只`} />
        <Filter label="市场环境" value={`${props.status?.market_environment ?? "未知"} · ${(props.status?.market_factor ?? 1).toFixed(2)}x`} />
        <Filter label="缓存年龄" value={cacheAge} />
        <div className="filter-note">选股雷达默认自动获取 A 股全市场股票池并后台扫描；观察池只用于记录重点关注，不会缩小雷达扫描范围。</div>
        <div className="scan-progress">
          <span>{props.status?.scan_status === "queued" ? "等待扫描启动" : isScanning ? `扫描中 ${progress}%` : props.status?.scan_status === "ready" ? "扫描完成" : "等待扫描"}</span>
          <strong>{props.status?.processed_count ?? 0}/{props.status?.total_count ?? 0}</strong>
          <i><b style={{ width: `${progress}%` }} /></i>
          {props.status?.last_error && <em>{props.status.last_error}</em>}
        </div>
        <div className="side-actions">
          <button className="primary-action" onClick={props.onRefresh} disabled={isScanning}>{isScanning ? "扫描中" : "全市场扫描"}</button>
          <button className="secondary-action" onClick={() => setView("manage")}>管理观察池</button>
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
          <Metric label="综合优选" value={`${props.balanced.filter((row) => row.score >= 70).length} 只`} tone={props.balanced.some((row) => row.score >= 70) ? "up" : undefined} />
          <Metric label="强趋势" value={`${strongCount} 只`} tone={strongCount > 0 ? "up" : undefined} />
          <Metric label="反弹候选" value={`${reboundCount} 只`} tone={reboundCount > 0 ? "up" : undefined} />
          <Metric label="扫描成功" value={`${props.status?.success_count ?? 0} 只`} />
          <Metric label="生成时间" value={generatedAt} />
        </div>
        <section className="panel global-radar">
          <div>
            <span>全局选股状态</span>
            <strong>{watchGrade}</strong>
            <p>雷达按沪深 A 股全市场扫描，观察池只作为重点跟踪，不会限制候选范围。</p>
          </div>
          {radarSignals.map((item) => (
            <div className="radar-signal" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.detail}</small>
            </div>
          ))}
        </section>
        {view === "lists" ? (
          <div className="lists-grid single-list">
            <div className="subtabs list-tabs">
              <button className={activeList === "balanced" ? "active" : ""} onClick={() => setActiveList("balanced")}>综合优选</button>
              <button className={activeList === "trend" ? "active" : ""} onClick={() => setActiveList("trend")}>趋势追强</button>
              <button className={activeList === "rebound" ? "active" : ""} onClick={() => setActiveList("rebound")}>超跌反弹</button>
            </div>
            <ResultList title={activeTitle} subtitle={activeSubtitle} rows={activeRows} onOpen={props.onOpen} onWatch={props.onWatch} />
          </div>
        ) : (
          <section className="panel pool-manager">
            <div className="panel-title">
              <div>
                <h2>观察池管理</h2>
                <p>{isUsingDefaultPool ? "观察池为空。雷达仍按全市场扫描。" : "观察池用于重点跟踪，不影响全市场扫描。"}</p>
              </div>
              <button onClick={resetPool}>清空观察池</button>
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
              {activeSymbols.length === 0 && <p>暂无观察代码。后续自选观察会统一迁移到这里。</p>}
            </div>
            {manageStatus && <p>{manageStatus}</p>}
          </section>
        )}
      </section>
    </main>
  );
}

function ResultList(props: { title: string; subtitle: string; rows: ScreenerResult[]; onOpen: (symbol: string) => void; onWatch: (symbol: string) => Promise<void> }) {
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
                <td>
                  <button className="link-button" onClick={() => props.onOpen(row.symbol)}>主页看K线</button>
                  <button className="link-button" onClick={() => props.onWatch(row.symbol)}>加入自选</button>
                </td>
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

function ReviewPage(props: {
  trades: TradeRecord[];
  positions: Position[];
  summary: PortfolioSummary;
  selectedSymbol: string;
  result: BacktestResult | null;
  onRun: (payload: BacktestRequest) => Promise<void>;
}) {
  const [symbol, setSymbol] = useState(props.selectedSymbol);
  const [initialCash, setInitialCash] = useState(100000);
  const [buyThreshold, setBuyThreshold] = useState(72);
  const [sellThreshold, setSellThreshold] = useState(45);
  const [atrMultiplier, setAtrMultiplier] = useState(2);
  const [maxPositionRatio, setMaxPositionRatio] = useState(35);
  const [isRunning, setIsRunning] = useState(false);
  const buyAmount = props.trades.filter((trade) => trade.side === "buy").reduce((sum, trade) => sum + trade.amount, 0);
  const sellAmount = props.trades.filter((trade) => trade.side === "sell").reduce((sum, trade) => sum + trade.amount, 0);
  const activePositionCount = props.positions.length;
  const result = props.result;

  useEffect(() => {
    setSymbol(props.selectedSymbol);
  }, [props.selectedSymbol]);

  const submitBacktest = () => {
    setIsRunning(true);
    props.onRun({
      symbol,
      initial_cash: initialCash,
      buy_threshold: buyThreshold,
      sell_threshold: sellThreshold,
      atr_multiplier: atrMultiplier,
      max_position_ratio: maxPositionRatio / 100,
      commission_rate: 0.0003,
      stamp_tax_rate: 0.0005,
      slippage_rate: 0.0005,
    }).finally(() => setIsRunning(false));
  };

  return (
    <main className="review-grid">
      <section className="panel review-summary">
        <Metric label="交易记录" value={`${props.trades.length} 笔`} />
        <Metric label="当前持仓" value={`${activePositionCount} 只`} />
        <Metric label="累计买入" value={yuan(buyAmount)} />
        <Metric label="累计卖出" value={yuan(sellAmount)} />
        <Metric label="当前浮盈" value={signed(props.summary.floating_pnl)} tone={props.summary.floating_pnl >= 0 ? "up" : "down"} />
      </section>
      <section className="panel backtest-panel">
        <div className="panel-title">
          <div>
            <h2>策略回测</h2>
            <p>用当前决策评分做买卖信号，叠加 ATR 止损、滑点、佣金和印花税。</p>
          </div>
          <button onClick={submitBacktest} disabled={isRunning}>{isRunning ? "回测中" : "运行回测"}</button>
        </div>
        <div className="backtest-controls">
          <label>股票代码<input value={symbol} onChange={(event) => setSymbol(event.target.value)} /></label>
          <label>初始资金<input type="number" value={initialCash} onChange={(event) => setInitialCash(Number(event.target.value))} /></label>
          <label>买入阈值<input type="number" value={buyThreshold} onChange={(event) => setBuyThreshold(Number(event.target.value))} /></label>
          <label>卖出阈值<input type="number" value={sellThreshold} onChange={(event) => setSellThreshold(Number(event.target.value))} /></label>
          <label>ATR倍数<input type="number" step="0.1" value={atrMultiplier} onChange={(event) => setAtrMultiplier(Number(event.target.value))} /></label>
          <label>单票上限%<input type="number" value={maxPositionRatio} onChange={(event) => setMaxPositionRatio(Number(event.target.value))} /></label>
        </div>
        {result ? (
          <>
            <div className="backtest-metrics">
              <Metric label="扣费后收益" value={`${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct.toFixed(2)}%`} tone={result.total_return_pct >= 0 ? "up" : "down"} />
              <Metric label="年化收益" value={`${result.annual_return_pct >= 0 ? "+" : ""}${result.annual_return_pct.toFixed(2)}%`} tone={result.annual_return_pct >= 0 ? "up" : "down"} />
              <Metric label="最大回撤" value={`${result.max_drawdown_pct.toFixed(2)}%`} tone="down" />
              <Metric label="胜率" value={`${(result.win_rate * 100).toFixed(1)}%`} />
              <Metric label="盈亏比" value={result.win_loss_ratio.toFixed(2)} />
              <Metric label="夏普" value={result.sharpe_ratio.toFixed(2)} />
              <Metric label="交易次数" value={`${result.trade_count} 笔`} />
              <Metric label="估算凯利" value={`${(result.estimated_kelly_ratio * 100).toFixed(1)}%`} />
            </div>
            <p className="backtest-summary">{result.name} · {result.start_date} 至 {result.end_date} · {result.summary} 成本合计 {yuan(result.cost_total)}</p>
            <EquityCurve result={result} />
            <BacktestTrades result={result} />
          </>
        ) : (
          <p className="empty-note">运行一次回测后，会显示权益曲线、扣费后收益、回撤、胜率、盈亏比和交易明细。</p>
        )}
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

function EquityCurve({ result }: { result: BacktestResult }) {
  const width = 760;
  const height = 220;
  const values = result.equity_curve.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = result.equity_curve.map((point, index) => {
    const x = result.equity_curve.length <= 1 ? 0 : (index / (result.equity_curve.length - 1)) * width;
    const y = height - ((point.equity - min) / span) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <div className="equity-curve">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="回测权益曲线">
        <polyline points={points} />
      </svg>
      <div>
        <span>{yuan(min)}</span>
        <span>{yuan(max)}</span>
      </div>
    </div>
  );
}

function BacktestTrades({ result }: { result: BacktestResult }) {
  return (
    <div className="trade-table compact">
      <table>
        <thead>
          <tr><th>日期</th><th>方向</th><th>价格</th><th>数量</th><th>费用</th><th>原因</th><th>结果</th></tr>
        </thead>
        <tbody>
          {result.trades.slice(-12).map((trade, index) => (
            <tr key={`${trade.trade_date}-${trade.side}-${index}`}>
              <td>{trade.trade_date}</td>
              <td className={trade.side === "buy" ? "up" : "down"}>{trade.side === "buy" ? "买入" : "卖出"}</td>
              <td>{trade.price.toFixed(2)}</td>
              <td>{trade.quantity}</td>
              <td>{yuan(trade.fee)}</td>
              <td>{trade.reason} · {trade.confidence}</td>
              <td>{trade.pnl == null ? "--" : `${signed(trade.pnl)} / ${trade.pnl_pct?.toFixed(2)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PredictionPage(props: {
  selectedSymbol: string;
  status: PredictionStatus | null;
  result: PredictionResult | null;
  onRun: (symbol: string, horizon: number) => Promise<void>;
  onOpenSettings: () => void;
}) {
  const [symbol, setSymbol] = useState(props.selectedSymbol);
  const [horizon, setHorizon] = useState(20);
  const activeResult = props.result?.symbol === symbol.trim() ? props.result : null;

  useEffect(() => {
    setSymbol(props.selectedSymbol);
  }, [props.selectedSymbol]);

  if (!props.status?.enabled) {
    return (
      <main className="prediction-grid">
        <section className="panel prediction-empty">
          <h2>预测功能未启用</h2>
          <p>在设置中打开预测功能，并按手动命令安装 Kronos 环境。检查通过后这里会显示 K 线预测。</p>
          <button className="primary-action" onClick={props.onOpenSettings}>去设置开启</button>
        </section>
      </main>
    );
  }

  if (!props.status.ready) {
    return (
      <main className="prediction-grid">
        <section className="panel prediction-empty">
          <h2>预测环境未就绪</h2>
          <p>当前状态：{props.status.install_status}。模型：{props.status.model_name}。</p>
          <p>运行目录：{props.status.runtime_path}</p>
          {props.status.last_error && <p>错误：{props.status.last_error}</p>}
          <button className="primary-action" onClick={props.onOpenSettings}>查看安装命令</button>
        </section>
      </main>
    );
  }

  return (
    <main className="prediction-grid">
      <section className="panel prediction-toolbar">
        <label>
          股票代码
          <input value={symbol} onChange={(event) => setSymbol(event.target.value)} inputMode="numeric" />
        </label>
        <label>
          预测天数
          <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
            <option value={10}>10 日</option>
            <option value={20}>20 日</option>
            <option value={30}>30 日</option>
            <option value={60}>60 日</option>
          </select>
        </label>
        <button className="primary-action" disabled={!symbol.trim()} onClick={() => props.onRun(symbol.trim(), horizon)}>生成预测</button>
        <MiniStat label="模型" value={props.status.model_name} />
      </section>
      {activeResult ? (
        <>
          <section className="metrics-grid">
            <Metric label="预测股票" value={`${activeResult.name} ${activeResult.symbol}`} />
            <Metric label="预测周期" value={`${activeResult.horizon} 日`} />
            <Metric label="预期涨跌" value={`${activeResult.expected_change_pct >= 0 ? "+" : ""}${activeResult.expected_change_pct.toFixed(2)}%`} tone={activeResult.expected_change_pct >= 0 ? "up" : "down"} />
            <Metric label="生成时间" value={new Date(activeResult.generated_at).toLocaleString("zh-CN", { hour12: false })} />
            <Metric label="数据" value="历史 + 预测" />
          </section>
          <section className="panel chart-panel prediction-chart">
            <KLineChart bars={[...activeResult.history, ...activeResult.forecast]} />
          </section>
          <section className="panel trade-table">
            <div className="panel-title">
              <div>
                <h2>预测 K 线</h2>
                <p>{activeResult.message}</p>
              </div>
            </div>
            <table>
              <thead>
                <tr><th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>成交量</th></tr>
              </thead>
              <tbody>
                {activeResult.forecast.map((bar) => (
                  <tr key={bar.timestamp}>
                    <td>{bar.trade_date}</td>
                    <td>{bar.open.toFixed(2)}</td>
                    <td>{bar.high.toFixed(2)}</td>
                    <td>{bar.low.toFixed(2)}</td>
                    <td>{bar.close.toFixed(2)}</td>
                    <td>{bar.volume.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : (
        <section className="panel prediction-empty">
          <h2>等待生成预测</h2>
          <p>选择股票和预测天数后点击“生成预测”。模型输出只用于辅助观察，不构成交易建议。</p>
        </section>
      )}
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
  marketSettings: MarketSettings | null;
  onSaveMarketSettings: (provider: string, tushareToken: string) => Promise<void>;
  predictionStatus: PredictionStatus | null;
  onSavePredictionSettings: (enabled: boolean, modelName: string) => Promise<PredictionStatus>;
  onCheckPredictionEnvironment: () => Promise<PredictionStatus>;
}) {
  const [symbolsText, setSymbolsText] = useState((props.screenerConfig?.symbols ?? []).join(", "));
  const [marketProvider, setMarketProvider] = useState(props.marketSettings?.provider ?? "auto");
  const [tushareToken, setTushareToken] = useState("");
  const [predictionEnabled, setPredictionEnabled] = useState(Boolean(props.predictionStatus?.enabled));
  const [predictionModel, setPredictionModel] = useState(props.predictionStatus?.model_name ?? "NeoQuasar/Kronos-small");
  const [settingsStatus, setSettingsStatus] = useState("");
  const [marketSettingsStatus, setMarketSettingsStatus] = useState("");
  const [predictionSettingsStatus, setPredictionSettingsStatus] = useState("");

  useEffect(() => {
    setSymbolsText((props.screenerConfig?.symbols ?? []).join(", "));
  }, [props.screenerConfig]);

  useEffect(() => {
    setPredictionEnabled(Boolean(props.predictionStatus?.enabled));
    setPredictionModel(props.predictionStatus?.model_name ?? "NeoQuasar/Kronos-small");
  }, [props.predictionStatus]);

  useEffect(() => {
    setMarketProvider(props.marketSettings?.provider ?? "auto");
  }, [props.marketSettings]);

  const saveSymbols = async () => {
    const symbols = symbolsText.split(/[\s,，]+/).map((symbol) => symbol.trim()).filter(Boolean);
    try {
      await props.onSaveScreenerSymbols(symbols);
      setSettingsStatus("观察池已保存。选股雷达继续按全市场扫描。");
    } catch {
      setSettingsStatus("保存失败，请检查股票代码。");
    }
  };

  const savePrediction = async () => {
    try {
      await props.onSavePredictionSettings(predictionEnabled, predictionModel);
      setPredictionSettingsStatus(predictionEnabled ? "预测功能已启用。请按下方命令手动安装，然后点击检查环境。" : "预测功能已关闭。");
    } catch {
      setPredictionSettingsStatus("预测设置保存失败。");
    }
  };

  const checkPrediction = async () => {
    try {
      const status = await props.onCheckPredictionEnvironment();
      setPredictionSettingsStatus(status.ready ? "Kronos 环境检查通过。" : "Kronos 环境检查未通过，请查看错误和命令。");
    } catch {
      setPredictionSettingsStatus("Kronos 环境检查失败。");
    }
  };

  const saveMarket = async () => {
    try {
      await props.onSaveMarketSettings(marketProvider, tushareToken);
      setMarketSettingsStatus("数据源设置已保存。");
      setTushareToken("");
    } catch {
      setMarketSettingsStatus("数据源设置保存失败。");
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
        <label>
          数据源
          <select value={marketProvider} onChange={(event) => setMarketProvider(event.target.value)}>
            <option value="auto">自动</option>
            <option value="akshare">AkShare</option>
            <option value="sina">Sina</option>
            <option value="tushare">Tushare</option>
            <option value="efinance">efinance</option>
            <option value="baostock">BaoStock</option>
            <option value="tencent">Tencent</option>
            <option value="sample">示例数据</option>
          </select>
        </label>
        <label>
          Tushare Token
          <input value={tushareToken} onChange={(event) => setTushareToken(event.target.value)} placeholder={props.marketSettings?.tushare_token_configured ? "已配置，留空则保留" : "可选"} />
        </label>
        <button className="primary-action" onClick={saveMarket}>保存数据源</button>
        {marketSettingsStatus && <p>{marketSettingsStatus}</p>}
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
          重点观察池
          <textarea value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} rows={8} placeholder="300308, 300502, 601138" />
        </label>
        <button className="primary-action" onClick={saveSymbols}>保存观察池</button>
        <MiniStat label="全市场扫描规模" value={`${props.screenerStatus?.pool_size ?? 0} 只`} />
        <MiniStat label="观察池" value={`${props.screenerConfig?.symbols.length ?? 0} 只`} />
        <MiniStat label="最近耗时" value={props.screenerStatus?.last_duration_seconds == null ? "--" : `${props.screenerStatus.last_duration_seconds} 秒`} />
        {settingsStatus && <p>{settingsStatus}</p>}
      </section>
      <section className="panel settings-card">
        <h2>预测功能</h2>
        <label className="inline-setting">
          <input type="checkbox" checked={predictionEnabled} onChange={(event) => setPredictionEnabled(event.target.checked)} />
          启用 Kronos K 线预测
        </label>
        <label>
          模型
          <select value={predictionModel} onChange={(event) => setPredictionModel(event.target.value)}>
            <option value="NeoQuasar/Kronos-small">Kronos-small</option>
            <option value="NeoQuasar/Kronos-base">Kronos-base</option>
          </select>
        </label>
        <button className="primary-action" onClick={savePrediction}>保存预测设置</button>
        <button className="refresh-button" onClick={checkPrediction}>检查环境</button>
        <MiniStat label="安装状态" value={props.predictionStatus?.install_status ?? "not_installed"} />
        <MiniStat label="运行目录" value={props.predictionStatus?.runtime_path ?? "--"} />
        <div className="settings-static">
          {(props.predictionStatus?.environment_checks ?? []).map((item) => (
            <MiniStat key={item} label="检查项" value={item} />
          ))}
        </div>
        <div className="command-list">
          {(props.predictionStatus?.install_commands ?? []).map((command) => (
            <code key={command}>{command}</code>
          ))}
        </div>
        {predictionSettingsStatus && <p>{predictionSettingsStatus}</p>}
        {props.predictionStatus?.last_error && <p>{props.predictionStatus.last_error}</p>}
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
