// dcf.js — DCF 估值页前端逻辑
// v3.2.1：拉取 defaults 时根据等待时间动态更新 loading 文案
//         （首次抓港股/A 股财报最慢）。
// v3.2 已有逻辑（unit state、displayValue、moneyState、数据源提示等）完整保留。

const API = "http://127.0.0.1:5000";

// HTML-escape values interpolated into innerHTML. URL params (?symbol=…) 等外部
// 输入必须转义后再拼接，避免反射型 XSS。
function escapeHtml(v) {
  if (v == null) return "";
  return String(v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const SCENARIO = (new URLSearchParams(window.location.search).get("scenario") || "base").toLowerCase();
const IS_BASE = SCENARIO === "base";
const IS_BULL = SCENARIO === "bull";
const IS_BEAR = SCENARIO === "bear";
const IS_SCENARIO_PAGE = IS_BULL || IS_BEAR;

// ── 状态 ──────────────────────────────────────────────────────────────────────
let currentDefaults = null;
let currentResults  = null;
let tvMethod        = "average";
let recalcTimer     = null;
let _baseCache      = null;
let _scenarioUpdatedAt = null;
let _scenarioCompatibility = {};
let _manualOperatingOverrides = {};
let _assumptionProvenance = {};
let _normalizedEbitApplyMessage = "";

let displayUnit     = "millions";

const UNIT_MULTIPLIERS = {
  "actual"   : 0.000001,
  "thousands": 0.001,
  "millions" : 1.0,
  "yi"       : 100.0,
  "billions" : 1000.0,
};

const MONEY_FIELDS = [
  ["f-revenue",   "revenue"],
  ["f-ebit",      "ebit"],
  ["f-da",        "da"],
  ["f-capex",     "capex"],
  ["f-wc-change", "wc_change"],
  ["f-net-debt",  "net_debt"],
];

const ASSUMPTION_LABELS = {
  revenue_growth: "Revenue Growth",
  ebit_margin: "EBIT Margin",
  da_pct_revenue: "D&A % Revenue",
  capex_pct_revenue: "CapEx % Revenue",
  wc_change_pct_revenue: "Delta NWC % Revenue (reference/fallback)",
  wacc: "WACC",
  terminal_g: "Terminal Growth",
  exit_multiple: "Exit Multiple",
  price: "Current Price",
  revenue: "Revenue",
  ebit: "EBIT",
  da: "D&A",
  capex: "CapEx",
  wc_change: "Delta NWC",
  tax_rate: "Tax Rate",
  net_debt: "Net Debt (Debt - Cash - selected MS)",
  shares: "Diluted Shares",
  forecast_years: "Forecast Years",
  tv_method: "Terminal Value Method",
  rf: "Risk-free Rate",
  erp: "Equity Risk Premium",
  beta: "Beta",
};

// V3.9.0 Forecast Path Upgrade v1: drivers exposed in the advanced 5-year path
// editor. Order matches the Assumptions sheet Operating Forecast Path block.
const FORECAST_PATH_DRIVERS = [
  ["revenue_growth",        "Revenue Growth"],
  ["ebit_margin",           "EBIT Margin"],
  ["da_pct_revenue",        "D&A % Revenue"],
  ["capex_pct_revenue",     "CapEx % Revenue"],
  ["wc_change_pct_revenue", "Delta NWC % Revenue (reference/fallback)"],
];

function _pathInputId(key, year) { return `p-path-${key}-y${year + 1}`; }

function renderForecastPathEditor(defaults, singleValuesDecimal) {
  const root = document.getElementById("forecast-path-editor");
  if (!root) return;
  // Strip previous driver rows; keep the column header row (first 6 nodes).
  while (root.childNodes.length > 6) root.removeChild(root.lastChild);
  FORECAST_PATH_DRIVERS.forEach(([key, label]) => {
    const fallback = Number(singleValuesDecimal[key] ?? 0);
    const supplied = Array.isArray(defaults && defaults[`${key}_path`])
      ? defaults[`${key}_path`].slice(0, 5).map(Number)
      : null;
    const lbl = document.createElement("div");
    lbl.textContent = label;
    lbl.style.color = "var(--text-muted)";
    root.appendChild(lbl);
    for (let i = 0; i < 5; i++) {
      const wrap = document.createElement("div");
      wrap.style.display = "flex";
      wrap.style.alignItems = "center";
      wrap.style.gap = "2px";
      const input = document.createElement("input");
      input.type = "number";
      input.step = "0.1";
      input.className = "dcf-input";
      input.id = _pathInputId(key, i);
      const decimalVal = supplied && supplied.length === 5 ? supplied[i] : fallback;
      input.value = (Number(decimalVal) * 100).toFixed(4);
      input.style.minWidth = "0";
      input.style.width = "100%";
      input.addEventListener("change", () => {
        markOperatingOverride(key);
        if (typeof recalc === "function") recalc();
      });
      const unit = document.createElement("span");
      unit.textContent = "%";
      unit.style.color = "var(--text-muted)";
      unit.style.fontSize = "11px";
      wrap.appendChild(input);
      wrap.appendChild(unit);
      root.appendChild(wrap);
    }
  });
}

function markOperatingOverride(key) {
  _manualOperatingOverrides[key] = true;
  if (key === "ebit_margin" && _assumptionProvenance.ebit_margin?.source === "normalized_ebit_candidate") {
    _normalizedEbitApplyMessage = "";
  }
}

function collectForecastPath(key) {
  const out = [];
  for (let i = 0; i < 5; i++) {
    const el = document.getElementById(_pathInputId(key, i));
    if (!el) return null;
    const v = Number(el.value);
    if (!Number.isFinite(v)) return null;
    out.push(v / 100);
  }
  return out;
}

function collectForecastPathForPayload(key, singleDecimal) {
  const path = collectForecastPath(key);
  if (!path || path.length !== 5) return path;

  const defaultPath = Array.isArray(currentDefaults && currentDefaults[`${key}_path`])
    ? currentDefaults[`${key}_path`].slice(0, 5).map(Number)
    : null;
  const defaultSingle = Number(currentDefaults && currentDefaults[key]);
  const single = Number(singleDecimal);
  const nearlyEqual = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 0.0000005;

  if (
    defaultPath && defaultPath.length === 5 &&
    Number.isFinite(single) &&
    !nearlyEqual(single, defaultSingle) &&
    path.every((v, i) => nearlyEqual(Number(v), Number(defaultPath[i])))
  ) {
    return [single, single, single, single, single];
  }

  return path;
}

const DIFF_FIELDS = [
  ["revenue_growth",        "Revenue Growth",        "pct"],
  ["ebit_margin",           "EBIT Margin",           "pct"],
  ["da_pct_revenue",        "D&A % Revenue",         "pct"],
  ["capex_pct_revenue",     "CapEx % Revenue",       "pct"],
  ["wc_change_pct_revenue", "Delta NWC % Revenue (reference/fallback)",   "pct"],
  ["wacc",          "WACC",                   "pct"],
  ["terminal_g",    "Terminal Growth",        "pct"],
  ["exit_multiple", "Exit Multiple",          "x"],
  ["price",         "Current Price",          "raw"],
  ["revenue",       "Revenue",                "raw"],
  ["ebit",          "EBIT",                   "raw"],
  ["da",            "D&A",                    "raw"],
  ["capex",         "CapEx",                  "raw"],
  ["wc_change",     "Delta NWC",              "raw"],
  ["tax_rate",      "Tax Rate",               "pct"],
  ["net_debt",      "Net Debt (negative = net cash)",               "raw"],
  ["shares",        "Diluted Shares",         "raw"],
  ["selected_net_debt_treatment", "Net Debt Treatment", "label"],
];

// V3.7.3: human labels for the four net-debt treatments. Mirror of the Python
// NET_DEBT_TREATMENT_LABELS map; UI shows labels, but API / scenario JSON keep
// keys so label edits never invalidate stored documents.
const NET_DEBT_TREATMENT_LABELS = {
  reported_input_net_debt: "Reported / Input Net Debt",
  debt_less_cash: "Debt less Cash",
  debt_less_cash_and_st_investments: "Debt less Cash & ST Investments",
  debt_less_cash_and_total_marketable_securities: "Debt less Cash & Total Marketable Securities",
};
const DEFAULT_NET_DEBT_TREATMENT = "reported_input_net_debt";

// V3.7.4 Shareholder Returns share-count treatment labels.
const SHARE_COUNT_TREATMENT_LABELS = {
  current_reported_shares: "Current Reported Diluted Shares",
  forecast_ending_diluted_shares: "Forecast Ending Diluted Shares",
  forecast_weighted_avg_diluted_shares: "Forecast Weighted Avg Diluted Shares",
};
const DEFAULT_SHARE_COUNT_TREATMENT = "current_reported_shares";

// V3.7.5 WACC treatment labels.
const WACC_TREATMENT_LABELS = {
  selected_model_wacc: "Selected / Model WACC",
  capm_indicative_wacc: "CAPM Indicative WACC",
  selected_plus_spread_100bps: "Selected WACC + 100 bps",
  selected_minus_spread_100bps: "Selected WACC - 100 bps",
};
const DEFAULT_WACC_TREATMENT = "selected_model_wacc";

// V3.7.6 Terminal Value treatment labels.
const TERMINAL_TREATMENT_LABELS = {
  current_model_terminal: "Current Model Terminal Value",
  gordon_growth: "Gordon Growth Terminal Value",
  exit_multiple: "Exit Multiple Terminal Value",
  gordon_exit_blend: "Gordon / Exit Blend",
  fade_period_reference: "Fade Period Reference Case",
};
const DEFAULT_TERMINAL_TREATMENT = "current_model_terminal";

let moneyState = {};

// 渐进式 loading 提示用的 timer
let _loadingTimers = [];

// ── 单位转换 ──────────────────────────────────────────────────────────────────

function displayValue(valueInMillions, unit) {
  if (valueInMillions == null) return "";
  const mul = UNIT_MULTIPLIERS[unit] || 1.0;
  const v   = valueInMillions / mul;
  const decimals = unit === "actual" ? 0 : (unit === "yi" ? 4 : 2);
  return Number(v.toFixed(decimals));
}

function parseValue(displayedValue, unit) {
  if (displayedValue === "" || displayedValue == null) return 0;
  const mul = UNIT_MULTIPLIERS[unit] || 1.0;
  return Number(displayedValue) * mul;
}

function unitLabel(unit, currency) {
  const zh = {
    actual: "", thousands: "千", millions: "百万", yi: "亿", billions: "十亿",
  }[unit] || "";
  return `${zh} ${currency}`.trim();
}

function defaultUnitForCurrency(ccy) {
  if (ccy === "CNY") return "yi";
  return "millions";
}

// ── 渐进式加载提示 ────────────────────────────────────────────────────────────

function _isSlowMarket(sym) {
  if (!sym) return false;
  const s = sym.toUpperCase();
  return s.endsWith(".HK") || s.endsWith(".SS") || s.endsWith(".SZ");
}

function _setupProgressiveLoading(symbol) {
  _clearLoadingTimers();
  const section = document.getElementById("loading-section");
  if (!section) return;

  // 默认初始文案
  section.innerHTML = `
    <div class="card" style="text-align:center;padding:40px;">
      <div class="skeleton" style="width:40%;height:24px;margin:0 auto 12px;"></div>
      <div style="font-size:13px;color:var(--text-muted);" id="loading-msg">
        正在加载 ${escapeHtml(symbol)} 数据…
      </div>
    </div>`;

  if (!_isSlowMarket(symbol)) return;   // 美股秒返

  const t1 = setTimeout(() => {
    const msg = document.getElementById("loading-msg");
    if (msg) msg.textContent = "正在抓取财报数据…（港股/A 股首次较慢）";
  }, 3000);

  const t2 = setTimeout(() => {
    const msg = document.getElementById("loading-msg");
    if (msg) msg.innerHTML = "首次抓取财报需 1-3 分钟（港股/A 股），<br>完成后会本地缓存，下次秒开。";
  }, 30000);

  _loadingTimers = [t1, t2];
}

function _clearLoadingTimers() {
  _loadingTimers.forEach(t => clearTimeout(t));
  _loadingTimers = [];
}

async function _loadBaseCache(symbol) {
  try {
    const defaultsRes = await fetch(`${API}/api/modeling/dcf?symbol=${encodeURIComponent(symbol)}`);
    const defaultsData = await defaultsRes.json();
    if (defaultsData.error) throw new Error(defaultsData.error);
    const baseParams = defaultsData.defaults;

    const postRes = await fetch(`${API}/api/modeling/dcf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(baseParams),
    });
    const result = await postRes.json();
    if (result.error) throw new Error(result.error);

    _baseCache = {
      params: baseParams,
      intrinsic_per_share: result.intrinsic_per_share,
      currency: result.currency || baseParams.currency,
    };
  } catch (err) {
    console.warn("[v3.4.6] base cache load failed:", err);
    _baseCache = null;
  }
}

// ── 页面初始化 ────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  if (IS_SCENARIO_PAGE) {
    const thesisCard = document.getElementById("thesis-card");
    if (thesisCard) thesisCard.style.display = "none";
    const saveRow = document.getElementById("scenario-save-row");
    if (saveRow) saveRow.style.display = "block";
  }

  const params = new URLSearchParams(window.location.search);
  const symbol = params.get("symbol");
  if (!symbol) {
    document.getElementById("landing-section").style.display = "block";
  } else {
    document.title = `DCF — ${symbol.toUpperCase()}`;
    loadDefaults(symbol.toUpperCase());
  }
});

function goValuate() {
  const val = document.getElementById("landing-input").value.trim().toUpperCase();
  if (!val) return;
  window.location.href = `/modeling/dcf/select?symbol=${val}`;
}

// ── 拉取默认值 ────────────────────────────────────────────────────────────────

async function loadDefaults(symbol) {
  document.getElementById("loading-section").style.display = "block";
  _setupProgressiveLoading(symbol);

  try {
    let loadedDefaults = null;

    if (IS_SCENARIO_PAGE) {
      const scenarioPromise = fetch(`${API}/api/modeling/dcf/scenario/${encodeURIComponent(symbol)}/${SCENARIO}`);
      const [res] = await Promise.all([scenarioPromise, _loadBaseCache(symbol)]);
      if (!res.ok) {
        window.location.href = `/modeling/dcf/select?symbol=${encodeURIComponent(symbol)}`;
        return;
      }
      const entry = await res.json();
      if (entry.error) throw new Error(entry.error);
      _scenarioUpdatedAt = entry.updated_at || null;
      _scenarioCompatibility = entry.compatibility || {};
      loadedDefaults = {
        ...entry.params,
        currency: entry.params.currency || entry.valuation?.currency || "USD",
        company: entry.params.company || entry.params.symbol || symbol,
        price: entry.params.price || 0,
        market: entry.params.market || "SAVED",
        data_source: entry.params.data_source || "Saved Scenario",
      };
    } else {
      _scenarioCompatibility = {};
      const res  = await fetch(`${API}/api/modeling/dcf?symbol=${symbol}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      loadedDefaults = data.defaults;
    }

    _clearLoadingTimers();

    currentDefaults = loadedDefaults;

    displayUnit = defaultUnitForCurrency(currentDefaults.currency);
    document.getElementById("unit-select").value = displayUnit;

    moneyState = {
      revenue   : currentDefaults.revenue   || 0,
      ebit      : currentDefaults.ebit      || 0,
      da        : currentDefaults.da        || 0,
      capex     : currentDefaults.capex     || 0,
      wc_change : currentDefaults.wc_change || 0,
      net_debt  : currentDefaults.net_debt  || 0,
    };

    fillForm(currentDefaults);
    _renderScenarioBar();
    updateUnitLabels();

    document.getElementById("loading-section").style.display = "none";
    document.getElementById("dcf-main").style.display        = "grid";

    await recalc(true);

  } catch (err) {
    _clearLoadingTimers();
    document.getElementById("loading-section").innerHTML =
      `<div class="card" style="color:var(--red);">⚠ 数据加载失败：${err.message}</div>`;
  }
}

// ── 填表 ──────────────────────────────────────────────────────────────────────

function fillForm(d) {
  document.getElementById("info-symbol").textContent = d.symbol;
  document.getElementById("info-name").textContent   = d.company;
  document.getElementById("info-price").textContent  = `${fmtNum(d.price, 3)} ${d.currency}`;
  document.getElementById("info-market").textContent = `${d.market} / ${d.currency}`;

  document.getElementById("src-name").textContent = d.data_source || "数据源";
  renderExitMultipleSource(d);
  renderDefaultQualityBanner(d);
  renderNormalizedEbitReviewCard(d);

  const revenue = Number(d.revenue || 0);
  const ratio = (num, den) => den ? Number(num || 0) / den : 0;
  const revenueGrowth = d.revenue_growth ?? d.fcf_growth ?? 0.03;
  const ebitMargin = d.ebit_margin ?? ratio(d.ebit, revenue);
  const daPctRevenue = d.da_pct_revenue ?? ratio(d.da, revenue);
  const capexPctRevenue = d.capex_pct_revenue ?? ratio(d.capex, revenue);
  const wcChangePctRevenue = d.wc_change_pct_revenue ?? ratio(d.wc_change, revenue);

  setInput("p-years",         d.forecast_years);
  setInput("p-fcf-growth",    revenueGrowth * 100, 4);
  setInput("p-revenue-growth", revenueGrowth * 100, 4);
  setInput("p-ebit-margin", ebitMargin * 100, 4);
  setInput("p-da-pct-revenue", daPctRevenue * 100, 4);
  setInput("p-capex-pct-revenue", capexPctRevenue * 100, 4);
  setInput("p-wc-change-pct-revenue", wcChangePctRevenue * 100, 4);
  // V3.9.0 Forecast Path Upgrade v1: seed the advanced 5-year path editor.
  // Defaults to flat expansion of the single-value driver so headline IV is
  // unchanged unless the analyst tilts a row.
  renderForecastPathEditor(d, {
    revenue_growth: revenueGrowth,
    ebit_margin: ebitMargin,
    da_pct_revenue: daPctRevenue,
    capex_pct_revenue: capexPctRevenue,
    wc_change_pct_revenue: wcChangePctRevenue,
  });

  setInput("p-terminal-g",    d.terminal_g * 100, 4);
  setInput("p-wacc",          d.wacc * 100, 4);
  setInput("p-exit-multiple", d.exit_multiple, 4);

  refreshMoneyInputs();

  setInput("f-tax-rate", d.tax_rate * 100, 4);
  setInput("f-shares",   d.shares);

  setTVMethod(d.tv_method || "average");

  // V3.7.3: seed Net Debt Treatment from defaults / saved scenario; unknown
  // keys fall back to reported_input_net_debt so the UI never sits on a
  // value the API would reject.
  const treatmentSel = document.getElementById("p-net-debt-treatment");
  if (treatmentSel) {
    const tk = d.selected_net_debt_treatment;
    treatmentSel.value = (tk && NET_DEBT_TREATMENT_LABELS[tk]) ? tk : DEFAULT_NET_DEBT_TREATMENT;
  }

  // V3.7.4: seed Share Count Treatment + shareholder return drivers.
  const scSel = document.getElementById("p-share-count-treatment");
  if (scSel) {
    const sk = d.selected_share_count_treatment;
    scSel.value = (sk && SHARE_COUNT_TREATMENT_LABELS[sk]) ? sk : DEFAULT_SHARE_COUNT_TREATMENT;
  }
  if (d.dividend_payout_pct_net_income != null) setInput("p-dividend-payout", d.dividend_payout_pct_net_income * 100, 4);
  if (d.buyback_pct_fcf != null) setInput("p-buyback-pct-fcf", d.buyback_pct_fcf * 100, 4);
  if (d.annual_dilution_pct != null) setInput("p-annual-dilution", d.annual_dilution_pct * 100, 4);

  // V3.7.5: seed WACC Treatment from defaults / saved scenario.
  const waccSel = document.getElementById("p-wacc-treatment");
  if (waccSel) {
    const wk = d.selected_wacc_treatment;
    waccSel.value = (wk && WACC_TREATMENT_LABELS[wk]) ? wk : DEFAULT_WACC_TREATMENT;
  }

  // V3.7.6: seed Terminal Treatment from defaults / saved scenario.
  const termSel = document.getElementById("p-terminal-treatment");
  if (termSel) {
    const tk = d.selected_terminal_treatment;
    termSel.value = (tk && TERMINAL_TREATMENT_LABELS[tk]) ? tk : DEFAULT_TERMINAL_TREATMENT;
  }

  // v3.2.7：金融行业 DCF 不适用警告 banner
  // 挂载在"公司信息"card 之后、"假设参数"card 之前——
  // 视觉上是"看完公司是谁，立刻看到警告，再看假设参数"
  // 阻断式但不破坏布局，金融产品 credibility boundary 标准做法。

  // 先移除旧 banner（切换股票时避免重复）
  const oldBanner = document.getElementById("industry-warning-banner");
  if (oldBanner) oldBanner.remove();

  if (d.industry_warning) {
    const banner = document.createElement("div");
    banner.id = "industry-warning-banner";
    banner.style.cssText = `
      margin: 12px 0;
      padding: 12px 16px;
      background: rgba(255, 165, 0, 0.1);
      border-left: 3px solid orange;
      border-radius: 4px;
      color: var(--text-primary);
      font-size: 13px;
      line-height: 1.5;
    `;
    banner.textContent = "⚠ " + d.industry_warning.message;

    // 锚点：从 #info-market 找最近的 card，banner 插到该 card 之后
    const infoMarketEl = document.getElementById("info-market");
    if (infoMarketEl) {
      const headerCard = infoMarketEl.closest(".card");
      if (headerCard && headerCard.parentNode) {
        headerCard.parentNode.insertBefore(banner, headerCard.nextSibling);
      }
    }
  }
}

function setInput(id, val, decimals = 2) {
  const el = document.getElementById(id);
  if (el) el.value = val != null ? roundN(val, decimals) : "";
}

function renderExitMultipleSource(d) {
  const sourceHint = document.getElementById("source-hint");
  if (!sourceHint) return;
  const old = document.getElementById("exit-multiple-source-hint");
  if (old) old.remove();
  if (!d.exit_multiple_source && !d.exit_multiple_warning) return;

  const hint = document.createElement("div");
  hint.id = "exit-multiple-source-hint";
  hint.className = "field-hint";
  hint.style.marginTop = "8px";
  const source = d.exit_multiple_source || "unknown";
  const warning = d.exit_multiple_warning ? ` ${d.exit_multiple_warning}` : "";
  hint.textContent = `Exit Multiple source: ${source}.${warning}`;
  sourceHint.insertAdjacentElement("afterend", hint);
}

function renderDefaultQualityBanner(d) {
  const old = document.getElementById("default-quality-banner");
  if (old) old.remove();
  const quality = d.default_quality || {};
  if (!quality.requires_review) return;

  const banner = document.createElement("div");
  banner.id = "default-quality-banner";
  banner.style.cssText = `
    margin: 12px 0;
    padding: 12px 16px;
    background: rgba(255, 165, 0, 0.1);
    border-left: 3px solid orange;
    border-radius: 4px;
    color: var(--text-primary);
    font-size: 13px;
    line-height: 1.5;
  `;
  const issueCount = Array.isArray(quality.issues) ? quality.issues.length : 0;
  banner.textContent = `${quality.banner || "Default assumptions require review before use."} ${quality.review_tier || "Review"}${issueCount ? ` (${issueCount} flags)` : ""}`;

  const infoMarketEl = document.getElementById("info-market");
  const headerCard = infoMarketEl ? infoMarketEl.closest(".card") : null;
  if (headerCard && headerCard.parentNode) {
    headerCard.parentNode.insertBefore(banner, headerCard.nextSibling);
  }
}

function getNormalizedEbitReview(d = currentDefaults) {
  return (d && (d.normalized_ebit_review || (d.default_quality && d.default_quality.normalized_ebit_review))) || null;
}

function buildNormalizedEbitProvenance(review) {
  if (!review) return null;
  const appliedMargin = Number(review.recommended_candidate_margin);
  if (!Number.isFinite(appliedMargin)) return null;
  return {
    source: "normalized_ebit_candidate",
    basis: review.recommended_candidate_basis || "HIGH_PLUS_MEDIUM",
    reported_margin: review.reported_ebit_margin,
    applied_margin: appliedMargin,
    confidence: "MEDIUM",
    note: "Applied by user from Normalized EBIT Review Candidate",
  };
}

function translateNormalizedEbitField(field) {
  const raw = String(field || "").trim();
  const key = raw.toLowerCase().replace(/[\s-]+/g, "_");
  const labels = {
    other_income: "其他收入 / 其他收益",
    other_income_expense: "其他收入 / 其他收益",
    other_income_expense_net: "其他收入 / 其他收益",
    other_non_operating_income: "其他收入 / 其他收益",
    impairment: "减值及拨备",
    impairments: "减值及拨备",
    impairment_and_provisions: "减值及拨备",
    provisions: "减值及拨备",
    provision: "减值及拨备",
    restructuring: "重组费用",
    stock_based_compensation: "股权激励费用",
    sbc: "股权激励费用",
  };
  return labels[key] || labels[raw] || raw;
}

function renderNormalizedEbitReviewCard(d) {
  const old = document.getElementById("normalized-ebit-review-card");
  if (old) old.remove();
  const rail = document.getElementById("dcf-review-rail");
  if (rail) rail.classList.remove("has-card");
  const review = getNormalizedEbitReview(d);
  if (!review || !Array.isArray(review.adjustments) || !review.adjustments.length) return;

  const card = document.createElement("div");
  card.id = "normalized-ebit-review-card";
  card.className = "normalized-ebit-review-card";
  const fields = review.adjustments
    .map(x => translateNormalizedEbitField(x.field))
    .filter(Boolean)
    .join(" / ");
  const status = _normalizedEbitApplyMessage
    ? `<div id="normalized-ebit-apply-status" style="margin-top:8px;color:var(--green);">${_normalizedEbitApplyMessage}</div>`
    : `<div id="normalized-ebit-apply-status" style="margin-top:8px;color:var(--text-muted);"></div>`;
  card.innerHTML = `
    <div class="review-title">标准化 EBIT 复核候选</div>
    <div>公司披露 EBIT 利润率：${pct(Number(review.reported_ebit_margin || 0))}%</div>
    <div>候选标准化 EBIT 利润率：${pct(Number(review.recommended_candidate_margin || 0))}%</div>
    <div>可能调整来源：${fields}</div>
    <div class="review-muted">该候选值不会自动进入估值，除非你手动应用。</div>
    <button type="button" id="apply-normalized-ebit-candidate" class="stale-result-clear" style="margin-top:8px;color:var(--text-primary);border-color:var(--border);">
      应用候选 EBIT 利润率
    </button>
    ${status}
  `;
  if (rail) {
    rail.appendChild(card);
    rail.classList.add("has-card");
    updateNormalizedEbitReviewPosition();
    requestAnimationFrame(updateNormalizedEbitReviewPosition);
  } else {
    const infoMarketEl = document.getElementById("info-market");
    const headerCard = infoMarketEl ? infoMarketEl.closest(".card") : null;
    if (headerCard && headerCard.parentNode) {
      headerCard.parentNode.insertBefore(card, headerCard.nextSibling);
    }
  }
  const btn = document.getElementById("apply-normalized-ebit-candidate");
  if (btn) btn.onclick = applyNormalizedEbitCandidate;
}

function updateNormalizedEbitReviewPosition() {
  const rail = document.getElementById("dcf-review-rail");
  const main = document.getElementById("dcf-main");
  if (!rail || !main || !rail.classList.contains("has-card")) return;
  const top = Math.max(72, Math.round(main.getBoundingClientRect().top));
  document.documentElement.style.setProperty("--dcf-review-top", `${top}px`);
}

function applyNormalizedEbitCandidate() {
  const review = getNormalizedEbitReview();
  if (!review) return;
  const margin = Number(review.recommended_candidate_margin);
  if (!Number.isFinite(margin)) return;
  setInput("p-ebit-margin", margin * 100, 4);
  markOperatingOverride("ebit_margin");
  _assumptionProvenance.ebit_margin = buildNormalizedEbitProvenance(review);
  _normalizedEbitApplyMessage = `已使用标准化 EBIT 候选值：${pct(margin)}%。`;
  const status = document.getElementById("normalized-ebit-apply-status");
  if (status) {
    status.textContent = _normalizedEbitApplyMessage;
    status.style.color = "var(--green)";
  }
  recalc(true);
}

function refreshMoneyInputs() {
  MONEY_FIELDS.forEach(([elId, key]) => {
    const el = document.getElementById(elId);
    if (el) el.value = displayValue(moneyState[key], displayUnit);
  });
}

function updateUnitLabels() {
  if (!currentDefaults) return;
  const ccy   = currentDefaults.currency;
  const label = unitLabel(displayUnit, ccy);

  const finLbl = document.getElementById("fin-unit-label");
  if (finLbl) finLbl.textContent = label;

  document.querySelectorAll(".money-unit").forEach(el => {
    el.textContent = label;
  });
}

// ── 用户编辑金额字段 ─────────────────────────────────────────────────────────

function onMoneyEdit(key) {
  const elId = MONEY_FIELDS.find(([_, k]) => k === key)?.[0];
  if (!elId) return;
  const el = document.getElementById(elId);
  if (!el) return;
  const displayed = parseFloat(el.value || 0) || 0;
  moneyState[key] = parseValue(displayed, displayUnit);
  recalc();
}

// ── 单位切换 ──────────────────────────────────────────────────────────────────

function onUnitChange() {
  displayUnit = document.getElementById("unit-select").value;
  refreshMoneyInputs();
  updateUnitLabels();
  if (currentResults) {
    renderResults(currentResults, collectParams());
  }
  if (IS_SCENARIO_PAGE) _renderAssumptionDiff();
}

// ── 收集参数 ──────────────────────────────────────────────────────────────────

function collectParams() {
  if (!currentDefaults) return null;
  const revenueGrowth = pctToDecimal("p-revenue-growth");
  const ebitMargin = pctToDecimal("p-ebit-margin");
  const daPctRevenue = pctToDecimal("p-da-pct-revenue");
  const capexPctRevenue = pctToDecimal("p-capex-pct-revenue");
  const wcChangePctRevenue = pctToDecimal("p-wc-change-pct-revenue");
  const operatingSingles = {
    revenue_growth: revenueGrowth,
    ebit_margin: ebitMargin,
    da_pct_revenue: daPctRevenue,
    capex_pct_revenue: capexPctRevenue,
    wc_change_pct_revenue: wcChangePctRevenue,
  };
  const operatingOverrideKeys = Object.keys(_manualOperatingOverrides).filter(k => _manualOperatingOverrides[k]);
  return {
    symbol        : currentDefaults.symbol,
    company       : currentDefaults.company,
    price         : currentDefaults.price,
    forecast_years: intVal("p-years"),
    revenue_growth: revenueGrowth,
    ebit_margin   : ebitMargin,
    da_pct_revenue: daPctRevenue,
    capex_pct_revenue: capexPctRevenue,
    wc_change_pct_revenue: wcChangePctRevenue,

    // V3.9.0 Forecast Path Upgrade v1: emit five-year paths collected from the
    // advanced editor. When the editor has not been rendered (older view), the
    // helper returns null and we omit the field so the backend flat-expands
    // the single value above and headline IV is preserved exactly.
    ...(() => {
      const out = {};
      FORECAST_PATH_DRIVERS.forEach(([k]) => {
        const p = collectForecastPathForPayload(k, operatingSingles[k]);
        if (p && p.length === 5) out[`${k}_path`] = p;
      });
      return out;
    })(),
    wacc          : pctToDecimal("p-wacc"),
    beta          : Number(currentDefaults.beta || 1.0),
    terminal_g    : pctToDecimal("p-terminal-g"),
    exit_multiple : floatVal("p-exit-multiple"),
    exit_multiple_source: currentDefaults.exit_multiple_source,
    exit_multiple_warning: currentDefaults.exit_multiple_warning,
    default_quality: currentDefaults.default_quality || null,
    normalized_ebit_review: currentDefaults.normalized_ebit_review
      || (currentDefaults.default_quality && currentDefaults.default_quality.normalized_ebit_review)
      || null,
    assumption_provenance: _assumptionProvenance,
    warnings: currentDefaults.warnings || [],
    reporting_currency: currentDefaults.reporting_currency || currentDefaults.currency,
    reporting_currency_source: currentDefaults.reporting_currency_source || null,
    tv_method     : tvMethod,

    revenue       : moneyState.revenue   || 0,
    ebit          : moneyState.ebit      || 0,
    da            : moneyState.da        || 0,
    capex         : moneyState.capex     || 0,
    wc_change     : moneyState.wc_change || 0,
    net_debt      : moneyState.net_debt  || 0,

    tax_rate      : pctToDecimal("f-tax-rate"),
    shares        : floatVal("f-shares"),

    // V3.7.3: persisted as KEY (not label); default keeps V3.7.2 IV.
    selected_net_debt_treatment: (
      document.getElementById("p-net-debt-treatment")?.value || DEFAULT_NET_DEBT_TREATMENT
    ),

    // V3.7.4 Shareholder Returns. KEY persisted; default keeps V3.7.3 IV.
    selected_share_count_treatment: (
      document.getElementById("p-share-count-treatment")?.value || DEFAULT_SHARE_COUNT_TREATMENT
    ),
    // Optional numeric drivers; blank → null → calculator falls back to
    // historical base.
    dividend_payout_pct_net_income: _pctOrNull("p-dividend-payout"),
    buyback_pct_fcf: _pctOrNull("p-buyback-pct-fcf"),
    annual_dilution_pct: _pctOrNull("p-annual-dilution"),

    // V3.7.5 WACC treatment. KEY persisted; default keeps V3.7.4 IV.
    selected_wacc_treatment: (
      document.getElementById("p-wacc-treatment")?.value || DEFAULT_WACC_TREATMENT
    ),

    // V3.7.6 Terminal Value treatment. KEY persisted; default keeps V3.7.5 IV.
    selected_terminal_treatment: (
      document.getElementById("p-terminal-treatment")?.value || DEFAULT_TERMINAL_TREATMENT
    ),
    selected_operating_path_source: (
      document.getElementById("p-operating-path-source")?.value || currentDefaults.selected_operating_path_source || "Selected Path"
    ),
    operating_override_keys: operatingOverrideKeys,
  };
}

function _pctOrNull(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const raw = el.value;
  if (raw === "" || raw === null || raw === undefined) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n / 100 : null;
}

// ── 计算 ──────────────────────────────────────────────────────────────────────

async function recalc(immediate = false) {
  if (recalcTimer) clearTimeout(recalcTimer);

  const run = async () => {
    const params = collectParams();
    if (!params) return;
    validateInputs(params);

    try {
      const res  = await fetch(`${API}/api/modeling/dcf`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify(params),
      });
      const data = await res.json();
      if (data.error) {
        console.warn("[DCF]", data.error);
        showStaleResult(`估值计算失败: ${data.error}, 以下结果为修改前的版本`);
        return;
      }
      clearStaleResult();
      currentResults = { ...data, ...params };
      renderResults(data, params);
      _renderScenarioBar();
      _renderAssumptionDiff();
    } catch (err) {
      console.warn("[DCF recalc]", err);
      showStaleResult(`网络或脚本错误: ${err.message || err}, 以下结果为修改前的版本`);
    }
  };

  if (immediate) await run();
  else recalcTimer = setTimeout(run, 300);
}

// ── 异常值警告 ────────────────────────────────────────────────────────────────

function showStaleResult(message) {
  const panel = document.getElementById("results-panel");
  if (!panel) return;
  panel.classList.add("stale-result");
  let banner = document.getElementById("stale-result-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "stale-result-banner";
    banner.className = "stale-result-banner";
    const text = document.createElement("span");
    text.className = "stale-result-message";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "stale-result-clear";
    btn.textContent = "清除";
    btn.onclick = clearStaleResult;
    banner.appendChild(text);
    banner.appendChild(btn);
    panel.insertBefore(banner, panel.firstChild);
  }
  banner.querySelector(".stale-result-message").textContent = message;
}

function clearStaleResult() {
  const panel = document.getElementById("results-panel");
  panel?.classList.remove("stale-result");
  document.getElementById("stale-result-banner")?.remove();
}

function validateInputs(p) {
  toggleWarn("warn-g",          p.terminal_g > 0.04, "⚠ 高于发达市场长期 GDP，偏激进");
  toggleWarn("warn-wacc",       p.wacc < 0.05,       "⚠ 低于一般折现率水平，请确认");
  toggleWarn("warn-revenue-growth", p.revenue_growth > 0.40, "Revenue growth exceeds 40%; please review.");
}

function toggleWarn(id, show, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent   = msg;
  el.style.display = show ? "block" : "none";
}

// ── 渲染结果 ──────────────────────────────────────────────────────────────────

function renderResults(r, p) {
  const ccy = r.currency || (currentDefaults && currentDefaults.currency) || "USD";
  renderModelSuitability(r);
  if (r.model_unsuitable || r.model_status === "unsuitable" || r.valuation_status === "model_unsuitable") {
    document.getElementById("r-intrinsic").textContent = "N/M";
    document.getElementById("r-intrinsic").className = "intrinsic-value mono down";
    document.getElementById("r-upside").textContent = "N/M";
    document.getElementById("r-upside").className = "intrinsic-upside down";
    document.getElementById("r-vs").textContent = r.model_unsuitable_reason || "DCF unavailable for this security type";
    clearValuationDetailTables();
    return;
  }

  const ivEl = document.getElementById("r-intrinsic");
  ivEl.textContent = `${fmtNum(r.intrinsic_per_share, 2)} ${ccy}`;
  ivEl.className   = "intrinsic-value mono " + (r.upside_pct >= 0 ? "up" : "down");

  const upEl = document.getElementById("r-upside");
  const sign = r.upside_pct >= 0 ? "+" : "";
  upEl.textContent = `${sign}${r.upside_pct.toFixed(1)}%`;
  upEl.className   = "intrinsic-upside " + (r.upside_pct >= 0 ? "up" : "down");

  document.getElementById("r-vs").textContent =
    `当前股价 ${fmtNum(p.price, 2)} ${ccy} · ${r.upside_pct >= 0 ? "低估" : "高估"} ${Math.abs(r.upside_pct).toFixed(1)}%`;

  const tvWarn = document.getElementById("warn-tv-pct");
  if (r.tv_pct > 80) {
    tvWarn.textContent  = `⚠ 终值占比 ${r.tv_pct}%，建议延长预测期`;
    tvWarn.style.display = "block";
  } else {
    tvWarn.style.display = "none";
  }

  renderFCFTable(r, p, ccy);
  renderBridgeTable(r, p, ccy);
  renderWaccBridge(r, p);
  renderTerminalSanity(r);
  renderOperatingSensitivity(r, p);

  renderSensitivity("sens-gordon", r.sensitivity_gordon,
    [0,1,2,3,4].map(j => `g=${pct(p.terminal_g + (j-2)*0.005)}%`),
    [0,1,2,3,4].map(i => `WACC=${pct(p.wacc + (i-2)*0.005)}%`),
    p.price);

  renderSensitivity("sens-exit", r.sensitivity_exit,
    [0,1,2,3,4].map(j => `${(p.exit_multiple + (j-2)*1.0).toFixed(1)}×`),
    [0,1,2,3,4].map(i => `WACC=${pct(p.wacc + (i-2)*0.005)}%`),
    p.price);
}

function clearValuationDetailTables() {
  [
    "fcf-head",
    "fcf-body",
    "bridge-table",
    "wacc-bridge-table",
    "terminal-sanity-table",
    "sens-gordon",
    "sens-exit",
    "sens-operating",
  ].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = "";
  });
}

