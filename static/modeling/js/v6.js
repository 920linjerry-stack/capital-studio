// V6 Market Intelligence cockpit front end (Chinese).
//
// Read-only rendering of the deterministic, portfolio-aware event-impact
// payload from /api/modeling/v6/intelligence. No trade actions, no LLM. All
// scoring / classification / localization happens server-side in modeling/v6.

const API = "";
let activeDemo = "";        // "" = my holdings; else a demo id
let mergeSources = false;
let DATA = null;

const $ = (id) => document.getElementById(id);

function fmtSigned(n, dp = 3) {
  if (n === null || n === undefined || !isFinite(n)) return "-";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(dp)}`;
}
function fmtPct(w) {
  if (w === null || w === undefined || !isFinite(w)) return "-";
  return `${(Number(w) * 100).toFixed(1)}%`;
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function impClass(n) { return n > 1e-9 ? "pos" : n < -1e-9 ? "neg" : "mut"; }

const STATUS_CN = { bullish: "偏利好", bearish: "偏利空", neutral: "中性", mixed: "多空分歧", uncertain: "不确定" };
const CHANNEL_CN = { direct: "直接影响", second_order: "二次传导", reflexivity: "反身性 / 情绪" };
const PHASE_CN = { upcoming: "待公布", anticipation: "预期升温", live: "进行中", post_event: "影响衰减", expired: "已兑现" };
const MODE_CN = { live: "公开实时源", "live-partial": "部分实时", fixture: "示例数据", unavailable: "不可用", error: "错误" };
const MATCH_KIND_CN = { ticker: "代码命中", alias: "名称命中", macro_factor: "宏观因子", factor_tag: "主题因子", second_order: "二次传导", sector_transmission: "行业 / ETF 保守传导", reflexivity: "情绪敞口" };
// Freshness vocabulary (mirrors modeling/v6/freshness.py).
const FRESH_CN = { fresh: "新鲜", delayed: "存在延迟", stale: "陈旧", fixture: "示例回退", unknown: "时间未知", future_event_active: "未来事件", scheduled_event: "已排期" };
const FRESH_CLS = { fresh: "bullish", delayed: "mixed", stale: "bearish", fixture: "neutral", unknown: "neutral" };
const SRCMODE_CN = { live: "实时", partial_live: "部分实时", fixture_fallback: "示例回退", offline: "离线 / 未接实时源", error: "获取错误" };
const SRCMODE_CLS = { live: "bullish", partial_live: "mixed", fixture_fallback: "neutral", offline: "neutral", error: "bearish" };
// Breaking-alert vocabulary (mirrors modeling/v6/breaking.py).
const URGENCY_CN = { breaking: "突发", elevated: "升温", normal: "一般" };
const ALERT_TYPE_CN = {
  breaking_news: "突发新闻", headline_velocity: "标题密集", sentiment_shock: "情绪切换",
  macro_shock: "宏观冲击", sector_shock: "板块 / 主题", company_shock: "个股新闻流", source_failure: "数据源告警",
};
const ALERT_DIR_CN = { bullish: "偏利好", bearish: "偏利空", mixed: "多空分歧", neutral: "中性", unknown: "方向待定" };
const fmtTs = (s) => (s ? String(s).replace("T", " ").replace("Z", " UTC").replace(/(\+\d{4})$/, " $1") : "—");
const ageZh = (m) => {
  if (m === null || m === undefined) return "—";
  if (m < 60) return `${Math.round(m)} 分钟`;
  if (m < 1440) return `${(m / 60).toFixed(1)} 小时`;
  return `${(m / 1440).toFixed(1)} 天`;
};
const ETYPE_CN = {
  analyst_upgrade: "上调评级", analyst_downgrade: "下调评级", price_target_raise: "上调目标价",
  price_target_cut: "下调目标价", earnings_beat: "业绩超预期", earnings_miss: "业绩不及预期",
  guidance_raise: "上调指引", guidance_cut: "下调指引", macro_inflation_hot: "通胀走高",
  macro_inflation_cool: "通胀降温", rate_cut: "降息", rate_hike: "加息", yields_up: "收益率上行",
  yields_down: "收益率下行", regulatory_risk: "监管风险", lawsuit_investigation: "诉讼/调查",
  ai_capex_semis: "AI资本开支/半导体", risk_on: "风险偏好回升", risk_off: "风险规避",
  margin_warning: "利润率/利差压力", revenue_acceleration: "收入增长加速", revenue_slowdown: "收入增长放缓",
  estimate_raise: "上调盈利预测", estimate_cut: "下调盈利预测", fda_approval: "FDA批准", fda_rejection: "FDA拒绝",
  trial_success: "临床试验达标", trial_failure: "临床试验未达标", regulatory_approval: "监管批准",
  regulatory_rejection: "监管否决", regulatory_tightening: "监管收紧", product_recall: "产品召回",
  outage: "系统服务中断", cybersecurity_breach: "网络安全事件", jobs_hot: "就业偏强", jobs_weak: "就业偏弱",
  dollar_up: "美元走强", dollar_down: "美元走弱", oil_up: "油价上行", oil_down: "油价下行",
  credit_stress: "信用压力", bank_stress: "银行体系压力",
  fomc_decision: "FOMC决议", cpi_release: "CPI数据", jobs_report: "非农数据",
  earnings_date: "财报披露", product_launch: "新品发布", policy_announcement: "政策公告",
  uncategorized: "未分类",
};
const sCN = (s) => STATUS_CN[s] || s;
const etCN = (s) => ETYPE_CN[s] || s;
const dirCN = (d) => (d > 0 ? "利好" : d < 0 ? "利空" : "中性");
const dirBadge = (d) => (d > 0 ? "bullish" : d < 0 ? "bearish" : "neutral");

function qstr() {
  const p = new URLSearchParams();
  if (activeDemo) p.set("demo", activeDemo);
  if (mergeSources) p.set("sources", "1");
  // Cache-buster so the browser never re-serves a stale "latest" payload.
  p.set("t", Date.now().toString());
  const s = p.toString();
  return s ? `?${s}` : "";
}

function setDemo(id) { activeDemo = id; load(); }
function toggleSourceFeed() { mergeSources = !mergeSources; load(); }

async function load() {
  $("v6-body").innerHTML = `<div class="v6-loading">正在计算组合事件影响…</div>`;
  $("btn-sources").classList.toggle("active", mergeSources);
  try {
    const resp = await fetch(`${API}/api/modeling/v6/intelligence${qstr()}`, { cache: "no-store" });
    DATA = await resp.json();
    if (DATA.status === "error") throw new Error("引擎构建失败");
    render();
  } catch (e) {
    $("v6-body").innerHTML = `<div class="v6-loading">加载失败：${esc(e.message || e)}</div>`;
  }
}

let holdingSort = "impact";   // "impact" | "weight"

// Collapsible section wrapper for progressive disclosure. Open state persists
// across re-renders via a module-level set keyed by section id.
const _openSections = { themes: false, heatmap: true, feed: true, sources: false };
function toggleSection(id, el) { _openSections[id] = el.open; }
function collapse(id, title, hint, body) {
  const open = _openSections[id] ? " open" : "";
  return `<details class="v6-collapse" id="sec-${id}"${open} ontoggle="toggleSection('${id}', this)">
    <summary><span class="v6-sec-h">${title}</span>${hint ? `<span class="v6-sec-hint">${hint}</span>` : ""}<span class="v6-sec-caret">▸</span></summary>
    <div class="v6-sec-body">${body}</div>
  </details>`;
}

function render() {
  renderSelector();
  renderNotices();
  const pf = DATA.portfolio;
  // First screen = the answer: status, net read, why, key drivers, risks, what's next.
  const primary =
    renderFreshnessBanner() +
    renderStatusBar(pf) +
    renderAlerts() +
    renderSummary(pf) +
    renderNarrative(pf) +
    renderDrivers(pf) +
    renderRiskCards(pf) +
    renderTimeline(pf) +
    renderHoldings(pf);
  // Secondary = deeper analysis, tucked into collapsible panels.
  const secondary =
    collapse("heatmap", "通道影响热力图", "绿=利好 · 红=利空 · 深浅=强度 · 点击单元格查看贡献事件", renderHeatmap(pf)) +
    collapse("feed", "事件流", `${(DATA.events || []).length} 条（已去重）`, renderFeed()) +
    collapse("themes", "主题归类", "按影响强度排序", renderThemes(pf)) +
    collapse("sources", "数据源与方法", "公开来源 · 无需 API Key · 非投资建议", renderSources() + renderMethodology());
  $("v6-body").innerHTML = primary + `<div class="v6-section-title">深入分析</div>` + secondary;
  $("v6-foot").style.display = "none";   // methodology now lives in a collapsible
}

function renderMethodology() {
  return `<div class="v6-method">
    引擎为确定性规则匹配（非 LLM）。事件经关键词分类器打标，按「持仓权重 × 方向 × 强度 × 相关性 × 置信度 × 时间权重」计分并聚合；
    未来事件按预期定价提前计入、事件后按半衰期衰减，并识别「利好出尽」风险。公开来源适配器（Yahoo / Google News / SEC EDGAR / 宏观日历 / 机构标题）默认以示例 fixture 运行，可在联网时切换为公开实时源；每个来源都会如实标注 live / 部分实时 / 示例回退 / 不可用 状态。
    本视图仅为事件—持仓影响方向解读，不构成投资建议，不提供买入 / 卖出信号、目标价或止损位。
  </div>`;
}

// Freshness banner: the first thing the user sees -- can I trust "latest"?
function renderFreshnessBanner() {
  const fz = DATA.freshness || {};
  const status = fz.freshness_status || DATA.freshness_status || "unknown";
  const smode = fz.source_mode || DATA.source_mode || "fixture_fallback";
  const warn = fz.freshness_warning_zh || DATA.freshness_warning_zh || "";
  const cell = (label, value) => `<div class="v6-fresh-cell"><div class="ffl">${label}</div><div class="ffv">${value}</div></div>`;
  const stCls = FRESH_CLS[status] || "neutral";
  const smCls = SRCMODE_CLS[smode] || "neutral";
  const warnHtml = warn
    ? `<div class="v6-fresh-warn"><span class="ic">⚠</span><span>${esc(warn)}</span></div>` : "";
  return `<div class="v6-fresh">
    <div class="v6-fresh-grid">
      ${cell("数据状态", `<span class="badge ${stCls}">${esc(FRESH_CN[status] || status)}</span>`)}
      ${cell("来源模式", `<span class="badge ${smCls}">${esc(SRCMODE_CN[smode] || smode)}</span>`)}
      ${cell("生成时间", esc(fmtTs(DATA.generated_at)))}
      ${cell("最新事件时间", esc(fmtTs(fz.newest_event_published_at)))}
      ${cell("最旧事件时间", esc(fmtTs(fz.oldest_event_published_at)))}
      ${cell("数据年龄", esc(ageZh(fz.max_event_age_minutes)))}
    </div>
    ${warnHtml}
  </div>`;
}

// Breaking-news / sudden-sentiment alert cards (deterministic, news-flow only).
function renderAlerts() {
  const alerts = DATA.alerts || [];
  const sum = DATA.alert_summary || {};
  if (!alerts.length) {
    return `<div class="v6-alerts-empty">近 24 小时未检测到突发新闻流或情绪骤变信号（基于公共新闻流聚类）。</div>`;
  }
  const cards = alerts.map(a => {
    const uCls = a.urgency === "breaking" ? "breaking" : a.urgency === "elevated" ? "elevated" : "normal";
    const dir = ALERT_DIR_CN[a.dominant_direction] || a.dominant_direction;
    const dirCls = a.dominant_direction === "bullish" ? "bullish" : a.dominant_direction === "bearish" ? "bearish" : "mixed";
    const fr = a.freshness_status ? `<span class="badge ${FRESH_CLS[a.freshness_status] || "neutral"}" style="font-size:9.5px;">${esc(FRESH_CN[a.freshness_status] || a.freshness_status)}</span>` : "";
    const tks = (a.affected_tickers || []).length ? `<div class="v6-alert-tk">影响标的：${esc(a.affected_tickers.join("、"))}</div>` : "";
    const tags = (a.affected_tags || []).slice(0, 6).map(t => `<span class="badge tiny">${esc(t)}</span>`).join(" ");
    return `<div class="v6-alert ${uCls}">
      <div class="v6-alert-head">
        <span class="v6-alert-urg ${uCls}">${esc(URGENCY_CN[a.urgency] || a.urgency)}</span>
        <span class="badge tiny">${esc(ALERT_TYPE_CN[a.alert_type] || a.alert_type)}</span>
        <span class="badge ${dirCls}" style="font-size:9.5px;">${esc(dir)}</span>
        ${fr}
        <span class="v6-alert-score">强度 ${esc(a.urgency_score)}</span>
      </div>
      <div class="v6-alert-ttl">${esc(a.title_zh)}</div>
      <div class="v6-alert-sum">${esc(a.summary_zh)}</div>
      ${tks}
      ${tags ? `<div class="v6-alert-tags">${tags}</div>` : ""}
      <div class="v6-alert-meta">证据 ${esc(a.evidence_count)} 条 · 来源 ${esc(a.source_count)} 个 · 置信 ${(a.confidence * 100).toFixed(0)}%</div>
    </div>`;
  }).join("");
  const head = `<div class="v6-section-title">突发 / 情绪雷达
    <span class="cnt">${sum.breaking || 0} 突发 · ${sum.elevated || 0} 升温 · 公共新闻流聚类（近实时，可能存在延迟）</span></div>`;
  return head + `<div class="v6-alerts">${cards}</div>`;
}

function renderStatusBar(pf) {
  const gen = (DATA.generated_at || "").replace("T", " ").replace("Z", " UTC");
  const dis = Math.round((pf.disagreement || 0) * 100);
  const cov = Math.round((pf.coverage || 0) * 100);
  const sourceHealth = DATA.source_health || {};
  const sourceTotal = (DATA.sources || []).length;
  const sourceLive = sourceHealth.live_count || 0;
  const sourceMode = DATA.sources_overall_mode || "fixture";
  const sourceLabel = sourceMode === "live" ? "实时正常"
    : sourceMode === "live-partial" ? "部分实时"
    : sourceMode === "fixture" ? "示例回退"
    : sourceHealth.any_error ? "错误" : "未接实时源";
  const fresh = (DATA.bands || {}).freshness_cn || "";
  // Lean status strip: provenance only. Analytical stats live in the hero.
  return `<div class="v6-statusbar">
    <span>数据模式 ${modeBadge(DATA.sources_overall_mode || "fixture")}</span>
    <span class="sep">·</span><span>新鲜度 <b>${esc(fresh)}</b></span>
    <span class="sep">·</span><span>数据源 <b>${sourceLive}/${sourceTotal}</b> 实时 · ${sourceLabel}</span>
    <span class="sep">·</span><span>事件 <b>${DATA.event_count}</b> 条</span>
    <span class="sep">·</span><span>最后更新 ${esc(gen)}</span>
    <span class="nadv">非投资建议 · 无买卖信号</span>
  </div>`;
}

function renderSelector() {
  const demos = DATA.demo_portfolios || [];
  let html = `<span class="lbl">组合：</span>`;
  html += `<button class="v6-btn ${activeDemo ? "" : "active"}" onclick="setDemo('')">我的持仓</button>`;
  for (const d of demos) {
    html += `<button class="v6-btn ${activeDemo === d.id ? "active" : ""}" onclick="setDemo('${esc(d.id)}')">${esc(d.label)}</button>`;
  }
  $("selector").innerHTML = html;
}

function renderNotices() {
  const mode = DATA.data_mode;
  const mock = $("mock-notice");
  if (mode === "sample") {
    mock.style.display = "flex";
    $("mock-text").textContent = "示例数据：当前为内置示例组合 + 示例事件，仅用于演示引擎逻辑。";
  } else if (mode === "sample-events") {
    mock.style.display = "flex";
    $("mock-text").textContent = "你的真实持仓 + 示例事件源：持仓来自 Portfolio Tracker，事件为内置示例 fixture（默认未联网）。";
  } else {
    mock.style.display = "flex";
    $("mock-text").textContent = "已合并公开来源（" + (MODE_CN[DATA.sources_overall_mode] || DATA.sources_overall_mode) + "）。来源可用性以下方「数据源」状态为准。";
  }
  // stale-data / source-health warning (professional, non-alarming).
  // Prefer the centralized freshness warning so the page never implies the
  // data is "today's latest" when it is fixture / delayed / stale / unknown.
  const sw = $("stale-notice");
  const h = DATA.source_health || {};
  const freshWarn = DATA.freshness_warning_zh || (DATA.freshness || {}).freshness_warning_zh || "";
  if (sw) {
    if (freshWarn) {
      sw.style.display = "flex";
      $("stale-text").textContent = freshWarn;
    } else if (h.any_error) {
      sw.style.display = "flex";
      $("stale-text").textContent = "部分公开数据源当前不可用或返回错误，已自动回退到示例数据；读数仅供参考。";
    } else {
      sw.style.display = "none";
    }
  }
}

function modeBadge(mode) {
  return `<span class="badge mode-${esc(mode)}">${esc(MODE_CN[mode] || mode)}</span>`;
}

function renderNarrative(pf) {
  if (!pf.narrative) return "";
  return `<div class="v6-narrative">
    <span class="v6-narr-tag">组合解读</span>${esc(pf.narrative)}</div>`;
}

const THEME_DOT = {
  macro_rates: "var(--gold)", tech_ai: "var(--accent)", semis: "#56d4dd",
  company: "var(--green)", institutional: "#a371f7", regulatory: "var(--red)",
  sentiment: "#e8a0bf", future: "var(--gold)", other: "var(--text-muted)",
};

function renderThemes(pf) {
  const themes = pf.themes || [];
  if (!themes.length) return "";
  const cards = themes.map(t => {
    const cls = impClass(t.net_impact);
    return `<div class="v6-theme">
      <span class="dot" style="background:${THEME_DOT[t.theme] || "var(--text-muted)"};"></span>
      <span class="tn">${esc(t.theme_cn)}</span>
      <span class="tc">${t.event_count} 事件</span>
      <span class="v6-num ${cls}">${fmtSigned(t.net_impact)}</span>
    </div>`;
  }).join("");
  return `<div class="v6-themes">${cards}</div>`;
}

function renderSummary(pf) {
  const weighting = pf.weight_is_fallback ? "等权回退" : (pf.weighting === "cost-basis" ? "成本加权" : pf.weighting === "market-value" ? "市值加权" : pf.weighting);
  const stat = (label, value, sub) =>
    `<div class="v6-hero-stat"><div class="hs-v">${value}</div><div class="hs-l">${label}</div>${sub ? `<div class="hs-s">${sub}</div>` : ""}</div>`;
  return `
  <div class="v6-hero">
    <div class="v6-hero-main">
      <div class="hs-l">组合净影响</div>
      <div class="v6-hero-score ${impClass(pf.net_impact_score)}">${fmtSigned(pf.net_impact_score)}</div>
      <div><span class="badge ${pf.status}" style="font-size:13px;padding:3px 12px;">${sCN(pf.status)}</span></div>
      <div class="hs-s">${pf.holdings_count} 只持仓 · ${esc(weighting)}</div>
    </div>
    <div class="v6-hero-stats">
      ${stat("置信度", `${(pf.avg_confidence * 100).toFixed(0)}%`, `利好 ${fmtSigned(pf.positive_impact)} · 利空 ${fmtSigned(pf.negative_impact)}`)}
      ${stat("多空分歧度", `${Math.round((pf.disagreement || 0) * 100)}%`, (DATA.bands || {}).disagreement_cn ? `${(DATA.bands).disagreement_cn}分歧` : "")}
      ${stat("事件覆盖率", `${Math.round((pf.coverage || 0) * 100)}%`, `${pf.covered_holdings || 0}/${pf.holdings_count} 只有事件`)}
    </div>
  </div>`;
}

function renderDrivers(pf) {
  const row = (c, sign) => `<div class="v6-chip-row">
      <span>${esc(c.ticker)} <span class="badge ${c.status}">${sCN(c.status)}</span></span>
      <span class="v6-num ${sign}">${fmtSigned(c.net_impact)}</span></div>`;
  const topPos = (pf.top_positive_contributors || []).map(c => row(c, "pos")).join("") || `<div class="v6-empty">无</div>`;
  const topNeg = (pf.top_negative_contributors || []).map(c => row(c, "neg")).join("") || `<div class="v6-empty">无</div>`;
  const drivers = (pf.main_drivers || []).slice(0, 6).map(d => {
    const cls = impClass(d.net_impact);
    const ph = d.is_future ? `<span class="badge phase phase-${esc(d.phase)}">${esc(d.temporal_label || PHASE_CN[d.phase])}</span>` : "";
    const sc = d.source_count > 1 ? `<span class="badge tiny">×${d.source_count}源</span>` : "";
    return `<div class="v6-driver">
      <span class="et">${esc(etCN(d.event_type))}</span>
      <span class="ttl">${esc(d.title)}</span>
      ${ph}${sc}
      <span class="v6-num ${cls}">${fmtSigned(d.net_impact)}</span></div>`;
  }).join("") || `<div class="v6-empty">无</div>`;

  return `
  <div class="v6-section-title">驱动拆解</div>
  <div class="v6-drivers-grid">
    <div class="card"><div class="card-title">▲ 主要利好来源</div>${topPos}</div>
    <div class="card"><div class="card-title">▼ 主要利空来源</div>${topNeg}</div>
    <div class="card"><div class="card-title">主要驱动事件（宏观 / 情绪 / 公司）</div>${drivers}</div>
  </div>`;
}

function renderRiskCards(pf) {
  const risks = DATA.risks || {};
  const neg = (risks.top_negative_drivers || []);
  const priced = (risks.priced_in_catalysts || []);
  const negHtml = neg.length ? neg.map(d => `<div class="v6-driver">
      <span class="et">${esc(etCN(d.event_type))}</span>
      <span class="ttl">${esc(d.title)}</span>
      <span class="v6-num neg">${fmtSigned(d.net_impact)}</span></div>`).join("")
      : `<div class="v6-empty">当前无显著利空驱动</div>`;
  const pricedHtml = priced.length ? priced.map(d => `<div class="v6-driver">
      <span class="et">${esc(etCN(d.event_type))}</span>
      <span class="ttl">${esc(d.title)}</span>
      <span class="badge tiny">${Math.abs(d.countdown_days).toFixed(0)}天后</span>
      <span class="v6-num mut">已反映 ${Math.round(d.priced_in_score * 100)}%</span></div>`).join("")
      : `<div class="v6-empty">近期无显著「利好出尽」风险</div>`;
  return `<div class="v6-section-title">核心风险</div>
  <div class="v6-drivers-grid" style="grid-template-columns:1fr 1fr;">
    <div class="card"><div class="card-title">⚠ 今日主要风险（已发生利空）</div>${negHtml}</div>
    <div class="card"><div class="card-title">⏳ 预期兑现风险（利好出尽 / 已反映）</div>${pricedHtml}</div>
  </div>`;
}

function renderTimeline(pf) {
  const tl = pf.future_timeline || [];
  if (!tl.length) return "";
  const cards = tl.map(f => {
    const d = Math.abs(f.countdown_days);
    const risk = f.sell_the_news_risk >= 0.4
      ? `<div class="cat-risk">⚠ 利好出尽风险（预期已部分定价 ${(f.priced_in_score * 100).toFixed(0)}%）</div>` : "";
    const hits = (f.affected_tickers || []).slice(0, 6).join("、");
    return `<div class="v6-cat">
      <div class="cd">${d.toFixed(d < 1 ? 1 : 0)}<small> 天后</small></div>
      <span class="badge phase phase-${esc(f.phase)}">${esc(f.temporal_label || PHASE_CN[f.phase])}</span>
      <span class="badge ${dirBadge(f.expected_direction)}" style="font-size:10px;">预期${dirCN(f.expected_direction)}</span>
      <div class="cat-ttl">${esc(f.title)}</div>
      <div class="cat-meta">${esc(etCN(f.event_type))} · ${esc(f.source)}</div>
      <div class="cat-hits">影响持仓：${hits ? esc(hits) : "（间接）"}</div>
      ${risk}
    </div>`;
  }).join("");
  return `<div class="v6-section-title">未来事件 · 倒计时 <span class="cnt">${tl.length} 个已知催化</span></div>
    <div class="v6-timeline">${cards}</div>`;
}

function setSort(s) { holdingSort = s; render(); }

function renderHoldings(pf) {
  const rows = (pf.holdings || []).slice().sort((a, b) =>
    holdingSort === "weight" ? b.weight - a.weight : Math.abs(b.net_impact) - Math.abs(a.net_impact));
  const body = rows.map((h, i) => renderHolding(h, i)).join("");
  const sortCtl = `<span style="margin-left:auto;font-weight:400;">排序：
    <button class="v6-btn ghost ${holdingSort === "impact" ? "active" : ""}" onclick="setSort('impact')">按净影响</button>
    <button class="v6-btn ghost ${holdingSort === "weight" ? "active" : ""}" onclick="setSort('weight')">按权重</button></span>`;
  return `<div class="v6-section-title">持仓影响矩阵 <span class="cnt">点击展开通道拆解</span>${sortCtl}</div>
    <div class="v6-matrix-head">
      <div>持仓</div><div>权重</div><div>事件</div><div>净影响</div>
      <div>直接 / 二阶 / 情绪 / 未来</div><div></div>
    </div>${body}`;
}

function chanBar(cs) {
  if (!cs) return "";
  const cell = (v) => `<span class="v6-num ${impClass(v)}" style="font-size:11px;">${fmtSigned(v, 2)}</span>`;
  return `${cell(cs.direct)} <span class="mut">/</span> ${cell(cs.second_order)} <span class="mut">/</span> ${cell(cs.reflexivity)} <span class="mut">/</span> ${cell(cs.future)}`;
}

function driverMini(d, sign) {
  if (!d) return `<span class="mut">—</span>`;
  const cls = sign > 0 ? "pos" : "neg";
  return `<span class="${cls}">${esc(d.title)}</span> <span class="v6-num ${cls}">(${fmtSigned(d.impact)})</span>`;
}

function renderHolding(h, idx) {
  const pflag = h.matched_profile ? "" : ` <span class="badge neutral" title="未匹配内置画像，使用通用画像">通用画像</span>`;
  return `
  <div class="v6-holding" id="hold-${idx}">
    <div class="v6-holding-head" onclick="toggleHold(${idx})">
      <div>
        <div class="v6-tk">${esc(h.ticker)} <span class="badge ${h.status}">${sCN(h.status)}</span>${pflag}</div>
        <div class="v6-nm">${esc(h.name || "")} · ${esc(h.sector || "")}</div>
      </div>
      <div class="v6-col-hide"><div class="v6-col-label">权重</div><div class="v6-num">${fmtPct(h.weight)}</div></div>
      <div class="v6-col-hide"><div class="v6-col-label">事件数</div><div class="v6-num">${h.event_count}</div></div>
      <div><div class="v6-col-label">净影响</div><div class="v6-num ${impClass(h.net_impact)}">${fmtSigned(h.net_impact)}</div></div>
      <div class="v6-col-hide">
        <div class="v6-col-label">通道贡献（直/二/情/未来）</div>
        <div>${chanBar(h.channel_scores)}</div>
      </div>
      <div class="v6-caret">▶</div>
    </div>
    <div class="v6-detail">
      <div class="v6-concl">${esc(h.conclusion)}</div>
      <div class="v6-keyline">
        <span>▲ 关键利好：${driverMini(h.key_positive_driver, 1)}</span>
        <span>▼ 关键利空：${driverMini(h.key_negative_driver, -1)}</span>
      </div>
      ${(h.matched_tags && h.matched_tags.length) ? `<div class="v6-tags">命中标签：${h.matched_tags.map(t => `<span class="badge tiny">${esc(t)}</span>`).join(" ")}</div>` : ""}
      ${renderChannel("direct", h.channels.direct)}
      ${renderChannel("second_order", h.channels.second_order)}
      ${renderChannel("reflexivity", h.channels.reflexivity)}
      ${(h.upcoming && h.upcoming.length) ? `<div class="v6-channel"><div class="v6-channel-h"><span class="dot" style="background:var(--gold);"></span>未来催化（尚未计入当前分值）</div>${h.upcoming.map(evtCard).join("")}</div>` : ""}
    </div>
  </div>`;
}

function evtCard(r) {
  const dCls = r.effective_direction > 0 ? "pos" : r.effective_direction < 0 ? "neg" : "mut";
  const mk = MATCH_KIND_CN[r.match_kind] ? `<span class="badge tiny">${esc(MATCH_KIND_CN[r.match_kind])}</span>` : "";
  const ph = r.is_future || r.phase === "post_event"
    ? `<span class="badge phase phase-${esc(r.phase)}">${esc(r.temporal_label || PHASE_CN[r.phase])}</span>` : "";
  const cd = r.is_future ? `<span class="badge tiny">${Math.abs(r.countdown_days).toFixed(0)}天后</span>` : "";
  return `<div class="v6-evt">
    <div class="v6-evt-top">
      <div>
        <div class="v6-evt-title">${esc(r.title)}</div>
        <div class="v6-evt-meta">${esc(r.source_type)} · ${esc(etCN(r.event_type))} ${mk} ${ph} ${cd}
          · 命中 [${(r.matched_terms || []).map(esc).join("、")}]</div>
      </div>
      <div style="text-align:right;flex-shrink:0;">
        <span class="badge ${dirBadge(r.effective_direction)}">${dirCN(r.effective_direction)}</span>
        <div class="v6-num ${dCls}" style="margin-top:4px;">${fmtSigned(r.impact)}</div>
      </div>
    </div>
    <div class="v6-evt-exp">${esc(r.explanation)}</div>
  </div>`;
}

function renderChannel(channel, rows) {
  const dotCls = { direct: "direct", second_order: "second", reflexivity: "reflex" }[channel];
  let inner;
  if (!rows || rows.length === 0) inner = `<div class="v6-empty">该通道暂无映射事件</div>`;
  else inner = rows.slice().sort((a, b) => a.impact - b.impact).map(evtCard).join("");
  return `<div class="v6-channel"><div class="v6-channel-h"><span class="dot ${dotCls}"></span>${CHANNEL_CN[channel]}</div>${inner}</div>`;
}

const CHAN_COLS = [["direct", "直接"], ["second_order", "二阶"], ["reflexivity", "情绪"], ["future", "未来"]];

let drillTicker = null, drillChannel = null;
function drillCell(ticker, channel) {
  if (drillTicker === ticker && drillChannel === channel) { drillTicker = drillChannel = null; }
  else { drillTicker = ticker; drillChannel = channel; }
  render();
}

function _cellEvents(h, channel) {
  if (channel === "future") return (h.contributions || []).filter(r => r.is_future);
  return (h.channels && h.channels[channel]) ? h.channels[channel] : [];
}

function renderHeatmap(pf) {
  const rows = (pf.holdings || []).filter(h => h.event_count > 0)
    .slice().sort((a, b) => Math.abs(b.net_impact) - Math.abs(a.net_impact));
  if (!rows.length) return "";
  let mx = 1e-9;
  for (const h of rows) for (const [k] of CHAN_COLS) mx = Math.max(mx, Math.abs(h.channel_scores[k] || 0));
  const cell = (h, k) => {
    const v = h.channel_scores[k] || 0;
    const a = Math.min(0.85, Math.abs(v) / mx * 0.85 + (Math.abs(v) > 1e-9 ? 0.12 : 0));
    const c = v > 1e-9 ? `rgba(63,185,80,${a})` : v < -1e-9 ? `rgba(248,81,73,${a})` : "transparent";
    const active = (drillTicker === h.ticker && drillChannel === k) ? " hm-active" : "";
    const clickable = Math.abs(v) > 1e-9 ? ` onclick="drillCell('${esc(h.ticker)}','${k}')" class="v6-num hm-click${active}"` : ` class="v6-num"`;
    return `<td style="background:${c};"${clickable}>${v ? fmtSigned(v, 2) : "·"}</td>`;
  };
  const head = `<tr><th>持仓</th>${CHAN_COLS.map(([, l]) => `<th>${l}</th>`).join("")}<th>净影响</th></tr>`;
  const body = rows.map(h => `<tr>
      <td class="hm-tk">${esc(h.ticker)} <span class="badge ${h.status}" style="font-size:9.5px;">${sCN(h.status)}</span></td>
      ${CHAN_COLS.map(([k]) => cell(h, k)).join("")}
      <td class="v6-num ${impClass(h.net_impact)}">${fmtSigned(h.net_impact)}</td></tr>`).join("");
  return `<div class="card" style="overflow-x:auto;"><table class="v6-heatmap">${head}${body}</table>
      ${renderDrill(rows)}</div>`;
}

function renderDrill(rows) {
  if (!drillTicker || !drillChannel) return "";
  const h = rows.find(x => x.ticker === drillTicker);
  if (!h) return "";
  const chLabel = (CHAN_COLS.find(([k]) => k === drillChannel) || [, drillChannel])[1];
  const evs = _cellEvents(h, drillChannel).slice().sort((a, b) => a.impact - b.impact);
  const inner = evs.length ? evs.map(evtCard).join("") : `<div class="v6-empty">该单元格暂无贡献事件</div>`;
  return `<div class="v6-drill">
      <div class="v6-drill-h">${esc(drillTicker)} · ${esc(chLabel)} 通道贡献事件
        <span class="v6-drill-x" onclick="drillCell('${esc(drillTicker)}','${drillChannel}')">✕ 关闭</span></div>
      ${inner}</div>`;
}

let feedSort = "relevance";   // relevance | severity | confidence | freshness | direction
let feedFilter = "all";       // all | bull | bear
let feedSrc = "all";          // all | macro | company | institutional | official | sentiment
function setFeedSort(s) { feedSort = s; render(); }
function setFeedFilter(f) { feedFilter = f; render(); }
function setFeedSrc(s) { feedSrc = s; render(); }

const AGE_RANK = { fresh: 0, lagging: 1, stale: 2, fixture: 3, future: 4, unknown: 5 };

function renderFeed() {
  let evs = (DATA.events || []).slice();
  if (!evs.length) return "";
  const total = evs.length;
  if (feedFilter === "bull") evs = evs.filter(e => e.direction > 0);
  else if (feedFilter === "bear") evs = evs.filter(e => e.direction < 0);
  if (feedSrc !== "all") evs = evs.filter(e => e.source_type === feedSrc);
  if (feedSort === "relevance") evs.sort((a, b) => (b.portfolio_abs_impact || 0) - (a.portfolio_abs_impact || 0));
  else if (feedSort === "severity") evs.sort((a, b) => b.magnitude - a.magnitude);
  else if (feedSort === "confidence") evs.sort((a, b) => b.confidence - a.confidence);
  else if (feedSort === "freshness") evs.sort((a, b) => (AGE_RANK[a.age_band] ?? 9) - (AGE_RANK[b.age_band] ?? 9));
  else evs.sort((a, b) => (b.direction) - (a.direction));

  const rows = evs.map(e => {
    // Clean meta line: plain text with separators, not a wall of badges.
    const bits = [esc(e.source || e.source_type), esc(etCN(e.event_type)), `强度${esc(e.severity_cn)}`];
    const ageStale = e.age_band === "stale";
    if (e.age_label) bits.push(`<span class="${ageStale ? "neg" : ""}">${esc(e.age_label)}</span>`);
    if (e.source_count > 1) bits.push(`×${e.source_count}源`);
    if (e.is_scheduled) bits.push("已排期");
    const tickers = (e.related_tickers || []).length ? `<div class="v6-feed-tk">${esc(e.related_tickers.join("、"))}</div>` : "";
    const rel = (e.portfolio_abs_impact || 0) > 1e-9
      ? `<div class="rel v6-num ${impClass(e.portfolio_net_impact)}">${fmtSigned(e.portfolio_net_impact, 2)}</div><div class="rl">组合相关</div>`
      : `<div class="rl">置信 ${esc(e.confidence_band_cn)}</div>`;
    return `<div class="v6-feed-row">
      <span class="badge ${dirBadge(e.direction)}">${dirCN(e.direction)}</span>
      <div>
        <div class="v6-feed-ttl">${esc(e.title)}</div>
        <div class="v6-feed-meta">${bits.join(" · ")}</div>
        ${tickers}
      </div>
      <div class="v6-feed-right">${rel}</div>
    </div>`;
  }).join("") || `<div class="v6-empty">无符合条件的事件</div>`;

  const sBtn = (k, l) => `<button class="v6-btn ghost ${feedSort === k ? "active" : ""}" onclick="setFeedSort('${k}')">${l}</button>`;
  const fBtn = (k, l) => `<button class="v6-btn ghost ${feedFilter === k ? "active" : ""}" onclick="setFeedFilter('${k}')">${l}</button>`;
  const srcBtn = (k, l) => `<button class="v6-btn ghost ${feedSrc === k ? "active" : ""}" onclick="setFeedSrc('${k}')">${l}</button>`;
  const ctl = `<div class="v6-feed-ctl">
    <span>排序：${sBtn("relevance", "相关性")}${sBtn("severity", "强度")}${sBtn("confidence", "置信度")}${sBtn("freshness", "新鲜度")}${sBtn("direction", "方向")}</span>
    <span>方向：${fBtn("all", "全部")}${fBtn("bull", "利好")}${fBtn("bear", "利空")}</span>
    <span>来源：${srcBtn("all", "全部")}${srcBtn("macro", "宏观")}${srcBtn("company", "公司")}${srcBtn("institutional", "机构")}${srcBtn("official", "官方")}${srcBtn("sentiment", "情绪")}</span>
  </div>`;
  return `<div class="v6-feed-count">显示 ${evs.length}/${total} 条</div>${ctl}<div class="card">${rows}</div>`;
}

function renderSources() {
  const srcs = DATA.sources || [];
  if (!srcs.length) return "";
  const relCls = { "实时正常": "bullish", "部分实时": "mixed", "示例回退": "neutral", "未接实时源": "neutral", "错误": "bearish" };
  const cards = srcs.map(s => {
    const rel = s.reliability ? `<span class="badge ${relCls[s.reliability] || "neutral"}" style="font-size:9.5px;">${esc(s.reliability)}</span>` : "";
    const seen = s.last_success ? esc(s.last_success.replace("T", " ").replace("Z", "")) : "—";
    const errMsg = s.error_zh || s.error || "";   // sanitized, never raw
    return `<div class="v6-source">
      <div class="sn">${esc(s.source_name)} ${modeBadge(s.mode)} ${rel}</div>
      <div class="mut" style="font-size:10.5px;margin-top:3px;">${s.item_count} 条 · 最近成功 ${seen}${errMsg ? " · " + esc(errMsg) : ""}</div>
    </div>`;
  }).join("");
  return `<div class="v6-sources">${cards}</div>`;
}

function toggleHold(idx) { $(`hold-${idx}`).classList.toggle("open"); }

// init
load();
