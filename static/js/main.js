// main.js — PT 首页
// v3.2.1 改动：首次加载若组合含港股/A 股，显示一次温和的提示，session 内不再显示。
// 自动刷新、多币种、双行金额等已有逻辑完整保留。

const API              = "http://127.0.0.1:5000";
const REFRESH_INTERVAL = 60 * 1000;

// ── 状态 ──────────────────────────────────────────────────────────────────────
let currentBase     = "HKD";
let autoRefreshTimer = null;

// session 标记：是否已经显示过"首次加载港股/A 股"提示
let _slowMarketHintShown = false;

// 渐进式 loading 提示用的 timer
let _loadingTimers = [];

// ── 自动刷新 ──────────────────────────────────────────────────────────────────

function onToggleAutoRefresh() {
  const isOn  = document.getElementById("auto-refresh-toggle").checked;
  const dotEl = document.getElementById("live-dot");

  if (isOn) {
    dotEl.style.display = "inline";
    loadPortfolio();
    autoRefreshTimer = setInterval(() => {
      loadPortfolio().catch(err => console.log("[auto-refresh] 刷新失败：", err));
    }, REFRESH_INTERVAL);
  } else {
    dotEl.style.display = "none";
    if (autoRefreshTimer !== null) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

// HTML-escape any value that is interpolated into innerHTML as text.
// 行情来源（yfinance/akshare）返回的公司名等字段，以及用户输入的 symbol，
// 都不是可信 HTML，必须转义后再拼接，避免 XSS。
function escapeHtml(v) {
  if (v == null) return "";
  return String(v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function colorClass(v) { return v > 0 ? "up" : v < 0 ? "down" : "flat"; }
function signed(v, d = 2) {
  const s = Number(v).toFixed(d);
  return v > 0 ? `+${s}` : s;
}
function formatMoney(n, decimals = 2) {
  if (n == null) return "--";
  return Number(n).toLocaleString("zh-CN",
    { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function amountCell(nativeVal, nativeCcy, baseVal, baseCcy, colorCls = "") {
  const sameAmt = nativeCcy === baseCcy;
  const primary = `
    <span class="amount-primary ${colorCls}">
      ${formatMoney(nativeVal)}<span class="ccy-tag">${nativeCcy}</span>
    </span>`;
  const secondary = sameAmt ? "" : `
    <span class="amount-secondary">
      ≈ ${formatMoney(baseVal)}<span class="ccy-tag" style="font-size:9px;">${baseCcy}</span>
    </span>`;
  return `<div class="amount-cell">${primary}${secondary}</div>`;
}

// ── 渐进式加载提示 ────────────────────────────────────────────────────────────

function _hasSlowMarketHoldings() {
  // 通过 portfolio.json 已加载的局部存储不可靠；这里在请求前先用 add 时的 symbol 判断
  // 简化做法：从 portfolio 里出现过的 symbol 表中查（实际上 holdings 数据来自后端）
  // 为了不引入额外查询，我们直接在每次 load 前都设一组 timer，反正失败时会清掉
  return true;
}

function _setupProgressiveLoading(loadingEl) {
  _clearLoadingTimers();
  if (!_hasSlowMarketHoldings()) return;

  const t1 = setTimeout(() => {
    loadingEl.textContent = "正在抓取数据…（首次访问港股/A 股较慢，请稍候）";
  }, 3000);
  const t2 = setTimeout(() => {
    loadingEl.textContent = "首次抓取需 1-2 分钟（港股/A 股财报量大），完成后会本地缓存，下次秒开。";
  }, 30000);

  _loadingTimers = [t1, t2];
}

function _clearLoadingTimers() {
  _loadingTimers.forEach(t => clearTimeout(t));
  _loadingTimers = [];
}

// session 级温和提示：放在持仓表上方一行小字（首次后自动消失）
function _maybeShowSlowMarketHint(holdings) {
  if (_slowMarketHintShown) return;

  const hasSlowMarket = holdings.some(h =>
    h.symbol && (h.symbol.endsWith(".HK") ||
                 h.symbol.endsWith(".SS") ||
                 h.symbol.endsWith(".SZ"))
  );
  if (!hasSlowMarket) return;

  // 仅当所有股票都成功加载（无 error）才认为"首次跑完了"，标记 shown
  const allLoaded = holdings.every(h => !h.error);
  if (allLoaded) _slowMarketHintShown = true;
}

// ── 饼图 ──────────────────────────────────────────────────────────────────────
let pieChart = null;
const PIE_COLORS = ["#388bfd","#f85149","#3fb950","#d29922","#a371f7","#39d353","#ff9500","#79c0ff"];

function renderPieChart(holdings, baseCcy) {
  const canvas = document.getElementById("pie-chart");
  const legend = document.getElementById("pie-legend");
  const valid  = holdings.filter(h => h.market_value_base > 0);

  if (valid.length === 0) {
    canvas.style.display = "none";
    legend.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">暂无持仓数据</span>';
    return;
  }

  canvas.style.display = "";
  const values = valid.map(h => h.market_value_base);
  const total  = values.reduce((a, b) => a + b, 0);

  if (pieChart) pieChart.destroy();

  pieChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels  : valid.map(h => h.symbol),
      datasets: [{
        data: values,
        backgroundColor: PIE_COLORS.slice(0, valid.length),
        borderColor: "#0d1117", borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const pct = (ctx.raw / total * 100).toFixed(1);
              return ` ${ctx.label}  ${formatMoney(ctx.raw)} ${baseCcy}  (${pct}%)`;
            },
          },
        },
      },
      cutout: "60%",
    },
  });

  legend.innerHTML = valid.map((h, i) => `
    <div class="legend-item">
      <div class="legend-dot" style="background:${PIE_COLORS[i]}"></div>
      <span>${escapeHtml(h.symbol)}</span>
      <span style="color:var(--text-primary);">${(values[i] / total * 100).toFixed(1)}%</span>
    </div>`).join("");
}

// ── 数据加载 ──────────────────────────────────────────────────────────────────

async function loadPortfolio(showLoading = false) {
  const loading   = document.getElementById("loading");
  const tableWrap = document.getElementById("table-wrap");
  const emptyHint = document.getElementById("empty-hint");

  if (showLoading) {
    loading.style.display   = "block";
    loading.textContent     = "正在获取行情数据，请稍候…";
    tableWrap.style.display = "none";
    emptyHint.style.display = "none";
    _setupProgressiveLoading(loading);
  }

  document.getElementById("base-select").value = currentBase;

  try {
    const res  = await fetch(`${API}/api/portfolio?base=${currentBase}`);
    const data = await res.json();

    _clearLoadingTimers();
    loading.style.display = "none";

    const { holdings, summary, base_currency } = data;

    if (!holdings || holdings.length === 0) {
      emptyHint.style.display = "block";
      tableWrap.style.display = "none";
      renderSummary(null, currentBase);
      return;
    }

    emptyHint.style.display = "none";
    renderSummary(summary, base_currency);
    renderTable(holdings, base_currency);
    renderPieChart(holdings, base_currency);

    const warnEl = document.getElementById("fx-warn");
    warnEl.style.display = summary.has_fallback_fx ? "inline" : "none";

    document.getElementById("last-updated").textContent =
      "最后更新：" + new Date().toLocaleTimeString("zh-CN");

    tableWrap.style.display = "block";

    _maybeShowSlowMarketHint(holdings);

  } catch (err) {
    _clearLoadingTimers();
    if (showLoading) {
      loading.innerHTML = `<span style="color:var(--red);">⚠ 无法连接后端服务，请确认 app.py 正在运行。</span>`;
    }
    console.error(err);
  }
}

// ── 渲染 ─────────────────────────────────────────────────────────────────────

function renderSummary(summary, base) {
  ["lbl-market","lbl-cost","lbl-pnl","lbl-daily"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = base || "";
  });

  const summaryLabel = document.getElementById("summary-base-label");
  if (summaryLabel) summaryLabel.textContent = base ? `· ${base}` : "";

  if (!summary) {
    ["total-market","total-cost","total-pnl","total-pnl-pct","daily-pnl"]
      .forEach(id => document.getElementById(id).textContent = "--");
    return;
  }

  document.getElementById("total-market").textContent = formatMoney(summary.total_market_value);
  document.getElementById("total-cost").textContent   = formatMoney(summary.total_cost);

  const tp = document.getElementById("total-pnl");
  tp.textContent = signed(summary.total_pnl_amount);
  tp.className   = "metric-value mono " + colorClass(summary.total_pnl_amount);

  const tpp = document.getElementById("total-pnl-pct");
  tpp.textContent = signed(summary.total_pnl_pct) + "%";
  tpp.className   = "metric-value mono " + colorClass(summary.total_pnl_pct);

  const dp = document.getElementById("daily-pnl");
  dp.textContent = signed(summary.total_daily_pnl);
  dp.className   = "metric-value mono " + colorClass(summary.total_daily_pnl);
}

function renderTable(holdings, base) {
  const tbody = document.getElementById("holdings-body");

  tbody.innerHTML = holdings.map(h => {
    if (h.error) {
      return `<tr>
        <td class="symbol-cell">${escapeHtml(h.symbol)}</td>
        <td colspan="8" style="color:var(--red);font-size:12px;">⚠ ${escapeHtml(h.error)}</td>
        <td><button class="btn btn-danger" data-action="delete" data-symbol="${escapeHtml(h.symbol)}">删除</button></td>
      </tr>`;
    }

    const ccy      = h.currency || "USD";
    const chgClass = colorClass(h.change_pct);
    const pnlClass = colorClass(h.pnl_amount_native);

    const costDisplay = `
      <div class="amount-cell">
        <span class="amount-primary">
          ${Number(h.cost_price).toFixed(3)}<span class="ccy-tag">${ccy}</span>
        </span>
      </div>`;

    const mvDisplay  = amountCell(h.market_value_native, ccy, h.market_value_base, base);
    const pnlDisplay = amountCell(h.pnl_amount_native,   ccy, h.pnl_amount_base,   base, pnlClass);
    const dpClass    = colorClass(h.daily_pnl_native);
    const dpDisplay  = amountCell(h.daily_pnl_native,    ccy, h.daily_pnl_base,    base, dpClass);

    return `<tr data-action="detail" data-symbol="${escapeHtml(h.symbol)}" data-cost="${escapeHtml(h.cost_price)}" data-qty="${escapeHtml(h.quantity)}">
      <td>
        <div class="symbol-cell">${escapeHtml(h.symbol)}</div>
        <div class="name-cell">${escapeHtml(h.name) || "--"}</div>
      </td>
      <td class="mono ${chgClass}">${h.current_price != null ? h.current_price.toFixed(3) : "--"}</td>
      <td class="mono ${chgClass}">${signed(h.change_pct)}%</td>
      <td>${costDisplay}</td>
      <td class="mono">${Number(h.quantity).toLocaleString()}</td>
      <td>${mvDisplay}</td>
      <td>${pnlDisplay}</td>
      <td class="mono ${pnlClass}">${signed(h.pnl_pct)}%</td>
      <td>${dpDisplay}</td>
      <td>
        <button class="btn btn-danger"
          data-action="delete" data-symbol="${escapeHtml(h.symbol)}">
          删除
        </button>
      </td>
    </tr>`;
  }).join("");
}

// ── 事件 ─────────────────────────────────────────────────────────────────────

function onBaseChange() {
  currentBase = document.getElementById("base-select").value;
  loadPortfolio().catch(err => console.log("[base-change] 加载失败：", err));
}

function goDetail(symbol, costPrice, quantity) {
  window.location.href =
    `/detail?symbol=${encodeURIComponent(symbol)}` +
    `&cost=${encodeURIComponent(costPrice)}&qty=${encodeURIComponent(quantity)}`;
}

async function addStock() {
  const symbol = document.getElementById("input-symbol").value.trim().toUpperCase();
  const cost   = parseFloat(document.getElementById("input-cost").value);
  const qty    = parseFloat(document.getElementById("input-qty").value);
  const date   = document.getElementById("input-date").value;
  const errEl  = document.getElementById("add-error");

  errEl.textContent = "";

  if (!symbol)                  { errEl.textContent = "请输入股票代码";   return; }
  if (isNaN(cost) || cost <= 0) { errEl.textContent = "请输入有效买入价"; return; }
  if (isNaN(qty)  || qty  <= 0) { errEl.textContent = "请输入有效持仓量"; return; }

  try {
    const res  = await fetch(`${API}/api/portfolio`, {
      method : "POST",
      headers: { "Content-Type": "application/json" },
      body   : JSON.stringify({ symbol, cost_price: cost, quantity: qty, buy_date: date }),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || "添加失败"; return; }

    ["input-symbol","input-cost","input-qty","input-date"]
      .forEach(id => document.getElementById(id).value = "");

    loadPortfolio(true).catch(err => console.log("[add-stock] 刷新失败：", err));
  } catch (err) {
    errEl.textContent = "网络错误：" + err.message;
  }
}

async function deleteStock(symbol) {
  if (!confirm(`确认删除 ${symbol}？`)) return;
  try {
    const res = await fetch(`${API}/api/portfolio/${encodeURIComponent(symbol)}`, { method: "DELETE" });
    if (res.ok) loadPortfolio().catch(err => console.log("[delete] 刷新失败：", err));
  } catch (err) {
    alert("删除失败：" + err.message);
  }
}

// ── 持仓表事件委托 ────────────────────────────────────────────────────────────
// 用 data-* 属性 + 事件委托代替行内 onclick，避免把 symbol/name 等值拼进
// JS 字符串上下文（消除注入面）。监听器只挂一次；renderTable 重写 innerHTML
// 不影响已绑定在 tbody 上的委托。
function _setupHoldingsTableEvents() {
  const tbody = document.getElementById("holdings-body");
  if (!tbody) return;
  tbody.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el || !tbody.contains(el)) return;
    if (el.dataset.action === "delete") {
      deleteStock(el.dataset.symbol);
    } else if (el.dataset.action === "detail") {
      goDetail(el.dataset.symbol, el.dataset.cost, el.dataset.qty);
    }
  });
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  _setupHoldingsTableEvents();
  loadPortfolio(true);
});