function renderModelSuitability(r) {
  const box = document.getElementById("model-suitability-warning");
  if (!box) return;
  const blocked = !!(r && (r.model_unsuitable || r.model_status === "unsuitable" || r.valuation_status === "model_unsuitable"));
  box.style.display = blocked ? "block" : "none";
  if (!blocked) return;
  const securityType = r.security_type || "ETF / index / fund";
  const reason = r.model_unsuitable_reason || `This ticker appears to be a ${securityType}. DCF is designed for operating companies.`;
  const methods = Array.isArray(r.recommended_methods) ? r.recommended_methods : [];
  const messageEl = document.getElementById("model-suitability-message");
  const methodsEl = document.getElementById("model-suitability-methods");
  if (messageEl) messageEl.textContent = reason;
  if (methodsEl) methodsEl.textContent = methods.length ? `Recommended methods: ${methods.join(", ")}` : "";
}

function renderOperatingSensitivity(r, p) {
  renderSensitivity("sens-operating", r.sensitivity_operating,
    [0,1,2,3,4].map(j => `Rev ${pct(p.revenue_growth + (j-2)*0.01)}%`),
    [0,1,2,3,4].map(i => `EBIT ${pct(p.ebit_margin + (i-2)*0.01)}%`),
    p.price);
}

function renderFCFTable(r, p, ccy) {
  const head = document.getElementById("fcf-head");
  const body = document.getElementById("fcf-body");
  const n    = r.forecast_years || 5;
  const lbl  = unitLabel(displayUnit, ccy);

  head.innerHTML = `<th style="text-align:left;color:var(--text-muted);">（${lbl}）</th>` +
    Array.from({length: n}, (_, i) => `<th>Year ${i+1}</th>`).join("");

  const sources = r.active_forecast_sources || r.audit?.active_forecast_sources || {};
  const sourceSuffix = key => sources[key] ? ` (${sources[key]})` : "";
  const rows = [
    ["Revenue", r.revenue_projections, false, true ],
    ["EBIT", r.ebit_projections, false, true ],
    ["NOPAT", r.nopat_projections, false, true ],
    [`D&A${sourceSuffix("da")}`, r.da_projections, false, true ],
    [`CapEx${sourceSuffix("capex")}`, r.capex_projections, false, true ],
    [`Delta NWC${sourceSuffix("delta_nwc")}`, r.delta_nwc_projections, false, true ],
    ["FCF", r.fcf_projections, false, true ],
    ["Discount Factor", r.discount_factors, true, false],
    ["PV of FCF", r.pv_fcfs, false, true ],
  ];

  body.innerHTML = rows.map(([label, vals, isDF, isMoney]) => {
    const cells = (vals || []).map(v => {
      if (isDF) return `<td class="mono">${v.toFixed(4)}</td>`;
      const shown = isMoney ? displayValue(v, displayUnit) : v;
      return `<td class="mono">${fmtComma(shown)}</td>`;
    }).join("");
    return `<tr><td style="color:var(--text-muted);">${label}</td>${cells}</tr>`;
  }).join("");
}

