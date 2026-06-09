// V5.6.1 Deal Arena · Tabletop (formal play view).
//
// Immersive play-view over the SAME real seed deck, SAME precomputed pairs and
// SAME deterministic A/D engine as the War Room (/modeling/ma/arena) and Deal
// Studio. It re-implements NO economics: the light result is a precomputed
// PAIRS_INDEX lookup, and the Deal Ticket reuses /api/modeling/ma/calculate.
//
// Hard boundaries: no bots, no turn system, no event cards, no Overall Score,
// no backend per-user state, no randomness, no runtime fetch/LLM/plugin.

const API = "";

// Fixed light-table deal terms — identical to arena.js / precompute so the play
// table, the War Room and Deal Studio all produce the SAME number.
const ARENA_DEAL_TERMS = {
  deal_type: "full_acquisition",
  premium: 0.30,
  cash_pct: 0.5,
  stock_pct: 0.5,
  financing_cost: 0.05,
  tax_rate: 0.25,
  synergy_mode: "default",
};

let CARDS = [];
let PAIRS_INDEX = {};
let BOARDS = null;
let selected = { acq: null, tgt: null };
// V5.8 Deal Review Queue: the LIGHT pair last rendered in the result HUD. Used
// only to build a queue summary on demand — never re-computed.
let currentLight = null;

// Front-end-only hand state (deterministic window over the deck; no randomness).
let HAND = [];
const HAND_SIZE = 7;
let handOffset = 0;
let DRAG_ID = null;

const $ = (id) => document.getElementById(id);
const companyById = (id) => CARDS.find((c) => c.id === id) || null;
const pairKey = (acq, tgt) => `${acq}__${tgt}`;
const ARENA_TIERS = new Set(["gold", "red", "blue", "green", "white"]);

function arenaTier(c) {
  return ARENA_TIERS.has(c?.arena_tier) ? c.arena_tier : "white";
}

function applyArenaTier(node, c) {
  const tier = arenaTier(c);
  node.classList.add("arena-tier", `tier-${tier}`);
  if (c?.arena_tier_reason) node.title = c.arena_tier_reason;
  return tier;
}

function arenaTierBadge(c, extraClass = "") {
  const badge = el("span", `arena-tier arena-tier-badge tier-${arenaTier(c)} ${extraClass}`.trim(),
    c?.arena_tier_label || "Basic");
  if (c?.arena_tier_reason) badge.title = c.arena_tier_reason;
  return badge;
}

function clearArenaTierClasses(node) {
  if (!node) return;
  node.classList.remove("arena-tier", "tier-gold", "tier-red", "tier-blue", "tier-green", "tier-white");
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

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

function marketCapSense(company) {
  const cap = Number(company.share_price) * Number(company.shares);
  if (!isFinite(cap) || cap <= 0) return "-";
  if (cap >= 1_000_000) return `$${(cap / 1_000_000).toFixed(2)}T`;
  return `$${fmt(cap)}B`;
}

function prettyTag(tag) {
  return String(tag || "").replace(/_/g, " ");
}

// V5.9.6 localization accessors (shared deterministic display map; safe fallback).
function cnName(c) { return (window.CardLocalization && window.CardLocalization.nameCn(c)) || c?.name || c?.ticker || "—"; }
function cnSector(c) { return (window.CardLocalization && window.CardLocalization.sectorCn(c)) || c?.sector || "—"; }
function enName(c) { return (window.CardLocalization && window.CardLocalization.enName(c)) || c?.name || ""; }

const VIA_CATEGORY_LABEL = {
  antitrust: "反垄断 · Antitrust",
  sensitive_sector: "敏感行业 · Sensitive Sector",
  capacity: "交易承接 · Deal Capacity",
  other: "综合 · General",
};

const VIA_SEVERITY_LABEL = {
  red: "高风险 · High",
  yellow: "需审查 · Review",
  green: "通过 · Clear",
};

function formatViaCategory(cat) {
  return VIA_CATEGORY_LABEL[cat] || prettyTag(cat);
}

function formatViaSeverity(sev) {
  return VIA_SEVERITY_LABEL[sev] || sev || "—";
}

function formatTriggeredSummary(tags) {
  const list = (tags || []).filter(Boolean);
  if (!list.length) return "";
  return list.map(prettyTag).join(" · ");
}

// ── Data loading (compact precomputed; never N*(N-1) calculate calls) ──────
async function loadCards() {
  try {
    const resp = await fetch(`${API}/api/modeling/ma/samples`);
    const data = await resp.json();
    CARDS = data.companies || [];
  } catch (e) {
    CARDS = [];
    showError("无法加载公司牌 / Could not load the company deck.");
  }
}

async function loadPairs() {
  try {
    const resp = await fetch(`${API}/api/modeling/ma/arena/pairs`);
    const data = await resp.json();
    const index = {};
    for (const p of data.pairs || []) index[pairKey(p.acquirer_id, p.target_id)] = p;
    PAIRS_INDEX = index;
    BOARDS = data.boards || null;
  } catch (e) {
    PAIRS_INDEX = {};
    BOARDS = null;
    console.info("[play] pairs map unavailable; will use calculate fallback");
  }
}

// ── Company cards (safe DOM; draggable + drop target) ───────────────────────
function buildHandCard(c) {
  // Stable hitbox wrapper: the shell holds the fan transform & receives :hover;
  // the inner .pcard does the visual lift. The shell never moves, so hovering
  // the card's bottom edge can't bounce the hitbox out from under the cursor.
  const shell = el("div", "pcard-shell");
  const card = el("div", "pcard");
  applyArenaTier(card, c);
  card.dataset.id = c.id;
  card.setAttribute("role", "button");
  card.setAttribute("tabindex", "0");
  card.setAttribute("draggable", "true");
  card.setAttribute("aria-label", `${c.ticker} ${cnName(c)} ${c.name || ""}`.trim());
  card.append(
    arenaTierBadge(c, "pcard-tier"),
    el("div", "pcard-ticker", c.ticker),
    el("div", "pcard-name", cnName(c)),
    el("div", "pcard-sub", cnSector(c)),
  );
  const cap = el("div", "pcard-cap");
  cap.append(document.createTextNode("市值感 "));
  cap.append(el("b", null, marketCapSense(c)));
  card.append(cap);

  card.addEventListener("click", () => onCardClick(c.id));
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCardClick(c.id); }
  });
  attachDragSource(card, c.id);
  attachCardDropZone(card, c.id);
  shell.appendChild(card);
  return shell;
}

