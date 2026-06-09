// V5.1 Deal Studio front end.
// Company cards and default cost synergy are deterministic API inputs; the
// Python A/D engine remains the source of truth for EPS math.

const API = "";
let CARDS = [];
let mixMode = "mix"; // cash | stock | mix
let synergyMode = "default"; // default | manual | zero
let selected = { acq: null, tgt: null };
let searchSide = "acq";

const $ = (id) => document.getElementById(id);
const companyById = (id) => CARDS.find((c) => c.id === id) || null;

function fmt(n, dp = 0) {
  if (n === null || n === undefined || !isFinite(n)) return "-";
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function pct(n, dp = 2) {
  if (n === null || n === undefined || !isFinite(n)) return "-";
  const v = n * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%`;
}

function tierLabel(tier) {
  return { high: "高", medium: "中", low: "低", none: "无" }[tier] || "-";
}

// Optional deep link from Deal Arena Lite: /modeling/ma?acq=<id>&tgt=<id>.
// Falls back to the default first/second cards when params are missing or
// don't match a known company id. Read-only; never changes engine behavior.
function deepLinkSelection() {
  try {
    const params = new URLSearchParams(window.location.search);
    const acq = params.get("acq");
    const tgt = params.get("tgt");
    return {
      acq: companyById(acq) ? acq : null,
      tgt: companyById(tgt) ? tgt : null,
    };
  } catch (e) {
    return { acq: null, tgt: null };
  }
}

async function loadCards() {
  try {
    const resp = await fetch(`${API}/api/modeling/ma/samples`);
    const data = await resp.json();
    CARDS = data.companies || [];
  } catch (e) {
    CARDS = [];
  }
  if (CARDS.length) {
    const link = deepLinkSelection();
    const acqId = link.acq || CARDS[0].id;
    let tgtId = link.tgt || CARDS[CARDS.length > 1 ? 1 : 0].id;
    if (tgtId === acqId && CARDS.length > 1) {
      tgtId = CARDS.find((c) => c.id !== acqId).id;
    }
    pickCompany("acq", acqId, false);
    pickCompany("tgt", tgtId, false);
    runDeal();
  }
}

function applyCard(side, id) {
  const c = companyById(id);
  if (!c) return;
  $(`${side}-ni`).value = c.net_income;
  $(`${side}-sh`).value = c.shares;
  $(`${side}-px`).value = c.share_price;
}

function updatePartyCard(side, company) {
  $(`${side}-ticker`).textContent = company ? company.ticker : "-";
  $(`${side}-name`).textContent = company ? company.name : (side === "acq" ? "选择买方" : "选择标的");
  $(`${side}-sub`).textContent = company
    ? `${company.sector || "-"} · ${company.industry || "-"}`
    : "";
  $(`${side}-meta`).textContent = company
    ? `收入 ${fmt(company.revenue)} · ${company.tags?.market_position || "-"}`
    : "";
}

function pickCompany(side, id, doRun = true) {
  const c = companyById(id);
  if (!c) return;
  selected[side] = id;
  applyCard(side, id);
  updatePartyCard(side, c);
  if (doRun) runDeal();
}

function openSearch(side) {
  searchSide = side;
  $("cs-role").textContent = side === "acq" ? "买方" : "标的";
  $("cs-search").value = "";
  renderSearchResults("");
  $("cs-overlay").style.display = "flex";
  $("cs-search").focus();
}

function closeSearch() {
  $("cs-overlay").style.display = "none";
}

function searchRank(company, query) {
  if (!query) return 0;
  const ticker = String(company.ticker || "").toLowerCase();
  const name = String(company.name || "").toLowerCase();
  const industry = String(company.industry || "").toLowerCase();
  const sector = String(company.sector || "").toLowerCase();
  const tags = (company.tags?.strategic_tags || []).join(" ").toLowerCase();
  if (ticker === query) return 0;
  if (ticker.startsWith(query)) return 1;
  if (name.startsWith(query)) return 2;
  if (`${ticker} ${name}`.includes(query)) return 3;
  if (`${industry} ${sector} ${tags}`.includes(query)) return 4;
  return 99;
}

function renderSearchResults(query) {
  const q = String(query || "").trim().toLowerCase();
  const rows = CARDS
    .map((c, index) => ({ c, index, rank: searchRank(c, q) }))
    .filter((row) => !q || row.rank < 99)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((row) => row.c);
  const box = $("cs-results");
  box.innerHTML = "";
  if (!rows.length) {
    // User-supplied query must never be interpolated into innerHTML; build the
    // node and set the query via textContent so HTML/script cannot execute.
    const empty = document.createElement("div");
    empty.className = "cs-empty";
    empty.textContent = `没有匹配结果：${query}`;
    box.appendChild(empty);
    return;
  }
  for (const c of rows) {
    const row = document.createElement("div");
    row.className = "cs-row";
    const tags = (c.tags?.strategic_tags || []).slice(0, 3).join(" · ");
    row.innerHTML =
      `<span class="cs-row-ticker">${c.ticker}</span>` +
      `<span class="cs-row-name">${c.name}</span>` +
      `<span class="cs-row-sub">${c.industry || c.sector || ""}</span>` +
      `<span class="cs-row-tags">${tags}</span>`;
    row.addEventListener("click", () => {
      closeSearch();
      pickCompany(searchSide, c.id, true);
    });
    box.appendChild(row);
  }
}

function setMixMode(mode) {
  mixMode = mode;
  document.querySelectorAll("#mix-seg button").forEach((b) => {
    b.classList.toggle("active", b.dataset.mix === mode);
  });
  $("cash-pct-row").style.display = mode === "mix" ? "" : "none";
  updateMixReadout();
}

function cashPct() {
  if (mixMode === "cash") return 1.0;
  if (mixMode === "stock") return 0.0;
  const v = parseFloat($("cash-pct").value);
  return isFinite(v) ? Math.min(100, Math.max(0, v)) / 100 : 0.5;
}

function updateMixReadout() {
  const c = cashPct();
  const stock = Math.round((1 - c) * 100);
  $("mix-readout").textContent = stock > 0
    ? `股票 ${stock}% · 以新增买方股份支付`
    : "全现金 · 计入税后融资成本";
}

function setSynergyMode(mode) {
  synergyMode = mode;
  document.querySelectorAll("#synergy-seg button").forEach((b) => {
    b.classList.toggle("active", b.dataset.synergyMode === mode);
  });
  $("manual-synergy-row").style.display = mode === "manual" ? "" : "none";
  $("manual-synergy-hint").style.display = mode === "manual" ? "" : "none";
}

function reverseDirection() {
  for (const field of ["ni", "sh", "px"]) {
    const a = $(`acq-${field}`);
    const t = $(`tgt-${field}`);
    [a.value, t.value] = [t.value, a.value];
  }
  [selected.acq, selected.tgt] = [selected.tgt, selected.acq];
  updatePartyCard("acq", companyById(selected.acq));
  updatePartyCard("tgt", companyById(selected.tgt));
  runDeal();
}

function buildPayload() {
  const c = cashPct();
  return {
    acquirer: {
      sample_id: selected.acq,
      net_income: parseFloat($("acq-ni").value),
      shares: parseFloat($("acq-sh").value),
      share_price: parseFloat($("acq-px").value),
    },
    target: {
      sample_id: selected.tgt,
      net_income: parseFloat($("tgt-ni").value),
      shares: parseFloat($("tgt-sh").value),
      share_price: parseFloat($("tgt-px").value),
    },
    deal: {
      deal_type: "full_acquisition",
      premium: parseFloat($("premium").value) / 100,
      cash_pct: c,
      stock_pct: 1 - c,
      financing_cost: parseFloat($("financing-cost").value) / 100,
      tax_rate: parseFloat($("tax-rate").value) / 100,
      synergy_mode: synergyMode,
      synergy: parseFloat($("synergy").value) || 0,
    },
    currency: "USD",
  };
}

async function runDeal() {
  showError("");
  let data;
  try {
    const resp = await fetch(`${API}/api/modeling/ma/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    data = await resp.json();
  } catch (e) {
    showError("无法连接计算服务 / Could not reach the calculation service.");
    return;
  }
  if (data.status !== "ok") {
    const msg = (data.flags || []).map((f) => f.message).join(" ");
    showError(msg || "计算失败 / Calculation failed.");
    return;
  }
  render(data.result);
}