function renderBridgeTable(r, p, ccy) {
  const lbl = unitLabel(displayUnit, ccy);
  const fmt = v => `${fmtComma(displayValue(v, displayUnit))} ${lbl}`;

  const rows = [
    ["显性期 FCF 现值合计",        fmt(r.pv_fcf_sum),  false],
    ["终值（Gordon，折现）",      fmt(r.tv_gordon),    false],
    ["终值（Exit，折现）",        fmt(r.tv_exit),      false],
    [`终值（采用：${p.tv_method}）`, fmt(r.tv_used),   false],
    ["企业价值 EV",                fmt(r.ev),           true ],
    ["减：净债务",                 fmt(-p.net_debt),    false],
    ["股权价值",                   fmt(r.equity_value), false],
    ["每股内在价值",
      `${fmtNum(r.intrinsic_per_share, 2)} ${ccy}`,    true ],
  ];

  document.getElementById("bridge-table").innerHTML = rows.map(([l, v, bold]) => {
    const cls = bold ? "bridge-total" : "";
    return `<tr class="${cls}"><td>${l}</td><td class="mono">${v}</td></tr>`;
  }).join("");
}

function renderWaccBridge(r, p) {
  const wc = r.wacc_components || {};
  const beta = wc.beta ?? p.beta ?? 1.0;
  const rf = wc.rf ?? 0;
  const erp = wc.erp ?? 0;
  const rows = [
    ["Risk-free Rate (rf)", pct(rf) + "%"],
    ["Equity Risk Premium (erp)", pct(erp) + "%"],
    ["Beta", fmtNum(beta, 2)],
    ["Implied Cost of Equity", pct(wc.cost_of_equity ?? (rf + beta * erp)) + "%"],
    ["Selected / Model WACC", pct(wc.wacc ?? p.wacc) + "%"],
  ];

  const table = document.getElementById("wacc-bridge-table");
  if (!table) return;
  table.innerHTML = rows.map(([label, value], idx) => {
    const cls = idx === rows.length - 1 ? "bridge-total" : "";
    return `<tr class="${cls}"><td>${label}</td><td class="mono">${value}</td></tr>`;
  }).join("");
}