// ── Player Hand · deterministic window over the deck ────────────────────────
function drawHand() {
  HAND = [];
  const n = Math.min(HAND_SIZE, CARDS.length);
  for (let i = 0; i < n; i++) HAND.push(CARDS[(handOffset + i) % CARDS.length].id);
  renderHand();
  refreshPileTier();
}

function refreshPileTier() {
  const pile = $("draw-pile");
  if (!pile || !CARDS.length) return;
  clearArenaTierClasses(pile);
  const next = CARDS[(handOffset + HAND_SIZE) % CARDS.length];
  applyArenaTier(pile, next);
  pile.setAttribute("aria-label", `Draw ${next.arena_tier_label || "Basic"} card`);
}

function drawOne() {
  if (!CARDS.length) return;
  handOffset = (handOffset + 1) % CARDS.length;
  drawHand();
}

function rotateHand() {
  if (!CARDS.length) return;
  handOffset = (handOffset + HAND_SIZE) % CARDS.length;
  drawHand();
}

function renderHand() {
  const fan = $("hand-fan");
  if (!fan) return;
  fan.textContent = "";
  const n = HAND.length;
  const mid = (n - 1) / 2;
  HAND.forEach((id, i) => {
    const c = companyById(id);
    if (!c) return;
    const shell = buildHandCard(c);
    // Foreground hand fan: the shell (stable hitbox) carries the rotate + edge
    // sink so the centre cards sit higher — a held-hand arch (deterministic).
    const rot = (i - mid) * 5;
    const lift = Math.abs(i - mid) * 5;
    shell.style.transform = `rotate(${rot}deg) translateY(${lift}px)`;
    shell.style.zIndex = String(10 - Math.abs(i - mid));
    fan.appendChild(shell);
  });
  refreshSelectionUI();
}

// ── Drag-to-deal · A dropped onto B means A → B ─────────────────────────────
function attachDragSource(node, id) {
  node.addEventListener("dragstart", (e) => {
    DRAG_ID = id;
    try { e.dataTransfer.setData("text/plain", id); e.dataTransfer.effectAllowed = "copy"; } catch (_) {}
    node.classList.add("dragging");
  });
  node.addEventListener("dragend", () => {
    DRAG_ID = null;
    node.classList.remove("dragging");
    document.querySelectorAll(".drag-over").forEach((n) => n.classList.remove("drag-over"));
  });
}

function getDragId(e) {
  let id = "";
  try { id = e.dataTransfer.getData("text/plain"); } catch (_) { id = ""; }
  if (!id) id = DRAG_ID || "";
  return companyById(id) ? id : null;
}

function attachCardDropZone(node, id) {
  node.addEventListener("dragover", (e) => { e.preventDefault(); node.classList.add("drag-over"); });
  node.addEventListener("dragleave", () => node.classList.remove("drag-over"));
  node.addEventListener("drop", (e) => {
    e.preventDefault();
    node.classList.remove("drag-over");
    const acqId = getDragId(e);
    if (!acqId) return;
    if (acqId === id) { flashHint("同一家公司不能并购自己。"); return; }
    setDeal(acqId, id); // dragged A onto card B => A acquires B
  });
}

function attachSlotDropZone(slotEl, side) {
  if (!slotEl) return;
  slotEl.addEventListener("dragover", (e) => { e.preventDefault(); slotEl.classList.add("drag-over"); });
  slotEl.addEventListener("dragleave", () => slotEl.classList.remove("drag-over"));
  slotEl.addEventListener("drop", (e) => {
    e.preventDefault();
    slotEl.classList.remove("drag-over");
    const id = getDragId(e);
    if (!id) return;
    if (side === "acq") setDeal(id, selected.tgt);
    else setDeal(selected.acq, id);
  });
}

// ── Selection funnel ────────────────────────────────────────────────────────
function setDeal(acqId, tgtId) {
  const a = acqId && companyById(acqId) ? acqId : null;
  const t = tgtId && companyById(tgtId) ? tgtId : null;
  if (a && t && a === t) { flashHint("同一家公司不能并购自己。"); return; }
  selected.acq = a;
  selected.tgt = t;
  applySelection();
}