function showError(msg) {
  const el = $("error-panel");
  if (!msg) {
    el.style.display = "none";
    el.textContent = "";
    return;
  }
  el.style.display = "block";
  el.textContent = msg;
}

const SYNERGY_CHIP_CLASS = {
  self_accretive: "synergy-self",
  synergy_supported: "synergy-supported",
  synergy_short: "synergy-short",
};

function renderSynergyPanel(ctx) {
  const defaultSynergy = ctx.default_cost_synergy;
  if (!defaultSynergy) {
    $("default-synergy-value").textContent = "不可用";
    $("default-synergy-detail").textContent = "默认成本协同需要 company card 和标的收入。";
    return;
  }
  $("default-synergy-value").textContent =
    `${tierLabel(defaultSynergy.synergy_tier)} · ${fmt(defaultSynergy.synergy_amount)} USD mm`;
  $("default-synergy-detail").textContent =
    `${(defaultSynergy.synergy_pct_of_target_revenue * 100).toFixed(1)}% × 标的收入 · ` +
    `${defaultSynergy.calibration} · 仅成本协同`;
}

function render(r) {
  const verdict = $("verdict");
  verdict.textContent = r.is_accretive ? "Accretive" : "Dilutive";
  verdict.className = `headline-verdict ${r.is_accretive ? "accretive" : "dilutive"}`;
  $("verdict-pct").textContent = `EPS 较独立口径 ${pct(r.accretion_dilution)}`;

  const ctx = r.synergy_context || {};
  renderSynergyPanel(ctx);

  const chipRow = $("chip-row");
  chipRow.innerHTML = "";
  const synChip = document.createElement("span");
  synChip.className = `chip ${SYNERGY_CHIP_CLASS[r.synergy_status] || ""}`;
  synChip.textContent = r.synergy_status_label;
  chipRow.appendChild(synChip);

  const modeChip = document.createElement("span");
  modeChip.className = "chip";
  const modeText = ctx.mode === "default" ? "默认成本协同" : (ctx.mode === "zero" ? "0 协同" : "手动覆盖");
  modeChip.textContent = `${modeText} · ${fmt(r.synergy)} USD mm`;
  chipRow.appendChild(modeChip);

  const ppaChip = document.createElement("span");
  ppaChip.className = "chip pre-ppa";
  ppaChip.textContent = `${r.pre_ppa_chip.label} · 未计PPA`;
  ppaChip.title = r.pre_ppa_chip.detail;
  ppaChip.onclick = () => $("pre-ppa-tip").classList.toggle("show");
  chipRow.appendChild(ppaChip);
  $("pre-ppa-tip").textContent = r.pre_ppa_chip.detail;
  $("pre-ppa-tip").classList.remove("show");

  const zero = ctx.zero_synergy_result || {};
  const cells = [
    ["要约价值", fmt(r.offer_value), `溢价 ${pct(r.premium, 0)}，基于 ${fmt(r.target_equity_value)}`],
    ["现金对价", fmt(r.cash_consideration), `占要约 ${Math.round(r.consideration_mix.cash_pct * 100)}%`],
    ["股票对价", fmt(r.stock_consideration), `占要约 ${Math.round(r.consideration_mix.stock_pct * 100)}%`],
    ["新增股份", fmt(r.new_shares_issued, 1), "百万股（买方）"],
    ["无协同 EPS 影响", pct(zero.accretion_dilution), `EPS ${fmt(zero.pro_forma_eps, 2)}`],
    ["当前协同 EPS 影响", pct(r.accretion_dilution), `协同 ${fmt(r.synergy)} USD mm`],
    ["备考净利润", fmt(r.pro_forma_net_income), "计入当前协同与融资后"],
    ["备考股数", fmt(r.pro_forma_shares, 1), "百万股"],
    ["打平所需协同", fmt(r.break_even_synergy), r.break_even_synergy <= 0 ? "无需协同" : "使 EPS 打平"],
  ];
  const grid = $("econ-grid");
  grid.innerHTML = "";
  for (const [label, value, sub] of cells) {
    const cell = document.createElement("div");
    cell.className = "econ-cell";
    cell.innerHTML = `<div class="econ-label">${label}</div><div class="econ-value">${value}</div><div class="econ-sub">${sub}</div>`;
    grid.appendChild(cell);
  }

  renderViability(r.viability_context);
}