function renderTerminalSanity(r) {
  const sanity = r.terminal_sanity || {};
  const thresholds = sanity.thresholds || {};
  const checks = [
    {
      label: "TV dependency",
      flag: !!sanity.tv_dependency_high,
      detail: `TV / EV ${fmtNum(r.tv_pct, 1)}% vs ${pct(thresholds.tv_dependency ?? 0.75)}%`,
    },
    {
      label: "Gordon spread",
      flag: !!sanity.gordon_unstable,
      detail: `WACC - g ${pct(sanity.gordon_spread ?? 0)}% vs ${pct(thresholds.gordon_spread ?? 0.01)}%`,
    },
    {
      label: "Terminal method gap",
      flag: !!sanity.method_divergence_high,
      detail: `Gordon vs Exit gap ${pct(sanity.method_diff ?? 0)}% vs ${pct(thresholds.method_diff ?? 0.25)}%`,
    },
  ];

  const table = document.getElementById("terminal-sanity-table");
  if (!table) return;
  table.innerHTML = checks.map(item => {
    const status = item.flag ? "Review" : "OK";
    const color = item.flag ? "var(--red)" : "var(--green)";
    return `<tr><td>${item.label}</td><td class="mono" style="color:${color};font-weight:700;">${status}</td><td class="mono">${item.detail}</td></tr>`;
  }).join("");
}