function applySelection() {
  refreshSelectionUI();
  if (selected.acq && selected.tgt) showDeal();
  else clearResult();
  closeTicket();
}

function flashHint(msg) {
  const h = $("deal-hint");
  if (h) h.textContent = msg;
}

function onCardClick(id) {
  if (!companyById(id)) return;
  if (selected.acq === id) {
    selected.acq = selected.tgt;
    selected.tgt = null;
  } else if (selected.tgt === id) {
    selected.tgt = null;
  } else if (!selected.acq) {
    selected.acq = id;
  } else if (!selected.tgt) {
    selected.tgt = id;
  } else {
    selected.tgt = id;
  }
  applySelection();
}

function reverseDirection() {
  if (!selected.acq || !selected.tgt) return;
  setDeal(selected.tgt, selected.acq);
}

function clearSelection() {
  selected = { acq: null, tgt: null };
  ticketReqId += 1;
  showError("");
  applySelection();
}

function deepLinkInit() {
  try {
    const params = new URLSearchParams(window.location.search);
    const acq = params.get("acq");
    const tgt = params.get("tgt");
    if ((acq && companyById(acq)) || (tgt && companyById(tgt))) {
      setDeal(companyById(acq) ? acq : null, companyById(tgt) ? tgt : null);
    }
  } catch (_) {}
}

function renderSlot(side, c) {
  const body = $(`slot-${side}-body`);
  const slot = $(`slot-${side}`);
  if (!body) return;
  body.textContent = "";
  clearArenaTierClasses(slot);
  if (!c) {
    body.appendChild(el("div", "pslot-empty",
      side === "acq" ? "拖入买方牌，或点选一张手牌" : "拖入标的牌，或再点一张手牌"));
    return;
  }
  applyArenaTier(slot, c);
  body.append(
    el("div", "pslot-ticker", c.ticker),
    el("div", "pslot-name", cnName(c)),
    el("div", "pslot-sub", cnSector(c)),
    el("div", "pslot-cap", `市值感 ${marketCapSense(c)}`),
    arenaTierBadge(c, "slot-tier"),
  );
}

function refreshSelectionUI() {
  renderSlot("acq", companyById(selected.acq));
  renderSlot("tgt", companyById(selected.tgt));

  document.querySelectorAll(".pcard").forEach((node) => {
    node.classList.toggle("sel-acq", node.dataset.id === selected.acq);
    node.classList.toggle("sel-tgt", node.dataset.id === selected.tgt);
  });

  $("slot-acq").classList.toggle("filled", !!selected.acq);
  $("slot-tgt").classList.toggle("filled", !!selected.tgt);
  $("reverse-btn").disabled = !(selected.acq && selected.tgt);
  const clearBtn = $("clear-deal-btn");
  if (clearBtn) clearBtn.disabled = !(selected.acq || selected.tgt);

  if (!selected.acq && !selected.tgt) {
    flashHint("把一张手牌拖到另一张牌或标的槽位上：A 拖到 B 表示「A 收购 B」。也可点击选牌。");
  } else if (!selected.tgt) {
    flashHint("已就位买方，再拖入或点选一张标的牌。");
  } else if (!selected.acq) {
    flashHint("已就位标的，再拖入或点选一张买方牌。");
  } else {
    flashHint("用 ⇄ 反转方向（买方↔标的），结果会重新计算。");
  }
}

// ── Light result (lookup-first; calculate only as fallback) ─────────────────
function buildPayload() {
  return {
    acquirer: { sample_id: selected.acq },
    target: { sample_id: selected.tgt },
    deal: { ...ARENA_DEAL_TERMS },
    currency: "USD",
  };
}

async function showDeal() {
  showError("");
  const light = PAIRS_INDEX[pairKey(selected.acq, selected.tgt)];
  if (light) { renderLight(light); return; }
  await calculateFallback();
}

async function calculateFallback() {
  console.info("[play] precomputed pair missing; falling back to /api/modeling/ma/calculate", selected);
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
    showError((data.flags || []).map((f) => f.message).join(" ") || "计算失败 / Calculation failed.");
    return;
  }
  renderLight(toLight(data.result));
}

function toLight(r) {
  const ctx = r.synergy_context || {};
  const def = ctx.default_cost_synergy;
  const via = r.viability_context || {};
  return {
    acquirer_id: r.acquirer?.id,
    target_id: r.target?.id,
    acquirer_ticker: r.acquirer?.ticker,
    target_ticker: r.target?.ticker,
    accretion_dilution_pct: r.accretion_dilution,
    is_accretive: !!r.is_accretive,
    synergy_status: r.synergy_status,
    synergy_status_label: r.synergy_status_label,
    default_synergy_tier: def ? def.synergy_tier : null,
    pre_ppa_chip: r.pre_ppa_chip || { label: "Pre-PPA", detail: "" },
    viability_level: via.viability_level,
    viability_label: via.viability_label,
    viability_flags_top: (via.flags || []).slice(0, 2).map((f) => ({ severity: f.severity, title: f.title })),
  };
}

const SYNERGY_CHIP_CLASS = {
  self_accretive: "synergy-self",
  synergy_supported: "synergy-supported",
  synergy_short: "synergy-short",
};

