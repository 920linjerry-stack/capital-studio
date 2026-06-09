// dcf_select.js - DCF version selector for Base / Bull / Bear.
const API = "http://127.0.0.1:5000";

document.addEventListener("DOMContentLoaded", async () => {
  const params = new URLSearchParams(window.location.search);
  const symbol = (params.get("symbol") || "").trim().toUpperCase();
  if (!symbol) {
    document.getElementById("select-content").innerHTML =
      '<div class="select-error">缺少 symbol 参数</div>';
    return;
  }

  const subtitle = document.getElementById("select-subtitle");
  if (subtitle) subtitle.textContent = `${symbol} · --`;

  try {
    const [baseData, scenarioMeta] = await Promise.all([
      _fetchBaseValuation(symbol),
      fetch(`${API}/api/modeling/dcf/scenarios/${encodeURIComponent(symbol)}`).then(r => r.json()),
    ]);
    renderSelectPage(symbol, baseData, scenarioMeta);
  } catch (err) {
    document.getElementById("select-content").innerHTML =
      `<div class="select-error">加载失败：${_escapeHtml(err.message)}</div>`;
  }
});

async function _fetchBaseValuation(symbol) {
  const defaultsRes = await fetch(`${API}/api/modeling/dcf?symbol=${encodeURIComponent(symbol)}`);
  const defaultsData = await defaultsRes.json();
  if (defaultsData.error) return { error: defaultsData.error };

  const params = defaultsData.defaults;
  const postRes = await fetch(`${API}/api/modeling/dcf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  const result = await postRes.json();
  if (result.error) return { error: result.error };

  return {
    intrinsic_per_share: result.intrinsic_per_share,
    currency: result.currency || params.currency,
    company: params.company,
    params,
  };
}

function renderSelectPage(symbol, base, meta) {
  const subtitle = document.getElementById("select-subtitle");
  if (subtitle) subtitle.textContent = `${symbol} · ${base.company || symbol}`;

  const content = document.getElementById("select-content");
  content.innerHTML = `
    <div class="scenario-stack">
      ${_renderBaseCard(symbol, base)}
      ${_renderScenarioCard(symbol, "bull", "Bull / 乐观情景 DCF", meta && meta.bull, base)}
      ${_renderScenarioCard(symbol, "bear", "Bear / 悲观情景 DCF", meta && meta.bear, base)}
    </div>
  `;
}

function _renderBaseCard(symbol, base) {
  const value = base.error
    ? `<div class="scenario-desc">系统默认估值加载失败：${_escapeHtml(base.error)}</div>`
    : `<div class="scenario-desc">系统默认估值</div>
       <div class="scenario-value">${_formatValue(base.intrinsic_per_share, base.currency)}</div>`;

  return `
    <article class="scenario-card">
      <div class="scenario-card-head">
        <div class="scenario-card-title">Base / 默认 DCF</div>
        <span class="scenario-badge saved">可进入</span>
      </div>
      ${value}
      <div class="scenario-actions">
        <a class="btn btn-primary" href="/modeling/dcf?symbol=${encodeURIComponent(symbol)}&scenario=base">进入</a>
      </div>
    </article>
  `;
}

function _renderScenarioCard(symbol, type, title, meta) {
  const isBull = type === "bull";
  const createHint = isBull
    ? "进入默认 DCF 后，在'估值情景设置'中调整投资逻辑并保存为乐观情景"
    : "进入默认 DCF 后，在'估值情景设置'中调整投资逻辑并保存为悲观情景";

  if (!meta) {
    return `
      <article class="scenario-card is-disabled">
        <div class="scenario-card-head">
          <div class="scenario-card-title">${title}</div>
          <span class="scenario-badge">未创建</span>
        </div>
        <div class="scenario-desc">${createHint}</div>
        <div class="scenario-actions">
          <button class="btn btn-secondary" disabled>进入</button>
        </div>
      </article>
    `;
  }

  return `
    <article class="scenario-card">
      <div class="scenario-card-head">
        <div class="scenario-card-title">${title}</div>
        <span class="scenario-badge saved">已保存</span>
      </div>
      <div class="scenario-value">${_formatValue(meta.intrinsic_per_share, meta.currency)}</div>
      <div class="scenario-time">最近修改：${_formatDateTime(meta.updated_at)}</div>
      <div class="scenario-actions">
        <a class="btn btn-primary" href="/modeling/dcf?symbol=${encodeURIComponent(symbol)}&scenario=${type}">进入</a>
      </div>
    </article>
  `;
}

function _renderBaseCardV346(symbol, base) {
  const value = base.error
    ? `<div class="scenario-value">--</div>
       <div class="scenario-time">系统默认 · 加载失败：${_escapeHtml(base.error)}</div>`
    : `<div class="scenario-value">${_formatValue(base.intrinsic_per_share, base.currency)}</div>
       <div class="scenario-time">系统默认</div>`;

  return `
    <article class="scenario-card">
      <div class="scenario-card-head">
        <div class="scenario-card-title">Base / 默认 DCF</div>
        <span class="scenario-badge saved">可进入</span>
      </div>
      ${value}
      <div class="scenario-actions">
        <a class="btn btn-primary" href="/modeling/dcf?symbol=${encodeURIComponent(symbol)}&scenario=base">进入</a>
      </div>
    </article>
  `;
}

function _renderScenarioCardV346(symbol, type, title, meta, base) {
  const isBull = type === "bull";
  const createHint = isBull
    ? "进入默认 DCF 后，在'估值情景设置'中调整投资逻辑并保存为乐观情景"
    : "进入默认 DCF 后，在'估值情景设置'中调整投资逻辑并保存为悲观情景";

  if (!meta) {
    return `
      <article class="scenario-card is-disabled">
        <div class="scenario-card-head">
          <div class="scenario-card-title">${title}</div>
          <span class="scenario-badge">未创建</span>
        </div>
        <div class="scenario-value">--</div>
        <div class="scenario-time">未创建</div>
        <div class="scenario-desc">${createHint}</div>
        <div class="scenario-actions">
          <button class="btn btn-secondary" disabled>进入</button>
        </div>
      </article>
    `;
  }

  const warnings = _scenarioWarnings(type, meta, base);

  return `
    <article class="scenario-card">
      <div class="scenario-card-head">
        <div class="scenario-card-title">${title}</div>
        <span class="scenario-badge saved">已保存</span>
      </div>
      <div class="scenario-value">${_formatValue(meta.intrinsic_per_share, meta.currency)}</div>
      <div class="scenario-time">最近修改 ${_formatDateTime(meta.updated_at)}</div>
      ${warnings}
      <div class="scenario-actions">
        <a class="btn btn-primary" href="/modeling/dcf?symbol=${encodeURIComponent(symbol)}&scenario=${type}">进入</a>
      </div>
    </article>
  `;
}

_renderBaseCard = _renderBaseCardV346;
_renderScenarioCard = _renderScenarioCardV346;

function _scenarioWarnings(type, meta, base) {
  const notes = [];
  const baseValue = Number(base && base.intrinsic_per_share);
  const scenarioValue = Number(meta && meta.intrinsic_per_share);
  if (Number.isFinite(baseValue) && Number.isFinite(scenarioValue) && baseValue > 0) {
    if (type === "bull" && scenarioValue < baseValue) {
      notes.push("Bull valuation is below Base. This may be an older or intentionally conservative saved scenario; review assumptions before using it.");
    }
    if (type === "bear" && scenarioValue > baseValue) {
      notes.push("Bear valuation is above Base. This may be an older or intentionally upside-skewed saved scenario; review assumptions before using it.");
    }
  }
  if (meta?.compatibility?.legacy_fcf_growth_mapped) {
    notes.push("Legacy saved field mapped: fcf_growth is shown as Revenue Growth for compatibility.");
  }
  if (_isStaleScenario(meta?.params, base?.params)) {
    notes.push("Saved scenario financial inputs differ from current Base defaults; treat it as a saved reference until refreshed.");
  }
  if (!notes.length) return "";
  return `<div class="scenario-desc scenario-warning">${notes.map(_escapeHtml).join("<br>")}</div>`;
}

function _isStaleScenario(scenarioParams, baseParams) {
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

function _formatValue(value, currency) {
  const ccy = currency || "";
  if (value == null) return `-- ${_escapeHtml(ccy)}`;
  return `${Number(value).toFixed(2)} ${_escapeHtml(ccy)}`.trim();
}

function _formatDateTime(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

function _escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