function renderSensitivity(tableId, matrix, colLabels, rowLabels, curPrice) {
  const tbl = document.getElementById(tableId);
  if (!matrix) { tbl.innerHTML = ""; return; }

  const head = `<tr><th>\\</th>${colLabels.map(c => `<th>${c}</th>`).join("")}</tr>`;
  const body = matrix.map((row, i) =>
    `<tr><th>${rowLabels[i]}</th>` +
    row.map((val, j) => {
      const isCenter = i === 2 && j === 2;
      let cls = isCenter ? "sens-highlight" : "";
      if (!isCenter) {
        if (val > curPrice * 1.10) cls = "sens-cheap";
        else if (val < curPrice * 0.90) cls = "sens-pricy";
      }
      return `<td class="${cls}">${fmtNum(val, 1)}</td>`;
    }).join("") +
    `</tr>`
  ).join("");

  tbl.innerHTML = head + body;
}

// ── 终值方法 / 导出 ──────────────────────────────────────────────────────────

function setTVMethod(val) {
  tvMethod = val;
  document.querySelectorAll(".tv-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.val === val);
  });
  recalc();
}

function _renderScenarioBar() {
  if (!IS_SCENARIO_PAGE) return;

  const bar = document.getElementById("scenario-context-bar");
  if (!bar) return;

  const symbol = currentDefaults?.symbol || new URLSearchParams(location.search).get("symbol") || "";

  if (IS_BASE) {
    bar.innerHTML = `
      <div style="background:rgba(56,139,253,0.06);border-left:3px solid var(--border);padding:10px 16px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <strong style="font-size:14px;color:var(--text-muted);">Base / 默认 DCF</strong>
        <a href="/modeling/dcf/select?symbol=${encodeURIComponent(symbol)}" style="font-size:12px;color:var(--accent);">返回 DCF 版本选择</a>
      </div>
    `;
    bar.style.display = "block";
    return;
  }

  if (!IS_SCENARIO_PAGE) return;

  const label = IS_BULL ? "Bull / 乐观情景 DCF" : "Bear / 悲观情景 DCF";
  bar.innerHTML = `
    <div style="background:rgba(56,139,253,0.1);border-left:3px solid var(--accent);padding:10px 16px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;gap:12px;">
      <strong style="font-size:14px;color:var(--accent);">${label}</strong>
      <a href="/modeling/dcf/select?symbol=${encodeURIComponent(symbol)}" style="font-size:12px;color:var(--accent);">返回 DCF 版本选择</a>
    </div>
  `;
  bar.style.display = "block";
}