function clearResult() {
  $("result-empty").style.display = "";
  $("result-body").style.display = "none";
  currentLight = null;
  updateQueueButtons();
}

function addChip(container, text, cls) {
  const chip = el("span", `chip ${cls || ""}`, text);
  container.appendChild(chip);
  return chip;
}

function renderLight(p) {
  $("result-empty").style.display = "none";
  $("result-body").style.display = "";
  currentLight = p;
  $("rc-acq").textContent = p.acquirer_ticker || "—";
  $("rc-tgt").textContent = p.target_ticker || "—";
  const acqCard = companyById(selected.acq);
  const tgtCard = companyById(selected.tgt);
  clearArenaTierClasses($("rc-acq"));
  clearArenaTierClasses($("rc-tgt"));
  if (acqCard) { applyArenaTier($("rc-acq"), acqCard); $("rc-acq").classList.add("tier-text"); }
  if (tgtCard) { applyArenaTier($("rc-tgt"), tgtCard); $("rc-tgt").classList.add("tier-text"); }

  const epsEl = $("rc-eps-val");
  epsEl.textContent = pct(p.accretion_dilution_pct);
  epsEl.className = `rc-eps-val ${p.is_accretive ? "accretive" : "dilutive"}`;

  const chips = $("rc-chips");
  chips.textContent = "";
  addChip(chips, p.synergy_status_label, SYNERGY_CHIP_CLASS[p.synergy_status] || "");
  addChip(chips, p.default_synergy_tier ? `默认协同：${tierLabel(p.default_synergy_tier)}` : "默认协同：不可用", "");
  addChip(chips, p.is_accretive ? "经济性：增厚" : "经济性：摊薄", p.is_accretive ? "econ-pos" : "econ-neg");
  const ppa = addChip(chips, `${p.pre_ppa_chip?.label || "Pre-PPA"} · 未计PPA`, "pre-ppa");
  ppa.title = p.pre_ppa_chip?.detail || "";

  renderViability(p);

  $("rc-studio-btn").href =
    `/modeling/ma?acq=${encodeURIComponent(selected.acq)}&tgt=${encodeURIComponent(selected.tgt)}`;

  updateQueueButtons();
}

function renderViability(p) {
  const box = $("rc-viability-chips");
  box.textContent = "";
  const level = p.viability_level || "green";
  box.appendChild(el("span", `vchip level ${level}`, p.viability_label || "现实可行性：—"));
  const flags = (p.viability_flags_top || []).filter((f) => f.severity !== "green");
  for (const f of flags.slice(0, 2)) box.appendChild(el("span", `vchip ${f.severity || ""}`, f.title));
}

// ── Mini settlement board (Top 3, two tabs, no Overall Score) ────────────────
const VIA_TAG_CLASS = { green: "green", yellow: "yellow", red: "red" };

function renderMiniBoards() {
  renderMiniBoard($("pb-board-econ"), (BOARDS && BOARDS.economic) || [], "econ");
  renderMiniBoard($("pb-board-via"), (BOARDS && BOARDS.viability) || [], "via");
}

function renderMiniBoard(box, rows, kind) {
  if (!box) return;
  box.textContent = "";
  if (!rows.length) {
    box.appendChild(el("div", "result-empty", "结算板暂不可用。"));
    return;
  }
  rows.slice(0, 3).forEach((p, i) => box.appendChild(buildMiniRow(p, i + 1, kind)));
}

function buildMiniRow(p, rank, kind) {
  const row = el("div", "pb-row");
  row.appendChild(el("span", "pb-rank", `#${rank}`));

  const deal = el("span", "pb-deal");
  const acq = el("span", "a");
  const acqCard = companyById(p.acquirer_id);
  if (acqCard) acq.appendChild(el("span", `tier-pip arena-tier tier-${arenaTier(acqCard)}`));
  acq.appendChild(document.createTextNode(p.acquirer_ticker || "—"));
  const tgt = el("span", "t");
  const tgtCard = companyById(p.target_id);
  if (tgtCard) tgt.appendChild(el("span", `tier-pip arena-tier tier-${arenaTier(tgtCard)}`));
  tgt.appendChild(document.createTextNode(p.target_ticker || "—"));
  deal.append(acq, el("span", "ar", "→"), tgt);
  row.appendChild(deal);

  if (kind === "via") {
    row.appendChild(el("span", `pb-vtag ${VIA_TAG_CLASS[p.viability_level] || ""}`,
      shortViaLabel(p)));
  } else {
    const epsText = pct(p.accretion_dilution_pct);
    const eps = el("span", `pb-eps ${epsText === "-" ? "na" : (p.is_accretive ? "accretive" : "dilutive")}`,
      epsText === "-" ? "数据不足" : epsText);
    row.appendChild(eps);
  }

  row.addEventListener("click", () => {
    if (!companyById(p.acquirer_id) || !companyById(p.target_id)) return;
    setDeal(p.acquirer_id, p.target_id);
  });
  return row;
}

function shortViaLabel(p) {
  const label = p.viability_label || "";
  return label.replace("现实可行性：", "可行性 ") || "可行性 —";
}

