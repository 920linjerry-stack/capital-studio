// detail.js — 个股详情页
// v3.2.1：加载行情时根据等待时间动态更新提示文字（首次港股/A 股慢）。

const API = "http://127.0.0.1:5000";

const params    = new URLSearchParams(window.location.search);
const SYMBOL    = params.get("symbol") || "";
const COST      = parseFloat(params.get("cost") || "0");
const QUANTITY  = parseFloat(params.get("qty")  || "0");

let priceChart = null;

// HTML-escape values interpolated into innerHTML (避免把错误信息/外部字段当 HTML 解析)。
function escapeHtml(v) {
  if (v == null) return "";
  return String(v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ── 渐进式加载提示 ────────────────────────────────────────────────────────────
// 检测到港股/A 股时，等待超过 3 秒/30 秒分别更新文案
function _isSlowMarket(sym) {
  return sym.endsWith(".HK") || sym.endsWith(".SS") || sym.endsWith(".SZ");
}

function _setupProgressiveLoading(loadingEl) {
  if (!_isSlowMarket(SYMBOL)) return [];   // 美股秒返，不需要

  const t1 = setTimeout(() => {
    loadingEl.textContent = "首次加载港股/A 股需 30-60 秒，正在抓取数据…";
  }, 3000);

  const t2 = setTimeout(() => {
    loadingEl.textContent = "数据较多，请耐心等候。下次访问将秒开（已建立本地缓存）。";
  }, 30000);

  return [t1, t2];   // 返回 timer 列表，加载完后清掉
}

function _clearTimers(timers) {
  timers.forEach(t => clearTimeout(t));
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

function colorClass(v) { return v > 0 ? "up" : v < 0 ? "down" : "flat"; }

function signed(v, d = 2) {
  const s = Number(v).toFixed(d);
  return v > 0 ? `+${s}` : s;
}

function formatMarketCap(n) {
  if (n == null) return "--";
  // n 现在是"百万原币种"（v3.2 归一化后）
  // 所以转换分级要除以的是百万级单位
  if (n >= 1e6)  return (n / 1e6).toFixed(2) + "T";  // 1e6 百万 = 1 万亿
  if (n >= 1e3)  return (n / 1e3).toFixed(2) + "B";  // 1e3 百万 = 10 亿
  if (n >= 1)    return n.toFixed(2) + "M";
  return n.toFixed(4);
}

// ── 价格走势图 ────────────────────────────────────────────────────────────────

function renderPriceChart(histData, costPrice) {
  const canvas = document.getElementById("price-chart");

  if (!histData || histData.length === 0) {
    canvas.style.display = "none";
    return;
  }

  const labels = histData.map(d => d.date);
  const prices = histData.map(d => d.close);

  const lineColor = prices[prices.length - 1] >= prices[0]
    ? "rgba(248, 81, 73, 0.9)"
    : "rgba(63, 185, 80, 0.9)";

  const costLine = costPrice > 0
    ? new Array(labels.length).fill(costPrice)
    : null;

  const datasets = [{
    label          : "收盘价",
    data           : prices,
    borderColor    : lineColor,
    backgroundColor: lineColor.replace("0.9", "0.08"),
    borderWidth    : 1.5,
    pointRadius    : 0,
    fill           : true,
    tension        : 0.1,
  }];

  if (costLine) {
    datasets.push({
      label      : `买入价 ${costPrice}`,
      data       : costLine,
      borderColor: "#d29922",
      borderWidth: 1.5,
      borderDash : [6, 4],
      pointRadius: 0,
      fill       : false,
      tension    : 0,
    });
  }

  canvas.style.display = "block";

  if (priceChart) {
    priceChart.data.labels = labels;
    priceChart.data.datasets = datasets;
    priceChart.update();
    return;
  }

  priceChart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive          : true,
      maintainAspectRatio : false,
      interaction         : { mode: "index", intersect: false },
      plugins: {
        legend : { labels: { color: "#8b949e", font: { size: 12 }, boxWidth: 20 } },
        tooltip: {
          backgroundColor: "#161b22", borderColor: "#30363d", borderWidth: 1,
          titleColor: "#e6edf3", bodyColor: "#8b949e",
          callbacks: {
            title: (items) => items[0].label,
            label: (ctx)   => ` ${ctx.dataset.label}: ${ctx.raw.toFixed(3)}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: "#8b949e", maxTicksLimit: 8, font: { size: 11 } },
             grid : { color: "#21262d" } },
        y: { position: "right",
             ticks: { color: "#8b949e", font: { size: 11 } },
             grid : { color: "#21262d" } },
      },
    },
  });
}

// ── 主加载 ────────────────────────────────────────────────────────────────────

async function loadDetail(period = "1y") {
  if (!SYMBOL) {
    document.getElementById("loading").textContent = "未找到股票代码，请返回首页";
    return;
  }

  document.title = `${SYMBOL} - 详情`;

  const loadingEl = document.getElementById("loading");
  const detailContent = document.getElementById("detail-content");
  const isPeriodSwitch = detailContent && detailContent.style.display !== "none";
  const chartContainer = document.querySelector(".chart-container");
  if (isPeriodSwitch) {
    if (chartContainer) chartContainer.classList.add("is-loading");
  } else {
    loadingEl.style.display = "block";
    loadingEl.textContent   = "正在加载行情数据…";
  }
  // 启动渐进式提示
  const timers = isPeriodSwitch ? [] : _setupProgressiveLoading(loadingEl);

  try {
    const [quoteRes, histRes] = await Promise.all([
      fetch(`${API}/api/quote/${SYMBOL}`),
      fetch(`${API}/api/history/${SYMBOL}?period=${period}`),
    ]);

    const quote = await quoteRes.json();
    const hist  = await histRes.json();

    _clearTimers(timers);
    loadingEl.style.display = "none";
    if (chartContainer) chartContainer.classList.remove("is-loading");
    detailContent.style.display = "block";

    // 标题
    document.getElementById("d-symbol").textContent   = SYMBOL;
    document.getElementById("d-name").textContent     = quote.name || "--";
    document.getElementById("d-currency").textContent = quote.currency || "";

    const priceEl  = document.getElementById("d-price");
    const changeEl = document.getElementById("d-change");
    if (quote.current_price != null) {
      priceEl.textContent  = quote.current_price.toFixed(3);
      priceEl.className    = "detail-price mono " + colorClass(quote.change_pct);
      changeEl.textContent = `${signed(quote.change_pct)}%`;
      changeEl.className   = "detail-change mono " + colorClass(quote.change_pct);
    }

    // 关键指标
    document.getElementById("d-pe").textContent     = quote.pe_ratio    != null ? quote.pe_ratio    : "--";
    document.getElementById("d-pb").textContent     = quote.pb_ratio    != null ? quote.pb_ratio    : "--";
    document.getElementById("d-mktcap").textContent = formatMarketCap(quote.market_cap);
    document.getElementById("d-52h").textContent    = quote.week52_high != null ? quote.week52_high.toFixed(3) : "--";
    document.getElementById("d-52l").textContent    = quote.week52_low  != null ? quote.week52_low.toFixed(3)  : "--";

    if (COST > 0) {
      document.getElementById("d-cost").textContent = COST.toFixed(3);
      if (quote.current_price != null) {
        const pnlAmt = (quote.current_price - COST) * QUANTITY;
        const pnlPct = (quote.current_price - COST) / COST * 100;
        const pnlEl  = document.getElementById("d-pnl");
        pnlEl.textContent = `${signed(pnlAmt, 0)}元  (${signed(pnlPct)}%)`;
        pnlEl.className   = "stat-value " + colorClass(pnlAmt);
      }
    } else {
      document.getElementById("d-cost").textContent = "--";
    }

    renderPriceChart(hist, COST);

  } catch (err) {
    _clearTimers(timers);
    if (chartContainer) chartContainer.classList.remove("is-loading");
    if (!isPeriodSwitch) {
      loadingEl.innerHTML =
        `<span style="color:var(--red);">⚠ 数据加载失败：${escapeHtml(err.message)}</span>`;
    }
    console.error(err);
  }
}

// ── 时间段切换 ────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadDetail("1y");

  document.querySelectorAll(".period-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active-period"));
      btn.classList.add("active-period");
      loadDetail(btn.dataset.period);
    });
  });
});