function _renderScenarioBarV346() {
  if (!IS_SCENARIO_PAGE) return;

  const bar = document.getElementById("scenario-context-bar");
  if (!bar) return;

  const symbol = currentDefaults?.symbol || new URLSearchParams(location.search).get("symbol") || "";
  const label = IS_BULL ? "Bull / 乐观情景 DCF" : "Bear / 悲观情景 DCF";
  const curIntrinsic = currentResults?.intrinsic_per_share;
  const ccy = currentResults?.currency || currentDefaults?.currency || "";

  let vsBaseStr = "—";
  let relationWarning = "";
  if (_baseCache && _baseCache.intrinsic_per_share && curIntrinsic != null) {
    const pct = (curIntrinsic - _baseCache.intrinsic_per_share) / _baseCache.intrinsic_per_share * 100;
    const sign = pct >= 0 ? "+" : "";
    vsBaseStr = `${sign}${pct.toFixed(1)}% vs Base`;
    if (IS_BULL && curIntrinsic < _baseCache.intrinsic_per_share) {
      relationWarning = "Bull valuation is below Base. Review saved assumptions before using this scenario.";
    }
    if (IS_BEAR && curIntrinsic > _baseCache.intrinsic_per_share) {
      relationWarning = "Bear valuation is above Base. Review saved assumptions before using this scenario.";
    }
  }
  if (_scenarioCompatibility.legacy_fcf_growth_mapped) {
    relationWarning = relationWarning
      ? `${relationWarning} Legacy fcf_growth was mapped to Revenue Growth.`
      : "Legacy fcf_growth was mapped to Revenue Growth for this saved scenario.";
  }
  if (_scenarioLooksStale(currentDefaults, _baseCache?.params)) {
    relationWarning = relationWarning
      ? `${relationWarning} Saved financial inputs differ from current Base defaults.`
      : "Saved financial inputs differ from current Base defaults; treat this as a saved reference until refreshed.";
  }

  const intrinsicStr = curIntrinsic != null ? `${fmtNum(curIntrinsic, 2)} ${ccy}` : "--";
  const savedStr = _scenarioUpdatedAt ? `最近保存 ${_formatTime(_scenarioUpdatedAt)}` : "未保存";

  bar.innerHTML = `
    <div style="background:rgba(56,139,253,0.1);border-left:3px solid var(--accent);padding:10px 16px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <strong style="font-size:14px;color:var(--accent);">${label}</strong>
        <a href="/modeling/dcf/select?symbol=${encodeURIComponent(symbol)}" style="font-size:12px;color:var(--accent);">← 返回 DCF 版本选择</a>
      </div>
      <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-family:'Consolas',monospace;">
        ${intrinsicStr} · ${vsBaseStr} · ${savedStr}
      </div>
      ${relationWarning ? `<div style="font-size:12px;color:var(--gold);margin-top:6px;line-height:1.45;">${relationWarning}</div>` : ""}
    </div>
  `;
  bar.style.display = "block";
}