function setMiniTab(board) {
  document.querySelectorAll(".pb-tab").forEach((b) => b.classList.toggle("active", b.dataset.board === board));
  $("pb-board-econ").style.display = board === "econ" ? "" : "none";
  $("pb-board-via").style.display = board === "via" ? "" : "none";
}

function showError(msg) {
  const el2 = $("error-panel");
  if (!msg) { el2.style.display = "none"; el2.textContent = ""; return; }
  el2.style.display = "block";
  el2.textContent = msg;
}

// ── Deal Ticket (reuses /api/modeling/ma/calculate; same render as War Room) ─
let ticketReqId = 0;

function closeTicket() { $("ticket-overlay").style.display = "none"; }

async function openTicket() {
  if (!selected.acq || !selected.tgt) return;
  $("ticket-overlay").style.display = "flex";
  $("ticket-loading").style.display = "";
  $("ticket-body").style.display = "none";
  $("ticket-error").style.display = "none";

  const acq = companyById(selected.acq);
  const tgt = companyById(selected.tgt);
  $("ticket-title").textContent = `Deal Ticket · ${acq ? acq.ticker : "—"} 收购 ${tgt ? tgt.ticker : "—"}`;
  $("tk-studio-btn").href =
    `/modeling/ma?acq=${encodeURIComponent(selected.acq)}&tgt=${encodeURIComponent(selected.tgt)}`;

  const reqId = ++ticketReqId;
  let data;
  try {
    const resp = await fetch(`${API}/api/modeling/ma/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    data = await resp.json();
  } catch (e) {
    if (reqId === ticketReqId) showTicketError("无法连接计算服务 / Could not reach the calculation service.");
    return;
  }
  if (reqId !== ticketReqId) return;
  if (!data || data.status !== "ok" || !data.result) {
    showTicketError(((data && data.flags) || []).map((f) => f.message).join(" ") || "计算失败 / Calculation failed.");
    return;
  }
  renderTicket(data.result);
}

function showTicketError(msg) {
  $("ticket-loading").style.display = "none";
  $("ticket-body").style.display = "none";
  const e = $("ticket-error");
  e.style.display = "";
  e.textContent = msg;
}

function renderTicket(r) {
  $("ticket-loading").style.display = "none";
  $("ticket-error").style.display = "none";
  $("ticket-body").style.display = "";

  const epsEl = $("tk-eps-val");
  epsEl.textContent = pct(r.accretion_dilution);
  epsEl.className = `tk-eps-val ${r.is_accretive ? "accretive" : "dilutive"}`;

  const ctx = r.synergy_context || {};
  const def = ctx.default_cost_synergy;
  const chips = $("tk-summary-chips");
  chips.textContent = "";
  addChip(chips, r.synergy_status_label, SYNERGY_CHIP_CLASS[r.synergy_status] || "");
  addChip(chips, def ? `默认协同：${tierLabel(def.synergy_tier)}` : "默认协同：不可用", "");
  addChip(chips, r.is_accretive ? "经济性：增厚" : "经济性：摊薄", r.is_accretive ? "econ-pos" : "econ-neg");
  const ppa = addChip(chips, `${r.pre_ppa_chip?.label || "Pre-PPA"} · 未计PPA`, "pre-ppa");
  ppa.title = r.pre_ppa_chip?.detail || "";

  const zero = ctx.zero_synergy_result || {};
  const mix = r.consideration_mix || {};
  const cells = [
    ["要约价值 / Offer Value", fmt(r.offer_value), `溢价 ${pct(r.premium, 0)}`],
    ["现金对价 / Cash", fmt(r.cash_consideration), `占要约 ${Math.round((mix.cash_pct || 0) * 100)}%`],
    ["股票对价 / Stock", fmt(r.stock_consideration), `占要约 ${Math.round((mix.stock_pct || 0) * 100)}%`],
    ["备考 EPS / Pro Forma EPS", fmt(r.pro_forma_eps, 2), "计入当前协同与融资后"],
    ["增厚/摊薄 / Accretion·Dilution", pct(r.accretion_dilution), r.is_accretive ? "EPS 增厚" : "EPS 摊薄"],
    ["打平所需协同 / Break-even", fmt(r.break_even_synergy), r.break_even_synergy <= 0 ? "无需协同" : "使 EPS 打平"],
    ["无协同 EPS 影响 / Zero-Synergy", pct(zero.accretion_dilution), `EPS ${fmt(zero.pro_forma_eps, 2)}`],
    ["当前协同 EPS 影响 / Current-Synergy", pct(r.accretion_dilution), `协同 ${fmt(r.synergy)} USD mm`],
  ];
  const grid = $("tk-econ-grid");
  grid.textContent = "";
  for (const [label, value, sub] of cells) {
    const cell = el("div", "tk-cell");
    cell.append(el("div", "tk-cell-label", label), el("div", "tk-cell-value", value), el("div", "tk-cell-sub", sub));
    grid.appendChild(cell);
  }

  renderTicketViability(r.viability_context);
}

function renderTicketViability(via) {
  const levelEl = $("tk-via-level");
  const summaryEl = $("tk-via-summary");
  const flagsEl = $("tk-via-flags");
  flagsEl.textContent = "";
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
    const card = el("div", `tk-flag ${f.severity || ""}`);
    const title = el("div", "tk-flag-title");
    title.appendChild(el("span", null, f.title || ""));
    title.appendChild(el("span", "tk-flag-cat", formatViaCategory(f.category)));
    title.appendChild(el("span", `tk-flag-sev ${f.severity || ""}`, formatViaSeverity(f.severity)));
    card.append(
      title,
      el("div", "tk-flag-msg", f.message || ""),
    );
    const triggerSummary = formatTriggeredSummary(f.triggered_tags);
    if (triggerSummary) {
      card.appendChild(el("div", "tk-flag-reason", `触发依据 · Trigger: ${triggerSummary}`));
    }
    if (f.rule_id || (f.triggered_tags || []).length) {
      const audit = el("details", "tk-flag-audit");
      const summary = el("summary", null, "Audit / Debug details");
      const body = el("div", "tk-flag-audit-body");
      const lines = [];
      if (f.rule_id) lines.push(`rule_id: ${f.rule_id}`);
      if ((f.triggered_tags || []).length) lines.push(`tags: ${(f.triggered_tags || []).join(", ")}`);
      body.textContent = lines.join("\n");
      audit.append(summary, body);
      card.appendChild(audit);
    }
    flagsEl.appendChild(card);
  }
}

// ── V5.8 Deal Review Queue · 候选交易队列 (compact play-table panel) ──────────
// Shared front-end-only shortlist (window.DealQueue, sessionStorage) — the SAME
// queue the War Room writes, so a deal saved in either place shows up here in the
// same tab/session. Adding reuses light data already on the table; it never
// triggers a calculate. Clear Deal does NOT touch the queue (it only resets the
// current selection). Safe DOM only (textContent), every id deck-validated.
const QUEUE_FROM_LABEL = {
  war_room: "War Room",
  play_table: "牌桌",
  ticket: "票据",
  settlement: "结算榜",
};

function tierClassName(t) {
  return ARENA_TIERS.has(t) ? t : "white";
}

function queueItemFrom(src, addedFrom) {
  if (!src) return null;
  const acqId = src.acquirer_id;
  const tgtId = src.target_id;
  const acqCard = companyById(acqId);
  const tgtCard = companyById(tgtId);
  if (!acqCard || !tgtCard || acqId === tgtId) return null;
  return {
    acquirer_id: acqId,
    acquirer_ticker: acqCard.ticker,
    acquirer_name: acqCard.name,
    acquirer_tier: arenaTier(acqCard),
    acquirer_tier_label: acqCard.arena_tier_label || "Basic",
    target_id: tgtId,
    target_ticker: tgtCard.ticker,
    target_name: tgtCard.name,
    target_tier: arenaTier(tgtCard),
    target_tier_label: tgtCard.arena_tier_label || "Basic",
    accretion_dilution_pct: src.accretion_dilution_pct,
    is_accretive: !!src.is_accretive,
    economic_label: src.is_accretive ? "经济性：增厚" : "经济性：摊薄",
    synergy_status: src.synergy_status,
    synergy_status_label: src.synergy_status_label,
    default_synergy_tier: src.default_synergy_tier || null,
    viability_level: src.viability_level || "green",
    viability_label: src.viability_label || "",
    pre_ppa: true,
    added_from: addedFrom,
  };
}

function addCurrentToQueue(addedFrom) {
  if (!currentLight || !selected.acq || !selected.tgt) return;
  const item = queueItemFrom(
    Object.assign({}, currentLight, { acquirer_id: selected.acq, target_id: selected.tgt }),
    addedFrom,
  );
  if (!item) return;
  if (window.DealQueue.has(item.acquirer_id, item.target_id)) {
    flashHint("已在候选队列 · Already in Deal Review Queue。");
    updateQueueButtons();
    return;
  }
  const res = window.DealQueue.add(item);
  if (!res.ok && res.reason === "full") flashHint("候选队列已满，先移除一些再加入。");
}

function updateQueueButtons() {
  const inQueue = !!(selected.acq && selected.tgt) &&
    window.DealQueue.has(selected.acq, selected.tgt);
  const enabled = !!(selected.acq && selected.tgt && currentLight);
  for (const id of ["rc-queue-btn", "tk-queue-btn"]) {
    const btn = $(id);
    if (!btn) continue;
    btn.disabled = inQueue || !enabled;
    btn.textContent = inQueue ? "已在候选 ✓" : "加入候选 · Add to Queue";
  }
}

function loadQueueItem(it) {
  if (!companyById(it.acquirer_id) || !companyById(it.target_id)) {
    flashHint("该候选公司不在当前牌堆中。");
    return;
  }
  setDeal(it.acquirer_id, it.target_id); // shared funnel: validates + refreshes
}

function buildQueueRow(it) {
  const row = el("div", "q-row");
  row.dataset.acq = it.acquirer_id;
  row.dataset.tgt = it.target_id;
  row.appendChild(el("span", "q-seq", `#${it.added_seq}`));

  const deal = el("span", "q-deal");
  const a = el("span", "a");
  a.appendChild(el("span", `tier-pip arena-tier tier-${tierClassName(it.acquirer_tier)}`));
  a.appendChild(document.createTextNode(it.acquirer_ticker || "—"));
  const t = el("span", "t");
  t.appendChild(el("span", `tier-pip arena-tier tier-${tierClassName(it.target_tier)}`));
  t.appendChild(document.createTextNode(it.target_ticker || "—"));
  deal.append(a, el("span", "ar", "→"), t);
  row.appendChild(deal);

  const epsText = pct(it.accretion_dilution_pct);
  row.appendChild(el("span", `q-eps ${epsText === "-" ? "na" : (it.is_accretive ? "accretive" : "dilutive")}`,
    epsText === "-" ? "—" : epsText));

  const rm = el("button", "q-remove", "✕");
  rm.type = "button";
  rm.title = "从候选移除";
  rm.setAttribute("aria-label", "移除该候选");
  rm.addEventListener("click", (e) => {
    e.stopPropagation();
    window.DealQueue.remove(it.acquirer_id, it.target_id);
  });
  row.appendChild(rm);

  row.addEventListener("click", () => loadQueueItem(it));
  return row;
}

function renderQueue(data) {
  const box = $("queue-list");
  if (!box) return;
  const rows = data || window.DealQueue.list();
  const badge = $("queue-count-badge");
  if (badge) badge.textContent = String(rows.length);
  const empty = $("queue-empty");
  box.textContent = "";
  if (!rows.length) {
    if (empty) empty.style.display = "";
  } else {
    if (empty) empty.style.display = "none";
    for (const it of rows) box.appendChild(buildQueueRow(it));
  }
  updateQueueButtons();
  updateRobotQueueButton();
}

// ── V5.9.0 Robot Opponent · 确定性机器人对手 ─────────────────────────────────
// A deterministic opponent that picks ONE deal from the SAME precomputed
// pairs already in PAIRS_INDEX, using window.RobotOpponent (no LLM, no network,
// no randomness). The robot generates no new financial judgement; it only ranks
// existing light fields. Its internal strategy_rank is never shown as an Overall
// Score and never enters the dual boards. Robot deals reuse the V5.8 Deal Review
// Queue and the V5.4 Deal Ticket — same number across light / ticket / calculate.
let robotDifficulty = window.RobotOpponent ? window.RobotOpponent.DEFAULT_DIFFICULTY : "analyst";
let robotResult = null;       // last { acquirer_id, target_id, difficulty, rationale, ... }
const robotRecentKeys = [];   // directed keys the robot already played this session

function robotPairList() {
  return Object.values(PAIRS_INDEX);
}

// Resolve a queue added_from into a display label (robot_* are dynamic).
function queueFromLabel(from) {
  if (from && from.indexOf("robot") === 0) {
    const meta = window.RobotOpponent && window.RobotOpponent.meta(from.replace("robot_", ""));
    return "机器人 · " + (meta ? meta.short : "Robot");
  }
  return QUEUE_FROM_LABEL[from] || "牌桌";
}

function setRobotDifficulty(d) {
  robotDifficulty = window.RobotOpponent ? window.RobotOpponent.normalizeDifficulty(d) : "analyst";
  document.querySelectorAll(".robot-diff-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.diff === robotDifficulty);
    b.setAttribute("aria-pressed", b.dataset.diff === robotDifficulty ? "true" : "false");
  });
  const meta = window.RobotOpponent && window.RobotOpponent.meta(robotDifficulty);
  const badge = $("robot-seat-badge");
  const state = $("robot-seat-state");
  if (badge && meta) badge.textContent = meta.badge;
  if (state && meta) state.textContent = `Robot · ${meta.short}`;
  const status = $("robot-status");
  if (status && meta) status.textContent = `已就坐：${meta.label}。点「机器人出牌」让它从 ${robotPairList().length} 对中选一笔。`;
}

function robotPlay() {
  const pairs = robotPairList();
  if (!pairs.length || !window.RobotOpponent) {
    const status = $("robot-status");
    if (status) status.textContent = "对局数据尚未就绪，请稍后再试。";
    return;
  }
  // Exclude pairs already in the queue OR already played by the robot this
  // session, so repeated clicks walk the deterministic ranking instead of
  // re-picking the same best deal. No randomness — pure next-best.
  const exclude = window.DealQueue.list().concat(robotRecentKeys.map((k) => {
    const parts = k.split("->");
    return { acquirer_id: parts[0], target_id: parts[1] };
  }));
  const res = window.RobotOpponent.selectRobotDeal(robotDifficulty, pairs, exclude, { cardById: companyById });
  if (!res) {
    // Everything got excluded — reset the robot's own recent memory and retry.
    robotRecentKeys.length = 0;
    const retry = window.RobotOpponent.selectRobotDeal(robotDifficulty, pairs, window.DealQueue.list(), { cardById: companyById });
    if (!retry) {
      const status = $("robot-status");
      if (status) status.textContent = "机器人暂时没有可出的牌（候选已覆盖全部组合）。";
      return;
    }
    robotResult = retry;
  } else {
    robotResult = res;
  }
  // Validate the returned ids against the deck before showing anything.
  if (!companyById(robotResult.acquirer_id) || !companyById(robotResult.target_id)) {
    robotResult = null;
    return;
  }
  const key = window.RobotOpponent.key(robotResult.acquirer_id, robotResult.target_id);
  if (robotRecentKeys.indexOf(key) < 0) robotRecentKeys.push(key);

  const seat = $("robot-seat");
  if (seat) {
    seat.classList.add("thinking");
    setTimeout(() => seat.classList.remove("thinking"), 320); // cosmetic only
  }
  renderRobotResult();
}

function robotResultPair() {
  if (!robotResult) return null;
  return PAIRS_INDEX[pairKey(robotResult.acquirer_id, robotResult.target_id)] || null;
}

function renderRobotResult() {
  const box = $("robot-result");
  if (!box || !robotResult) return;
  const pair = robotResultPair();
  const acqCard = companyById(robotResult.acquirer_id);
  const tgtCard = companyById(robotResult.target_id);
  box.style.display = "";

  const meta = window.RobotOpponent.meta(robotResult.difficulty);
  const badge = $("rr-diff-badge");
  if (badge) badge.textContent = meta ? meta.badge : "BOT";

  const acqEl = $("rr-acq");
  const tgtEl = $("rr-tgt");
  acqEl.textContent = acqCard ? acqCard.ticker : "—";
  tgtEl.textContent = tgtCard ? tgtCard.ticker : "—";
  clearArenaTierClasses(acqEl);
  clearArenaTierClasses(tgtEl);
  if (acqCard) { applyArenaTier(acqEl, acqCard); acqEl.classList.add("tier-text"); }
  if (tgtCard) { applyArenaTier(tgtEl, tgtCard); tgtEl.classList.add("tier-text"); }

  const epsText = pair ? pct(pair.accretion_dilution_pct) : "-";
  const epsEl = $("rr-eps");
  epsEl.textContent = epsText === "-" ? "数据不足" : epsText;
  epsEl.className = `rr-eps ${epsText === "-" ? "na" : (pair && pair.is_accretive ? "accretive" : "dilutive")}`;

  const chips = $("rr-chips");
  chips.textContent = "";
  for (const c of robotResult.rationale || []) {
    chips.appendChild(el("span", `rr-chip ${c.kind || ""}`.trim(), c.text));
  }

  const status = $("robot-status");
  if (status && meta) {
    status.textContent = `${meta.short} 出牌：${acqEl.textContent} → ${tgtEl.textContent}`;
  }
  updateRobotQueueButton();
}

function updateRobotQueueButton() {
  const btn = $("robot-queue-btn");
  if (!btn) return;
  const inQueue = robotResult &&
    window.DealQueue.has(robotResult.acquirer_id, robotResult.target_id);
  btn.disabled = !robotResult || !!inQueue;
  btn.textContent = inQueue ? "已在候选 ✓" : "加入候选 · Add to Queue";
}

function addRobotToQueue() {
  if (!robotResult) return;
  const pair = robotResultPair();
  if (!pair) return;
  const item = queueItemFrom(pair, `robot_${robotResult.difficulty}`);
  if (!item) return;
  if (window.DealQueue.has(item.acquirer_id, item.target_id)) {
    flashHint("已在候选队列 · Already in Deal Review Queue。");
    updateRobotQueueButton();
    return;
  }
  window.DealQueue.add(item);
}

function loadRobotToTable() {
  if (!robotResult) return;
  loadQueueItem({ acquirer_id: robotResult.acquirer_id, target_id: robotResult.target_id });
}

function robotViewTicket() {
  if (!robotResult) return;
  if (!companyById(robotResult.acquirer_id) || !companyById(robotResult.target_id)) return;
  setDeal(robotResult.acquirer_id, robotResult.target_id);
  openTicket();
}

async function init() {
  $("reverse-btn").addEventListener("click", reverseDirection);
  $("clear-deal-btn").addEventListener("click", clearSelection);
  $("rc-ticket-btn").addEventListener("click", openTicket);
  $("rc-queue-btn").addEventListener("click", () => addCurrentToQueue("play_table"));
  $("tk-queue-btn").addEventListener("click", () => addCurrentToQueue("ticket"));
  document.querySelectorAll(".robot-diff-btn").forEach((b) => {
    b.addEventListener("click", () => setRobotDifficulty(b.dataset.diff));
  });
  $("robot-play-btn").addEventListener("click", robotPlay);
  $("robot-queue-btn").addEventListener("click", addRobotToQueue);
  $("robot-load-btn").addEventListener("click", loadRobotToTable);
  $("robot-ticket-btn").addEventListener("click", robotViewTicket);
  setRobotDifficulty(robotDifficulty);
  $("ticket-close").addEventListener("click", closeTicket);
  $("ticket-overlay").addEventListener("click", (e) => { if (e.target.id === "ticket-overlay") closeTicket(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeTicket(); });
  $("hand-draw").addEventListener("click", drawOne);
  $("hand-rotate").addEventListener("click", rotateHand);
  const pile = $("draw-pile");
  pile.addEventListener("click", drawOne);
  pile.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drawOne(); } });
  document.querySelectorAll(".pb-tab").forEach((b) => b.addEventListener("click", () => setMiniTab(b.dataset.board)));
  attachSlotDropZone($("slot-acq"), "acq");
  attachSlotDropZone($("slot-tgt"), "tgt");

  window.DealQueue.subscribe(renderQueue);
  renderQueue();

  await Promise.all([loadCards(), loadPairs()]);
  setRobotDifficulty(robotDifficulty);
  renderMiniBoards();
  drawHand();
  deepLinkInit();
}

document.addEventListener("DOMContentLoaded", init);