// V5.3 Real-World Viability. Rendered in its own block, physically separate
// from the economics above; it never reads or alters EPS / accretion-dilution.
function renderViability(via) {
  const levelEl = $("via-level");
  const summaryEl = $("via-summary");
  const flagsEl = $("via-flags");
  flagsEl.innerHTML = "";
  if (!via) {
    levelEl.textContent = "—";
    levelEl.className = "via-level";
    summaryEl.textContent = "本次推演未返回现实可行性结果。";
    return;
  }
  const level = via.viability_level || "green";
  levelEl.textContent = via.viability_label || "现实可行性：—";
  levelEl.className = `via-level ${level}`;
  summaryEl.textContent = via.summary || "";

  for (const f of via.flags || []) {
    const tags = (f.triggered_tags || []).join(", ");
    const card = document.createElement("div");
    card.className = `via-flag ${f.severity || ""}`;
    card.innerHTML =
      `<div class="via-flag-title">${f.title || ""}<span class="via-cat">${f.category || ""}</span></div>` +
      `<div class="via-flag-msg">${f.message || ""}</div>` +
      `<div class="via-flag-meta">rule: ${f.rule_id || "-"}${tags ? " · tags: " + tags : ""}</div>`;
    flagsEl.appendChild(card);
  }
}

function init() {
  loadCards();
  $("acq-card").addEventListener("click", () => openSearch("acq"));
  $("tgt-card").addEventListener("click", () => openSearch("tgt"));
  $("cs-close").addEventListener("click", closeSearch);
  $("cs-overlay").addEventListener("click", (e) => { if (e.target.id === "cs-overlay") closeSearch(); });
  $("cs-search").addEventListener("input", (e) => renderSearchResults(e.target.value));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSearch(); });
  $("reverse-btn").addEventListener("click", reverseDirection);
  $("run-btn").addEventListener("click", runDeal);
  document.querySelectorAll("#mix-seg button").forEach((b) => {
    b.addEventListener("click", () => {
      setMixMode(b.dataset.mix);
      runDeal();
    });
  });
  document.querySelectorAll("#synergy-seg button").forEach((b) => {
    b.addEventListener("click", () => {
      setSynergyMode(b.dataset.synergyMode);
      runDeal();
    });
  });
  [
    "premium", "cash-pct", "financing-cost", "tax-rate", "synergy",
    "acq-ni", "acq-sh", "acq-px", "tgt-ni", "tgt-sh", "tgt-px",
  ].forEach((id) => {
    $(id).addEventListener("input", () => {
      updateMixReadout();
      runDeal();
    });
  });
  setMixMode("mix");
  setSynergyMode("default");
}

document.addEventListener("DOMContentLoaded", init);