function _renderAssumptionDiff() {
  if (!IS_SCENARIO_PAGE) return;

  const card = document.getElementById("assumption-diff-card");
  const table = document.getElementById("assumption-diff-table");
  if (!card || !table) return;

  if (!_baseCache || !_baseCache.params) {
    table.innerHTML = `<tr><td style="color:var(--text-muted);">Base 数据加载失败，无法对比</td></tr>`;
    card.style.display = "block";
    return;
  }

  const scenarioParams = collectParams();
  if (!scenarioParams) return;
  const baseParams = _baseCache.params;

  const fmt = (val, type) => {
    if (type === "pct") return (Number(val) * 100).toFixed(2) + "%";
    if (type === "x") return Number(val).toFixed(1) + "×";
    return val;
  };

  const rows = [];
  for (const [key, label, type] of DIFF_FIELDS) {
    // V3.7.3: Net Debt Treatment is a string assumption, not a number.
    if (type === "label") {
      const baseKey = baseParams[key] || DEFAULT_NET_DEBT_TREATMENT;
      const scnKey = scenarioParams[key] || DEFAULT_NET_DEBT_TREATMENT;
      if (baseKey === scnKey) continue;
      const baseStr = NET_DEBT_TREATMENT_LABELS[baseKey] || baseKey;
      const scnStr = NET_DEBT_TREATMENT_LABELS[scnKey] || scnKey;
      rows.push(`<tr><td>${label}</td><td>${baseStr}</td><td>${scnStr}</td><td>—</td></tr>`);
      continue;
    }
    const baseVal = Number(baseParams[key]);
    const scnVal = Number(scenarioParams[key]);
    if (!Number.isFinite(baseVal) || !Number.isFinite(scnVal)) continue;
    if (Math.abs(baseVal - scnVal) < 1e-9) continue;

    let baseStr;
    let scnStr;
    let diffStr;
    const isMoney = ["price", "revenue", "ebit", "da", "capex", "wc_change", "net_debt"].includes(key);

    if (type === "raw" && isMoney) {
      baseStr = fmtComma(displayValue(baseVal, displayUnit));
      scnStr = fmtComma(displayValue(scnVal, displayUnit));
      const d = displayValue(scnVal - baseVal, displayUnit);
      diffStr = (d >= 0 ? "+" : "") + fmtComma(d);
    } else if (type === "raw") {
      baseStr = fmtComma(baseVal);
      scnStr = fmtComma(scnVal);
      diffStr = (scnVal - baseVal >= 0 ? "+" : "") + fmtComma(scnVal - baseVal);
    } else {
      baseStr = fmt(baseVal, type);
      scnStr = fmt(scnVal, type);
      const rawDiff = scnVal - baseVal;
      if (type === "pct") diffStr = (rawDiff >= 0 ? "+" : "") + (rawDiff * 100).toFixed(2) + "%";
      if (type === "x") diffStr = (rawDiff >= 0 ? "+" : "") + rawDiff.toFixed(1) + "×";
    }

    rows.push(`<tr><td>${ASSUMPTION_LABELS[key] || label}</td><td class="mono">${baseStr}</td><td class="mono">${scnStr}</td><td class="mono">${diffStr}</td></tr>`);
  }

  const notes = [];
  if (_scenarioCompatibility.legacy_fcf_growth_mapped) {
    notes.push(`<tr><td colspan="4" style="color:var(--text-muted);font-size:11px;">Note: this scenario uses an older saved field; Revenue Growth was mapped from fcf_growth for display and calculation.</td></tr>`);
  }

  if (rows.length === 0) {
    table.innerHTML = `<tr><td style="color:var(--text-muted);">当前情景与 Base 关键假设一致</td></tr>` + notes.join("");
  } else {
    table.innerHTML =
      `<tr><td style="color:var(--text-muted);">假设 / Assumption</td>` +
      `<td style="color:var(--text-muted);text-align:right;">Base</td>` +
      `<td style="color:var(--text-muted);text-align:right;">Scenario</td>` +
      `<td style="color:var(--text-muted);text-align:right;">Difference</td></tr>` +
      rows.join("") +
      notes.join("");
  }
  card.style.display = "block";
}

function _formatTime(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "--";
    const p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  } catch {
    return "--";
  }
}

_renderScenarioBar = _renderScenarioBarV346;

function _scenarioLooksStale(scenarioParams, baseParams) {
  if (!scenarioParams || !baseParams) return false;
  const keys = ["revenue", "ebit", "da", "capex", "wc_change", "tax_rate", "net_debt", "shares", "price"];
  return keys.some(key => {
    const a = Number(scenarioParams[key]);
    const b = Number(baseParams[key]);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
    const scale = Math.max(1, Math.abs(a), Math.abs(b));
    return Math.abs(a - b) / scale > 0.001;
  });
}

function _setSaveStatus(message, type) {
  const el = document.getElementById("scenario-save-status");
  if (!el) return;
  el.textContent = message || "";
  el.style.color = type === "error"
    ? "var(--red)"
    : (type === "saved" ? "var(--green)" : "var(--text-muted)");
}

async function saveCurrentScenario() {
  if (!IS_SCENARIO_PAGE) return;

  const params = scenarioParamsForSave(collectParams());
  if (!params) return;

  const valuation = {
    intrinsic_per_share: currentResults?.intrinsic_per_share,
    currency: currentResults?.currency,
    ev: currentResults?.ev,
    equity_value: currentResults?.equity_value,
    tv_pct: currentResults?.tv_pct,
  };

  if (valuation.intrinsic_per_share == null) {
    _setSaveStatus("请先计算估值", "error");
    return;
  }

  _setSaveStatus("保存中...", "");

  try {
    const res = await fetch(`${API}/api/modeling/dcf/scenario/${encodeURIComponent(params.symbol)}/${SCENARIO}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        params,
        valuation,
        origin: { source: "scenario_page_save" },
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    _scenarioUpdatedAt = data.updated_at || new Date().toISOString();
    _renderScenarioBar();
    _setSaveStatus("已保存", "saved");
    setTimeout(() => _setSaveStatus("", ""), 2000);
  } catch (err) {
    _setSaveStatus("保存失败：" + err.message, "error");
  }
}

function scenarioParamsForSave(params) {
  if (!params) return null;
  const cleaned = { ...params };
  delete cleaned.fcf_growth;
  delete cleaned._legacy_fcf_growth_mapped;
  return cleaned;
}

async function deleteCurrentScenario() {
  if (!IS_SCENARIO_PAGE) return;

  const label = IS_BULL ? "Bull / 乐观情景 DCF" : "Bear / 悲观情景 DCF";
  if (!confirm(`确定删除 ${label}？删除后选择层将恢复为未创建状态。`)) return;

  const symbol = currentDefaults.symbol;
  try {
    const res = await fetch(`${API}/api/modeling/dcf/scenario/${encodeURIComponent(symbol)}/${SCENARIO}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    window.location.href = `/modeling/dcf/select?symbol=${encodeURIComponent(symbol)}`;
  } catch (err) {
    alert("删除失败：" + err.message);
  }
}

async function exportExcel() {
  const params = scenarioParamsForSave(collectParams());
  if (!params) return;
  params.scenario = IS_BULL ? "bull" : (IS_BEAR ? "bear" : "base");
  if (IS_SCENARIO_PAGE && _baseCache?.params) {
    params.base_params = scenarioParamsForSave(_baseCache.params);
  }
  try {
    const res = await fetch(`${API}/api/modeling/dcf/export`, {
      method : "POST",
      headers: { "Content-Type": "application/json" },
      body   : JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json();
      alert("导出失败：" + (err.error || "未知错误"));
      return;
    }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    const scenarioSuffix = IS_BULL ? "Bull" : (IS_BEAR ? "Bear" : "Base");
    a.href = url; a.download = `DCF_${params.symbol}_${scenarioSuffix}_${today()}.xlsx`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("导出失败：" + err.message);
  }
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

const floatVal = id => parseFloat(document.getElementById(id)?.value || 0) || 0;
const intVal   = id => parseInt(document.getElementById(id)?.value   || 5) || 5;
const pctToDecimal = id => floatVal(id) / 100;
const pct      = v => (v * 100).toFixed(2);
const round2   = v => typeof v === "number" ? Math.round(v * 100) / 100 : v;
const roundN   = (v, d=2) => typeof v === "number" ? Math.round(v * Math.pow(10, d)) / Math.pow(10, d) : v;
const fmtNum   = (v, d=2) => v != null ? Number(v).toFixed(d) : "--";
const fmtComma = v => v != null
  ? Number(v).toLocaleString("zh-CN", {minimumFractionDigits:2, maximumFractionDigits:2})
  : "--";
const today    = () => new Date().toISOString().slice(0, 10);
