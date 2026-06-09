// V5.9.2 Deal Arena · Match table (five-round game loop).
//
// The formal match: same real seed deck, same precomputed pairs, same
// deterministic A/D engine and same Deal Ticket / Deal Review Queue as the War
// Room and the sandbox Play Table. It re-implements NO economics — the light
// result is a precomputed PAIRS_INDEX lookup and the Deal Ticket reuses
// /api/modeling/ma/calculate. The GAME LOOP (round flow, two seated robots, the
// local Match Points scoreboard, the settlement end screen) lives in
// window.MatchEngine (pure) and is wired here.
//
// Hard boundaries: no LLM, no event cards, no resource system, no merged score,
// no backend per-user state, no randomness, no runtime fetch/LLM/plugin. Match
// Points is a LOCAL game score only — it never enters the Economic/Viability
// boards or the calculate API. Robots are the SAME deterministic RobotOpponent;
// the only calculate fetches are the single-deal fallback and the Deal Ticket.

const API = "";

const ARENA_DEAL_TERMS = {
  deal_type: "full_acquisition",
  premium: 0.30,
  cash_pct: 0.5,
  stock_pct: 0.5,
  financing_cost: 0.05,
  tax_rate: 0.25,
  synergy_mode: "default",
};

const SETUP_STORAGE_KEY = "ma_match_setup_v1";
const MATCH_STATE_KEY = "ma_match_state_v1";

let CARDS = [];
let PAIRS_INDEX = {};
let selected = { acq: null, tgt: null };
let currentLight = null;

// V5.9.4 hand lifecycle. HAND mirrors MATCH.hand (the live player hand, by id).
// Played companies move into MATCH.used_cards and never return; deck_cursor walks
// the deterministic deck order so Draw / Reshuffle / round-refresh skip used cards.
let HAND = [];
const HAND_SIZE = 7;       // target player hand size each round
const RETAIN_MAX = 4;      // most cards a player may keep across a round transition
const REFRESH_COUNT = 3;   // canonical new cards drawn at a transition (keep 4 -> +3 = 7)
let DRAG_ID = null;

// V5.9.4 player-visible opponent personas — NEVER "机器人1/2" or "ROBOT · …".
// Internal state ids stay robot_1 / robot_2; only the visible copy is the persona.
const PERSONA = {
  intern: { title: "实习生", sub: "Intern" },
  analyst: { title: "分析师", sub: "Analyst" },
  associate: { title: "高级分析师", sub: "Associate" },
  vp: { title: "副总裁", sub: "VP" },
  md: { title: "董事总经理", sub: "MD" },
};
function personaOf(diff) {
  const norm = (window.MatchEngine && window.MatchEngine.normalizeDifficulty)
    ? window.MatchEngine.normalizeDifficulty(diff) : diff;
  return PERSONA[norm] || PERSONA.analyst;
}

// The live match state (window.MatchEngine shape). Created from the setup config.
let MATCH = null;
let MATCH_CONFIG = null;

// V5.10.2 presentation-only banker identities (robot_1 / robot_2 display layer).
let OPPONENT_IDS = null;
function refreshOpponentIdentities() {
  if (!window.OpponentIdentity || !MATCH) { OPPONENT_IDS = null; return; }
  OPPONENT_IDS = window.OpponentIdentity.buildForMatch(MATCH);
}
function opponentIdentity(id) {
  if (!OPPONENT_IDS || id === "player") return null;
  return OPPONENT_IDS[id] || null;
}
function renderSigil(host, identity, size) {
  if (!host || !window.OpponentIdentity) return;
  host.textContent = "";
  if (!identity) return;
  const node = window.OpponentIdentity.makeSigilNode(identity, size);
  const rc = window.OpponentIdentity.rankClass(identity.difficulty);
  if (rc) node.classList.add(rc);
  host.appendChild(node);
}
const RANK_VIS_CLASSES = ["rank-intern", "rank-analyst", "rank-associate", "rank-vp", "rank-md"];
function applyRankVisual(node, difficulty) {
  if (!node || !window.OpponentIdentity) return;
  RANK_VIS_CLASSES.forEach((c) => node.classList.remove(c));
  const rc = window.OpponentIdentity.rankClass(difficulty);
  if (rc) node.classList.add(rc);
}

const $ = (id) => document.getElementById(id);
const companyById = (id) => CARDS.find((c) => c.id === id) || null;
const pairKey = (acq, tgt) => `${acq}__${tgt}`;
const getPair = (acq, tgt) => PAIRS_INDEX[pairKey(acq, tgt)] || null;
const ARENA_TIERS = new Set(["gold", "red", "blue", "green", "white"]);

function arenaTier(c) { return ARENA_TIERS.has(c?.arena_tier) ? c.arena_tier : "white"; }
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
function signed(n) { return `${n >= 0 ? "+" : ""}${n}`; }
function tierLabel(tier) { return { high: "高", medium: "中", low: "低", none: "无" }[tier] || "-"; }
function marketCapSense(company) {
  const cap = Number(company.share_price) * Number(company.shares);
  if (!isFinite(cap) || cap <= 0) return "-";
  if (cap >= 1_000_000) return `$${(cap / 1_000_000).toFixed(2)}T`;
  return `$${fmt(cap)}B`;
}
function prettyTag(tag) { return String(tag || "").replace(/_/g, " "); }

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
const VIA_SEVERITY_LABEL = { red: "高风险 · High", yellow: "需审查 · Review", green: "通过 · Clear" };
function formatViaCategory(cat) { return VIA_CATEGORY_LABEL[cat] || prettyTag(cat); }
function formatViaSeverity(sev) { return VIA_SEVERITY_LABEL[sev] || sev || "—"; }
function formatTriggeredSummary(tags) {
  const list = (tags || []).filter(Boolean);
  if (!list.length) return "";
  return list.map(prettyTag).join(" · ");
}

// ── Data loading ────────────────────────────────────────────────────────────
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
  } catch (e) {
    PAIRS_INDEX = {};
    console.info("[match] pairs map unavailable; will use calculate fallback");
  }
}

// ── Hand cards (safe DOM; draggable + drop target) ──────────────────────────
function buildHandCard(c) {
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

// ── V5.9.4 deterministic eligible-card draw (used cards never return) ────────
function usedSet() {
  return new Set(Array.isArray(MATCH && MATCH.used_cards) ? MATCH.used_cards : []);
}
// V5.9.6.2 per-match draw pool = a SEEDED shuffle of the deck ids (the opening
// hand and every later draw come from this order, so a new match deals a
// different opening hand while a given match stays replayable/restorable). Built
// lazily once CARDS are loaded; validated against the current deck and rebuilt if
// it is missing/stale (graceful for legacy or corrupt restored state).
function drawPool() {
  if (!MATCH || !Array.isArray(CARDS) || !CARDS.length) return [];
  const order = Array.isArray(MATCH.draw_order) ? MATCH.draw_order.filter((id) => companyById(id)) : [];
  if (order.length === CARDS.length) { MATCH.draw_order = order; return order; }
  const seed = (typeof MATCH.match_seed === "number" && isFinite(MATCH.match_seed)) ? MATCH.match_seed : 1;
  MATCH.draw_order = window.MatchEngine.buildDrawOrder(seed, CARDS.map((c) => c.id));
  return MATCH.draw_order;
}
// Walk the seeded draw order from MATCH.deck_cursor and return up to `count` ids
// that are NOT used, NOT already in hand, and NOT in `excludeIds`. Each card is
// scanned at most once per call, so an exhausted pool degrades gracefully
// (returns fewer ids) instead of looping forever or crashing.
function drawEligible(count, excludeIds) {
  if (!MATCH || !Array.isArray(CARDS) || !CARDS.length) return [];
  const pool = drawPool();
  if (!pool.length) return [];
  if (typeof MATCH.deck_cursor !== "number" || !isFinite(MATCH.deck_cursor)) MATCH.deck_cursor = 0;
  const used = usedSet();
  const inHand = new Set(Array.isArray(MATCH.hand) ? MATCH.hand : []);
  const ex = new Set(excludeIds || []);
  const out = [];
  const N = pool.length;
  let scanned = 0;
  while (out.length < count && scanned < N) {
    const id = pool[((MATCH.deck_cursor % N) + N) % N];
    MATCH.deck_cursor = (MATCH.deck_cursor + 1) % N;
    scanned++;
    if (!id || !companyById(id)) continue;
    if (used.has(id) || inHand.has(id) || ex.has(id) || out.indexOf(id) >= 0) continue;
    out.push(id);
  }
  return out;
}
// Deal a fresh full hand from the top of the deck (used cards excluded). Resets
// the round-transition state for a brand-new match / Play Again.
function initialDeal() {
  if (!MATCH) return;
  if (typeof MATCH.deck_cursor !== "number" || !isFinite(MATCH.deck_cursor)) MATCH.deck_cursor = 0;
  if (!Array.isArray(MATCH.used_cards)) MATCH.used_cards = [];
  MATCH.hand = [];
  HAND = MATCH.hand;
  const ids = drawEligible(HAND_SIZE);
  MATCH.hand = ids;
  HAND = MATCH.hand;
  renderHand();
}
// Use the restored hand when one exists (dropping any now-invalid / used ids),
// otherwise deal a fresh hand. Never auto-tops-up so a restored mid-round-result
// hand (5 cards after a play) keeps its size until the retain step.
function ensureHand() {
  if (!MATCH) return;
  if (typeof MATCH.deck_cursor !== "number" || !isFinite(MATCH.deck_cursor)) MATCH.deck_cursor = 0;
  if (!Array.isArray(MATCH.used_cards)) MATCH.used_cards = [];
  if (Array.isArray(MATCH.hand) && MATCH.hand.length) {
    const used = usedSet();
    MATCH.hand = MATCH.hand.filter((id) => companyById(id) && !used.has(id));
    HAND = MATCH.hand;
    renderHand();
  } else {
    initialDeal();
  }
}

// V5.9.3 Draw is a per-round resource (max 1/round). V5.9.4: it swaps the oldest
// hand card for one fresh eligible card (used cards are never redrawn).
function drawOne() {
  if (!CARDS.length || !MATCH) return;
  if (!window.MatchEngine.canDraw(MATCH)) {
    flashHint("本回合的抽牌次数已用完，下一回合恢复。");
    updateResourceButtons();
    return;
  }
  const picks = drawEligible(1);
  if (!picks.length) { flashHint("没有可补充的新公司牌了。"); return; }
  window.MatchEngine.useDraw(MATCH);
  if (MATCH.hand.length >= HAND_SIZE) MATCH.hand.shift();
  MATCH.hand.push(picks[0]);
  HAND = MATCH.hand;
  renderHand();
  persistMatch();
  updateResourceButtons();
  updatePlayDealButton();
}
// V5.9.3 Reshuffle is a whole-match resource (max 2 across the five rounds).
// V5.9.4: the current (non-used) hand returns to the pool and a fresh full hand
// is drawn from the next eligible cards; used cards are still excluded.
function rotateHand() {
  if (!CARDS.length || !MATCH) return;
  if (!window.MatchEngine.canReshuffle(MATCH)) {
    flashHint("本局的换牌次数已用完。");
    updateResourceButtons();
    return;
  }
  MATCH.hand = [];
  HAND = MATCH.hand;
  const ids = drawEligible(HAND_SIZE);
  MATCH.hand = ids;
  HAND = MATCH.hand;
  window.MatchEngine.useReshuffle(MATCH);
  renderHand();
  persistMatch();
  updateResourceButtons();
  updatePlayDealButton();
}

// Reflect the remaining Draw / Reshuffle allowances on the hand controls (count
// in the label, disabled when exhausted). The draw pile mirrors the Draw state.
function updateResourceButtons() {
  if (!MATCH || !window.MatchEngine) return;
  const drawLeft = window.MatchEngine.drawRemaining(MATCH);
  const reshLeft = window.MatchEngine.reshuffleRemaining(MATCH);
  const drawBtn = $("hand-draw");
  if (drawBtn) {
    drawBtn.textContent = `抽一张 · Draw (${drawLeft}/${window.MatchEngine.DRAW_PER_ROUND})`;
    drawBtn.disabled = drawLeft <= 0;
  }
  const reshBtn = $("hand-rotate");
  if (reshBtn) {
    reshBtn.textContent = `换一批 · Reshuffle (${reshLeft} left)`;
    reshBtn.disabled = reshLeft <= 0;
  }
  const pile = $("draw-pile");
  if (pile) {
    const depleted = drawLeft <= 0;
    pile.classList.toggle("depleted", depleted);
    pile.setAttribute("aria-disabled", depleted ? "true" : "false");
  }
}

// V5.9.3 hand-validity: a deal is playable only when BOTH companies are in the
// current player hand (an id set check), the pair has a light result, and it is
// the player's turn. `handHas` is a pure local hand-id membership check.
function handHas(id) { return HAND.indexOf(id) >= 0; }
function isUsed(id) { return usedSet().has(id); }
// A candidate deal is PLAYABLE only when it is the player's turn, the selection
// is complete + non-self, the pair has a light result, BOTH companies are in the
// live current hand, AND neither has already gone to this match's used pile.
// (Used cards are pulled from the hand, so handHas already covers them; the
// explicit used guard keeps the rule self-documenting and crash-safe.)
function dealPlayable() {
  if (!MATCH || !window.MatchEngine) return { ok: false, reason: "no_match" };
  const P = window.MatchEngine.PHASE;
  if (MATCH.phase === P.MATCH_COMPLETE) return { ok: false, reason: "complete" };
  if (MATCH.phase !== P.WAITING_PLAYER) return { ok: false, reason: "phase" };
  if (!selected.acq || !selected.tgt) return { ok: false, reason: "incomplete" };
  if (selected.acq === selected.tgt) return { ok: false, reason: "self" };
  if (!getPair(selected.acq, selected.tgt)) return { ok: false, reason: "no_pair" };
  if (isUsed(selected.acq) || isUsed(selected.tgt)) return { ok: false, reason: "used" };
  if (!handHas(selected.acq) || !handHas(selected.tgt)) return { ok: false, reason: "not_in_hand" };
  return { ok: true };
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
  updatePlayDealButton();
}
function flashHint(msg) {
  const h = $("deal-hint");
  if (h) h.textContent = msg;
}
function onCardClick(id) {
  if (!companyById(id)) return;
  if (selected.acq === id) { selected.acq = selected.tgt; selected.tgt = null; }
  else if (selected.tgt === id) { selected.tgt = null; }
  else if (!selected.acq) { selected.acq = id; }
  else if (!selected.tgt) { selected.tgt = id; }
  else { selected.tgt = id; }
  applySelection();
}
function reverseDirection() {
  if (!selected.acq || !selected.tgt) return;
  setDeal(selected.tgt, selected.acq);
}
// Clear Deal only resets the current table selection. It NEVER touches the match
// state (rounds / played deals / score) or the Deal Review Queue.
function clearSelection() {
  selected = { acq: null, tgt: null };
  ticketReqId += 1;
  showError("");
  applySelection();
}
// V5.9.6.2: the Match no longer deep-links a deal from the URL. Start Match is a
// formal new game with a clean deal table, so the War Room's current selection
// (passed as ?acq/?tgt) is intentionally ignored. (Queue still persists across
// pages, but a queued deal is preview/load only — it never auto-seats the table.)

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
  const light = getPair(selected.acq, selected.tgt);
  if (light) { renderLight(light); return; }
  await calculateFallback();
}
async function calculateFallback() {
  console.info("[match] precomputed pair missing; falling back to /api/modeling/ma/calculate", selected);
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
    viability_flags_count: (via.flags || []).filter((f) => f.severity !== "green").length,
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

  // Local Match Points preview for this candidate deal (game score only).
  const mp = window.MatchEngine ? window.MatchEngine.matchPoints(p, companyById) : 0;
  $("rc-mp-badge").textContent = signed(mp);

  const chips = $("rc-chips");
  chips.textContent = "";
  addChip(chips, p.synergy_status_label, SYNERGY_CHIP_CLASS[p.synergy_status] || "");
  addChip(chips, p.default_synergy_tier ? `默认协同：${tierLabel(p.default_synergy_tier)}` : "默认协同：不可用", "");
  addChip(chips, p.is_accretive ? "经济性：增厚" : "经济性：摊薄", p.is_accretive ? "econ-pos" : "econ-neg");
  const ppa = addChip(chips, `${p.pre_ppa_chip?.label || "Pre-PPA"} · 未计PPA`, "pre-ppa");
  ppa.title = p.pre_ppa_chip?.detail || "";

  renderViability(p);
  // V5.10.4.x: no Deal Studio jump from Match Play (leaving resets the match).
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

function showError(msg) {
  const e = $("error-panel");
  if (!msg) { e.style.display = "none"; e.textContent = ""; return; }
  e.style.display = "block";
  e.textContent = msg;
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
  // V5.10.4.x: Deal Ticket no longer deep-links to Deal Studio in Match Play.
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
    card.append(title, el("div", "tk-flag-msg", f.message || ""));
    const triggerSummary = formatTriggeredSummary(f.triggered_tags);
    if (triggerSummary) card.appendChild(el("div", "tk-flag-reason", `触发依据 · Trigger: ${triggerSummary}`));
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

// ── Deal Review Queue (shared light shortlist; same module as War Room) ──────
function tierClassName(t) { return ARENA_TIERS.has(t) ? t : "white"; }
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
// Add a played deal (player or robot) to the queue by its directed ids — used by
// the end-screen compact review chips and the "Add Best Deals" button.
function addDealToQueue(acqId, tgtId, addedFrom) {
  const pair = getPair(acqId, tgtId);
  if (!pair) return false;
  if (window.DealQueue.has(acqId, tgtId)) return false;
  const item = queueItemFrom(pair, addedFrom);
  if (!item) return false;
  const res = window.DealQueue.add(item);
  return !!(res && res.ok);
}
function updateQueueButtons() {
  const inQueue = !!(selected.acq && selected.tgt) && window.DealQueue.has(selected.acq, selected.tgt);
  const enabled = !!(selected.acq && selected.tgt && currentLight);
  for (const id of ["rc-queue-btn", "tk-queue-btn"]) {
    const btn = $(id);
    if (!btn) continue;
    btn.disabled = inQueue || !enabled;
    btn.textContent = inQueue ? "已在候选 ✓" : "加入候选 · Add to Queue";
  }
}
function loadQueueItem(it) {
  if (!it || !companyById(it.acquirer_id) || !companyById(it.target_id)) {
    flashHint("该候选公司不在当前牌堆中。");
    return;
  }
  // V5.9.4 a queue deal always loads for preview / Ticket / review. The hint is
  // (re)computed from the LIVE current hand + used pile EVERY time, so a deal
  // whose companies are both in hand shows the positive "playable" hint (never a
  // stale "not in hand" warning left over from a previous load), and an
  // out-of-hand / used deal always shows why it cannot be played this round.
  setDeal(it.acquirer_id, it.target_id);
  const outOfHand = !handHas(it.acquirer_id) || !handHas(it.target_id);
  if (isUsed(it.acquirer_id) || isUsed(it.target_id)) {
    flashHint("这笔候选交易的公司已在本局打出（进入弃用堆），本局无法再次打出，但仍可预览 / 看票据。");
  } else if (outOfHand) {
    flashHint("这笔候选交易需要的公司不在当前手牌中，可预览 / 看票据，但不能本回合打出。");
  } else {
    flashHint("这笔候选交易就在你的当前手牌内，可直接「打出交易」。");
  }
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
  rm.addEventListener("click", (e) => { e.stopPropagation(); window.DealQueue.remove(it.acquirer_id, it.target_id); });
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
}

// ── Match state persistence (front-end session only; light records) ─────────
function persistMatch() {
  try { sessionStorage.setItem(MATCH_STATE_KEY, JSON.stringify(MATCH)); }
  catch (_) { /* private mode: refresh just loses the in-progress match */ }
}
function loadSetupConfig() {
  try {
    const raw = sessionStorage.getItem(SETUP_STORAGE_KEY);
    if (raw) {
      const cfg = JSON.parse(raw);
      if (cfg && Array.isArray(cfg.robots)) return cfg;
    }
  } catch (_) {}
  // No setup found (deep entry / private mode): default two robots so the page
  // is still playable. Illegal difficulties normalize to Analyst in the engine.
  return { v: 1, robots: [{ seat: 1, difficulty: "analyst" }, { seat: 2, difficulty: "vp" }] };
}
function restoreMatchState(config) {
  try {
    const raw = sessionStorage.getItem(MATCH_STATE_KEY);
    if (!raw) return null;
    const st = JSON.parse(raw);
    if (st && st.match_started && st.participants && Array.isArray(st.rounds)) return st;
  } catch (_) {}
  return null;
}

// V5.9.6.2 fresh per-match game seed (crypto preferred; deterministic-after-pick).
// This seeds the card shuffle ONLY — never any financial result. Once chosen, the
// whole match's dealing is deterministic. The rare non-crypto fallback mixes
// wall-clock, high-res time and a per-session counter (no PRNG) so back-to-back
// new matches still get distinct seeds.
let seedCounter = 0;
function freshSeed() {
  try {
    if (window.crypto && window.crypto.getRandomValues) {
      const a = new Uint32Array(1);
      window.crypto.getRandomValues(a);
      return a[0] >>> 0;
    }
  } catch (_) {}
  const hi = (typeof performance !== "undefined" && performance.now) ? Math.floor(performance.now() * 1000) : 0;
  seedCounter = (seedCounter + 0x9E3779B1) >>> 0;
  return (((Date.now() >>> 0) ^ (hi >>> 0) ^ seedCounter) >>> 0) || 1;
}
// Start a brand-new match: a clean engine state PLUS a fresh seed and an empty
// draw order (filled lazily once the deck loads). Used for Start Match and Play
// Again so old used_cards / deck order / round state never bleed into a new game.
function startNewMatch(config) {
  const m = window.MatchEngine.createMatch(config);
  m.match_seed = freshSeed();
  m.draw_order = [];
  m.deck_cursor = 0;
  m.used_cards = [];
  return m;
}

// ── Opponent seats + scoreboard ─────────────────────────────────────────────
// V5.10.2: banker display name + rank + sigil; internal ids stay robot_1/robot_2.
function renderSeats() {
  refreshOpponentIdentities();
  for (const seat of [1, 2]) {
    const id = `robot_${seat}`;
    const p = MATCH.participants[id];
    const ident = opponentIdentity(id);
    const persona = personaOf(p.difficulty);
    const seatName = $(`seat-name-${seat}`);
    const badge = $(`seat-${seat}-badge`);
    const scoreName = $(`score-name-robot-${seat}`);
    const scoreRank = $(`score-rank-robot-${seat}`);
    const fig = $(`seat-fig-${seat}`);
    const scoreSigil = $(`score-sigil-robot-${seat}`);
    const diff = ident ? ident.difficulty : p.difficulty;
    const seatEl = $(`seat-robot-${seat}`);
    const scoreChip = $(`score-chip-robot-${seat}`);
    applyRankVisual(seatEl, diff);
    applyRankVisual(scoreChip, diff);
    if (ident) {
      if (seatName) seatName.textContent = ident.displayName;
      if (badge) badge.textContent = ident.rankEn;
      if (scoreName) scoreName.textContent = ident.displayName;
      if (scoreRank) scoreRank.textContent = ident.rankCn;
      renderSigil(fig, ident, 36);
      renderSigil(scoreSigil, ident, 30);
    } else {
      if (seatName) seatName.textContent = persona.title;
      if (badge) badge.textContent = persona.sub;
      if (scoreName) scoreName.textContent = persona.title;
      if (scoreRank) scoreRank.textContent = `席位 ${seat}`;
      if (fig) fig.textContent = "";
      if (scoreSigil) scoreSigil.textContent = "";
    }
  }
}
function setSeatState(seat, text, cls) {
  const el2 = $(`seat-${seat}-state`);
  if (el2) el2.textContent = text;
  const seatEl = $(`seat-robot-${seat}`);
  if (seatEl) {
    seatEl.classList.remove("active-turn", "played", "thinking", "winner-emphasis");
    if (cls) seatEl.classList.add(cls);
  }
}
// V5.10.2.3 (re-probe): the seat avatar dot + ring (.winner-emphasis) are BOTH
// transient and mark ONLY the current round winner — always clear before any
// re-apply so a prior round's winner cannot stick to a banker's avatar. The old
// `.leading` cumulative-leader seat pip is gone (it welded a dot to the round-1
// winner for the rest of the match); the total leader now lives ONLY on the
// scoreboard chip glow (renderScoreboard → .score-chip.lead). We still strip the
// legacy `leading` class defensively in case a stale DOM carries it.
function clearSeatTransientState() {
  for (const seat of [1, 2]) {
    const seatEl = $(`seat-robot-${seat}`);
    if (seatEl) seatEl.classList.remove("leading", "winner-emphasis");
  }
}
// Cumulative unique total leader (engine truth; null on tie / nobody > 0). Used
// ONLY by the scoreboard chip glow — never to place a seat dot.
function matchLeaderId() {
  if (!MATCH || !window.MatchEngine) return null;
  const w = window.MatchEngine.winner(MATCH);
  if (w === "draw" || !w) return null;
  const pts = MATCH.participants[w] ? MATCH.participants[w].points : 0;
  return pts > 0 ? w : null;
}
function emphasizeWinnerSeat(winnerId) {
  if (!winnerId || winnerId === "draw" || winnerId === "player") return;
  const seat = winnerId === "robot_2" ? 2 : 1;
  const seatEl = $(`seat-robot-${seat}`);
  if (seatEl) seatEl.classList.add("winner-emphasis");
}
// Clear all transient seat state, then re-apply ONLY the current round winner
// (none on a draw, or when there is no settled round result for this turn).
function refreshSeatPresence(roundRec) {
  clearSeatTransientState();
  if (roundRec && window.MatchEngine) {
    emphasizeWinnerSeat(window.MatchEngine.roundWinner(roundRec));
  }
}
// Participant ids use underscores (`robot_1`); the scoreboard DOM ids use hyphens
// (`score-robot-1`) to match the seat/badge/role ids. Bridge the two so the
// in-match robot tallies actually refresh (they previously stuck at 0 MP).
function scoreDomId(id) { return id.replace("_", "-"); }
// Write one participant's running MP total (used by the sequential robot reveal
// so the scoreboard ticks up opponent-by-opponent, not all at once).
function setScoreSpan(id) {
  const span = $(`score-${scoreDomId(id)}`);
  if (span && MATCH && MATCH.participants[id]) span.textContent = String(MATCH.participants[id].points);
}
function renderScoreboard() {
  const leadId = matchLeaderId();
  for (const id of ["player", "robot_1", "robot_2"]) {
    const dom = scoreDomId(id);
    const span = $(`score-${dom}`);
    if (span) span.textContent = String(MATCH.participants[id].points);
    const chip = $(`score-chip-${dom}`);
    if (chip) chip.classList.toggle("lead", leadId === id);
  }
}
function renderRoundPill() {
  const pill = $("match-round-pill");
  if (pill) pill.textContent = `回合 ${MATCH.round_index} / ${MATCH.max_rounds}`;
}

// ── Turn loop ───────────────────────────────────────────────────────────────
function setPlayChip(kind, text) {
  const chip = $("play-state-chip");
  if (!chip) return;
  chip.textContent = text;
  chip.className = `play-state-chip ${kind}`;
  chip.style.display = "";
}

function updatePlayDealButton() {
  const btn = $("play-deal-btn");
  if (!btn || !MATCH || !window.MatchEngine) return;
  const P = window.MatchEngine.PHASE;
  const state = dealPlayable();
  btn.disabled = !state.ok;
  const status = $("turn-status");
  const setStatus = (t) => { if (status) status.textContent = t; };

  if (MATCH.phase === P.ROBOTS_PLAYING) {
    setStatus("对手正在依次应对出牌…");
    setPlayChip("wait", "对手回合");
    return;
  }
  if (MATCH.phase === P.ROUND_RESULT) {
    setStatus("本回合结束，查看右侧结果后点「下一回合」。");
    setPlayChip("wait", "本回合已结束");
    return;
  }
  if (MATCH.phase === P.MATCH_COMPLETE) {
    setStatus("对局已结束，查看结算。");
    setPlayChip("blocked", "对局已结束 · Match complete");
    return;
  }
  // waiting_player: the turn status + chip explain whether the deal is playable.
  if (state.ok) {
    setStatus("已就位一笔来自手牌的交易，点「打出交易」结束你的回合。");
    setPlayChip("ok", "可打出 · Playable");
    return;
  }
  const STATUS_BY_REASON = {
    incomplete: "你的回合：选好买方与标的，然后点「打出交易」。",
    self: "同一家公司不能并购自己，换一笔交易。",
    no_pair: "该组合暂无轻结果，换一笔交易再打出。",
    not_in_hand: "这笔候选交易需要的公司不在当前手牌中，不能本回合打出（可预览 / 看票据 / 留在候选）。",
    used: "这笔交易的公司已在本局打出（进入弃用堆），本局无法再次打出。",
  };
  const CHIP_BY_REASON = {
    incomplete: ["wait", "待选择"],
    self: ["blocked", "同一家公司"],
    no_pair: ["wait", "无轻结果"],
    not_in_hand: ["blocked", "不在手牌 · Not in hand"],
    used: ["blocked", "已打出 · Used"],
  };
  setStatus(STATUS_BY_REASON[state.reason] || STATUS_BY_REASON.incomplete);
  const chip = CHIP_BY_REASON[state.reason] || CHIP_BY_REASON.incomplete;
  setPlayChip(chip[0], chip[1]);
}

// ── Used-card lifecycle (controller-owned; the engine stays hand-agnostic) ──
// A successfully played deal consumes both companies: they leave the hand and
// enter MATCH.used_cards. Used cards never come back via Draw / Reshuffle /
// round refresh. Robots do NOT touch this pile (they pick over all pairs).
function markPlayerUsed(acqId, tgtId) {
  if (!MATCH) return;
  if (!Array.isArray(MATCH.used_cards)) MATCH.used_cards = [];
  if (!Array.isArray(MATCH.hand)) MATCH.hand = [];
  for (const id of [acqId, tgtId]) {
    if (!id) continue;
    if (MATCH.used_cards.indexOf(id) < 0) MATCH.used_cards.push(id);
    const i = MATCH.hand.indexOf(id);
    if (i >= 0) MATCH.hand.splice(i, 1);
  }
  HAND = MATCH.hand;
  renderHand();
}

function playDeal() {
  if (!MATCH || MATCH.phase !== window.MatchEngine.PHASE.WAITING_PLAYER) return;
  // V5.9.4 the player can only play a deal whose BOTH companies are in hand and
  // not already used this match.
  const state = dealPlayable();
  if (!state.ok) {
    if (state.reason === "incomplete") flashHint("先选好买方与标的，再打出交易。");
    else if (state.reason === "not_in_hand") flashHint("这笔交易的公司不在当前手牌中，不能本回合打出。");
    else if (state.reason === "used") flashHint("这笔交易的公司已在本局打出，本局无法再次打出。");
    else flashHint("这笔交易暂时无法打出，换一笔再试。");
    return;
  }
  const res = window.MatchEngine.playerPlay(MATCH, selected.acq, selected.tgt, getPair, companyById);
  if (!res.ok) { flashHint("这笔交易暂时无法打出，换一笔再试。"); return; }
  // Consume the two played companies (hand -> used pile) and reset the table.
  markPlayerUsed(selected.acq, selected.tgt);
  $("play-deal-btn").disabled = true;
  renderScoreboard();
  // Open the deterministic turn feedback with the player's own play. Clear any
  // stale timers FIRST so the fresh fade-in timers below survive.
  clearTurnTimers();
  const log = $("turn-feedback");
  if (log) { log.textContent = ""; log.classList.remove("resolved", "collapsing"); log.style.display = ""; }
  const pd = res.deal;
  feedbackLine(`你 打出 ${pd.acquirer_ticker}→${pd.target_ticker} · ${signed(pd.match_points)} MP`, "you", "player");
  refreshSeatPresence(null);
  setSeatState(1, "等待出牌 · Ready", null);
  setSeatState(2, "等待出牌 · Ready", null);
  clearSelection();
  persistMatch();
  updatePlayDealButton();
  // Brief beat, then the opponents respond one after another (deterministic).
  turnTimers.push(setTimeout(robotsTakeTurn, 380));
}

// ── Deterministic opponent turn feedback (sequential, no randomness/animation
// library). Opponent 1 thinks then plays, then Opponent 2 — each with a fixed
// short delay and a CSS fade-in line. The final match state is identical to a
// non-animated resolution; only the reveal is staged. ────────────────────────
let turnTimers = [];
function clearTurnTimers() { turnTimers.forEach(clearTimeout); turnTimers = []; }
const TURN_STEP_MS = 480;

function feedbackLine(text, cls, participant) {
  const log = $("turn-feedback");
  if (!log) return;
  const line = el("div", `tf-line ${cls || ""}`.trim(), text);
  // Tag the owning participant (player / robot_1 / robot_2) so the round winner's
  // line can be gold-highlighted later. This is a display hook only.
  if (participant) line.dataset.participant = participant;
  log.appendChild(line);
  // Force a reflow-free fade-in on the next frame.
  turnTimers.push(setTimeout(() => line.classList.add("in"), 20));
}

// V5.10.1.1: once Showdown is the primary result stage, the full turn-feedback
// sequence (player + both bankers + winner badge) collapses to a single compact
// auxiliary line. The robot thinking/played rhythm stays live UNTIL this runs.
// Showdown + dock Round Result own the winner/deal/MP truth — this is status only.
const TF_SUMMARY_TEXT = "本轮三方摊牌完成 · 查看桌面结果 · Showdown resolved";
function collapseTurnFeedbackSummary(animated) {
  const log = $("turn-feedback");
  if (!log) return;
  const reduce = prefersReducedMotion();
  const apply = () => {
    log.textContent = "";
    log.classList.remove("collapsing");
    log.classList.add("resolved");
    log.appendChild(el("div", "tf-line tf-summary in", TF_SUMMARY_TEXT));
    log.style.display = "";
  };
  if (!animated || reduce || log.children.length === 0) { apply(); return; }
  Array.from(log.children).forEach((line) => line.classList.add("out"));
  log.classList.add("collapsing");
  turnTimers.push(setTimeout(apply, 280));
}

function bankerLabel(id) {
  const ident = opponentIdentity(id);
  if (ident) return ident.displayName;
  return personaOf(MATCH.participants[id].difficulty).title;
}

function beginThinking(seat, id) {
  setSeatState(seat, "思考中… · Thinking", "active-turn");
  const node = $(`seat-robot-${seat}`);
  if (node) node.classList.add("thinking");
  feedbackLine(`${bankerLabel(id)} 思考中…`, "think");
}

function revealOneRobot(seat, id, rec) {
  const node = $(`seat-robot-${seat}`);
  if (node) node.classList.remove("thinking");
  setSeatState(seat, "已出牌 · Played", "played");
  const deal = rec && rec[id];
  const title = bankerLabel(id);
  if (deal) {
    feedbackLine(`${title} 打出 ${deal.acquirer_ticker}→${deal.target_ticker} · ${signed(deal.match_points)} MP`,
      deal.match_points >= 0 ? "pos" : "neg", id);
  } else {
    feedbackLine(`${title} 本回合未出牌`, "think", id);
  }
  setScoreSpan(id); // tick this opponent's running total up now
}

function robotsTakeTurn() {
  const pairs = Object.values(PAIRS_INDEX);
  window.MatchEngine.robotsPlay(MATCH, pairs, getPair, companyById);
  persistMatch();
  const rec = MATCH.rounds.find((r) => r.round === MATCH.round_index);
  clearTurnTimers();
  // Opponent 1 thinks immediately, then plays; Opponent 2 follows.
  beginThinking(1, "robot_1");
  turnTimers.push(setTimeout(() => {
    revealOneRobot(1, "robot_1", rec);
    beginThinking(2, "robot_2");
  }, TURN_STEP_MS));
  turnTimers.push(setTimeout(() => {
    revealOneRobot(2, "robot_2", rec);
    finishRobotsTurn(rec);
  }, TURN_STEP_MS * 2));
}

function finishRobotsTurn() {
  renderScoreboard();
  const rec = MATCH.rounds.find((r) => r.round === MATCH.round_index);
  refreshSeatPresence(rec);
  renderRoundResult();
  // V5.10.1: stage the three-way Showdown on the table center (animated reveal).
  // V5.10.1.1: showShowdown also collapses turn-feedback to a one-line summary so
  // winner/result info is not triple-stacked with Showdown + Round Result.
  showShowdown(rec, true);
  persistMatch();
  $("play-deal-btn").style.display = "none";
  const nb = $("next-round-btn");
  nb.style.display = "";
  const isLast = MATCH.round_index >= MATCH.max_rounds;
  nb.textContent = isLast ? "查看结算 · Settlement →" : "保留并进入下一回合 · Keep & Next →";
  // V5.9.4.1 flow fix: DO NOT auto-open the retain modal. The page rests on the
  // round-result state so the player can read the Showdown (primary), the compact
  // Round Result panel, the scoreboard and the Queue. The retain modal only opens
  // when the player actively clicks Keep & Next (see onKeepNext).
  updatePlayDealButton();
}

// V5.10.2 player-visible name: banker display name + rank (fallback: persona · seat).
function participantName(id) {
  if (id === "player") return "你 · You";
  const ident = opponentIdentity(id);
  if (ident) return `${ident.displayName} · ${ident.rankCn}`;
  const p = MATCH.participants[id];
  const persona = personaOf(p.difficulty);
  const seat = id === "robot_2" ? "2" : "1";
  return `${persona.title} · 席位 ${seat}`;
}
function participantNameShort(id) {
  if (id === "player") return "你 · You";
  const ident = opponentIdentity(id);
  if (ident) return ident.displayName;
  return participantName(id);
}

function buildDealMini(deal) {
  const wrap = el("span", "mr-deal");
  const a = el("span", "a", deal ? (deal.acquirer_ticker || "—") : "—");
  const t = el("span", "t", deal ? (deal.target_ticker || "—") : "—");
  wrap.append(a, el("span", "ar", "→"), t);
  return wrap;
}

// ── V5.10.1 The Showdown ─────────────────────────────────────────────────────
// Re-stages the resolved round on the table center as three result cards
// (你 / Banker 1 / Banker 2). It is PURE PRESENTATION over the SAME light round
// record the engine already produced: it reads each participant's existing deal
// (ACQ→TGT, EPS, viability_level) and Match Points and the existing roundWinner.
// It recomputes nothing, stores nothing new, fetches nothing, and changes no
// rule / Match Points / engine truth. All dynamic text uses el()/textContent;
// missing fields fall back to a muted placeholder, never a crash / white screen.
function prefersReducedMotion() {
  try { return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); }
  catch (_) { return false; }
}
const VIA_SHORT = { green: "可行性 绿 · Clear", yellow: "可行性 黄 · Review", red: "可行性 红 · High" };
function viabilityShort(level) { return VIA_SHORT[level] || "可行性 · —"; }

// Swap the deal table between PLAY mode (slots + deck) and SHOWDOWN mode (the
// three result cards). Showdown is inline-on-table (no full-screen overlay): the
// empty deal zone / hint hide and the Showdown stage takes the table center.
function setTableShowdown(on) {
  const stage = $("showdown-stage");
  const zone = $("deal-zone");
  const hint = $("deal-hint");
  const label = $("felt-label");
  if (stage) stage.style.display = on ? "" : "none";
  if (zone) zone.style.display = on ? "none" : "";
  if (hint) hint.style.display = on ? "none" : "";
  if (label) label.textContent = on ? "Showdown · 三方摊牌" : "Deal Table";
}
function resetShowdown() {
  const grid = $("showdown-grid");
  if (grid) grid.textContent = "";
  const verdict = $("showdown-verdict");
  if (verdict) verdict.textContent = "";
  setTableShowdown(false);
  refreshSeatPresence(null);
}

// Light count-roll for an MP badge: animates the integer 0 → match_points and
// ALWAYS lands on the exact engine value (text equals `${signed(mp)} MP`). Under
// reduced-motion (or without rAF) it sets the final value immediately. Visual
// only — it never reads or writes Match Points.
function rollMatchPoints(node, target, ms) {
  const final = `${signed(target)} MP`;
  if (!node) return;
  if (prefersReducedMotion() || typeof window.requestAnimationFrame !== "function") {
    node.textContent = final;
    return;
  }
  let start = null;
  function step(ts) {
    if (start === null) start = ts;
    const p = Math.min(1, (ts - start) / ms);
    const v = Math.round(target * p);
    node.textContent = `${signed(v)} MP`;
    if (p < 1) window.requestAnimationFrame(step);
    else node.textContent = final;
  }
  window.requestAnimationFrame(step);
}

// Build ONE result card for a participant from its light deal record (or null).
function buildShowdownCard(id, deal, winnerId) {
  const card = el("div", `scard owner-${id === "player" ? "you" : "bot"}`);
  card.id = `scard-${id}`;
  card.dataset.participant = id;
  if (id !== "player" && window.OpponentIdentity) {
    const ident = opponentIdentity(id);
    if (ident) applyRankVisual(card, ident.difficulty);
  }
  if (winnerId && winnerId !== "draw" && id === winnerId) card.dataset.winner = "1";

  // Winner mark (hidden until the card gains .winner).
  card.appendChild(el("div", "scard-crown", "本回合胜者 · WINNER"));

  // Owner label: 你 · You / banker name + rank (display only; ids stay internal).
  const owner = el("div", `scard-owner${id === "player" ? " you" : ""}`);
  if (id === "player") {
    owner.textContent = "你 · You";
  } else {
    const ident = opponentIdentity(id);
    if (ident) {
      owner.appendChild(el("span", "scard-owner-name", ident.displayName));
      owner.appendChild(el("span", "scard-owner-rank", ` · ${ident.rankCn}`));
    } else {
      owner.textContent = participantName(id);
    }
  }
  card.appendChild(owner);

  if (!deal) {
    card.appendChild(el("div", "scard-deal", "—"));
    card.appendChild(el("div", "scard-empty", "本回合未出牌 · No deal"));
    return card;
  }

  // Deal line: ACQ → TGT (tickers, monospace, acquirer blue / target amber).
  const dealEl = el("div", "scard-deal");
  dealEl.append(
    el("span", "a", deal.acquirer_ticker || "—"),
    el("span", "ar", "→"),
    el("span", "t", deal.target_ticker || "—"),
  );
  card.appendChild(dealEl);

  // Chinese company names when available (graceful fallback to ticker).
  const acqCard = companyById(deal.acquirer_id);
  const tgtCard = companyById(deal.target_id);
  const acqCn = acqCard ? cnName(acqCard) : (deal.acquirer_ticker || "—");
  const tgtCn = tgtCard ? cnName(tgtCard) : (deal.target_ticker || "—");
  const sub = el("div", "scard-sub");
  sub.append(document.createTextNode(acqCn), document.createTextNode(" → "), document.createTextNode(tgtCn));
  card.appendChild(sub);

  // EPS hero + MP badge.
  const mid = el("div", "scard-mid");
  const epsWrap = el("div", "scard-eps-wrap");
  const epsText = pct(deal.accretion_dilution_pct);
  const epsCls = epsText === "-" ? "na" : (deal.is_accretive ? "accretive" : "dilutive");
  epsWrap.append(
    el("div", `scard-eps ${epsCls}`, epsText === "-" ? "数据不足" : epsText),
    el("div", "scard-eps-lbl", "EPS 增厚/摊薄"),
  );
  mid.appendChild(epsWrap);
  const mp = el("span", "scard-mp", `${signed(deal.match_points)} MP`);
  mp.id = `scard-mp-${id}`;
  mp.dataset.mp = String(deal.match_points);
  mid.appendChild(mp);
  card.appendChild(mid);

  // Viability lamp (red/yellow/green = deal viability ONLY, never a player grade).
  const foot = el("div", "scard-foot");
  const via = el("div", `scard-via ${deal.viability_level || "green"}`);
  via.append(el("span", "via-lamp"), el("span", null, viabilityShort(deal.viability_level)));
  foot.appendChild(via);
  card.appendChild(foot);

  // V5.10.2 finite scripted showdown line (deterministic; presentation only).
  if (id !== "player" && window.OpponentIdentity && MATCH) {
    const ident = opponentIdentity(id);
    if (ident) {
      const line = window.OpponentIdentity.pickShowdownLine(ident, MATCH.match_seed, MATCH.round_index);
      if (line) card.appendChild(el("div", "scard-line", line));
    }
  }
  return card;
}

// Build the three face-down cards from the current round record.
function buildShowdown(rec) {
  const grid = $("showdown-grid");
  if (!grid || !rec) return;
  grid.textContent = "";
  const winnerId = window.MatchEngine.roundWinner(rec);
  for (const id of ["player", "robot_1", "robot_2"]) {
    grid.appendChild(buildShowdownCard(id, rec[id], winnerId));
  }
}

// Mark the winner (committee amber ring + WINNER) + dim losers, pop/roll each MP,
// and write the verdict line. Winner/tie semantics come straight from the engine
// roundWinner — a "draw" highlights no card and shows the existing draw copy.
function settleShowdown(rec) {
  refreshSeatPresence(rec);
  const reduce = prefersReducedMotion();
  const winnerId = window.MatchEngine.roundWinner(rec);
  for (const id of ["player", "robot_1", "robot_2"]) {
    const card = $(`scard-${id}`);
    if (!card) continue;
    card.classList.add("revealed");
    if (winnerId !== "draw") {
      if (id === winnerId) card.classList.add("winner");
      else card.classList.add("loser", "dim");
    }
    const mpNode = $(`scard-mp-${id}`);
    if (mpNode) {
      const deal = rec[id];
      if (!reduce) mpNode.classList.add("pop");
      rollMatchPoints(mpNode, deal ? numOrZero(deal.match_points) : 0, 600);
    }
  }
  const verdict = $("showdown-verdict");
  if (verdict) {
    verdict.textContent = "";
    const line = el("div", `sv-line${winnerId === "draw" ? " draw" : ""}`);
    if (winnerId === "draw") {
      line.appendChild(document.createTextNode("本回合平局 · Round Draw"));
    } else if (winnerId === "player") {
      line.append(document.createTextNode("本回合 "), el("span", "hl", "你赢得了这张桌子"),
        document.createTextNode(" · You win the round"));
    } else {
      line.append(document.createTextNode("本回合 "), el("span", "hl", `${participantName(winnerId)} 胜`));
    }
    verdict.appendChild(line);
    if (reduce) line.classList.add("in");
    else turnTimers.push(setTimeout(() => line.classList.add("in"), 40));
  }
}
function numOrZero(n) { return (typeof n === "number" && isFinite(n)) ? n : 0; }

// Build + reveal the Showdown. When `animated`, the cards flip up You → B1 → B2
// on a short stagger then the winner is lit; otherwise (restore on refresh) they
// appear settled at once. Reveal timers use turnTimers so they are cleared by the
// existing nextRound / playAgain / clearTurnTimers paths (never block Keep & Next).
function showShowdown(rec, animated) {
  if (!rec) return;
  collapseTurnFeedbackSummary(animated);
  setTableShowdown(true);
  buildShowdown(rec);
  if (!animated || prefersReducedMotion()) { settleShowdown(rec); return; }
  const ids = ["player", "robot_1", "robot_2"];
  ids.forEach((id, k) => {
    turnTimers.push(setTimeout(() => {
      const card = $(`scard-${id}`);
      if (card) card.classList.add("revealed");
    }, k * 200));
  });
  turnTimers.push(setTimeout(() => settleShowdown(rec), ids.length * 200 + 220));
}

function renderRoundResult() {
  const rec = MATCH.rounds.find((r) => r.round === MATCH.round_index);
  const panel = $("round-result");
  const list = $("mr-list");
  const winnerEl = $("mr-winner");
  if (!rec || !panel || !list) return;
  panel.classList.add("show");
  const winnerId = window.MatchEngine.roundWinner(rec);
  winnerEl.textContent = "";
  if (winnerId === "draw") {
    winnerEl.append(el("span", "mr-win-draw", "本回合平局 · Round Draw"));
  } else {
    const cls = winnerId === "player" ? "mr-win-you" : "mr-win-bot";
    winnerEl.append(el("span", cls, `本回合胜者 · ${participantName(winnerId)}`));
  }
  list.textContent = "";
  for (const id of ["player", "robot_1", "robot_2"]) {
    const deal = rec[id];
    const row = el("div", "mr-row" + (id === winnerId ? " win" : ""));
    const whoWrap = el("span", "mr-who-wrap" + (id === "player" ? " you" : ""));
    const who = el("span", "mr-who" + (id === "player" ? " you" : ""),
      id === "player" ? "你" : participantNameShort(id));
    whoWrap.appendChild(who);
    if (id !== "player" && window.OpponentIdentity && MATCH) {
      const ident = opponentIdentity(id);
      if (ident) {
        const outcome = winnerId === "draw" ? "draw"
          : (id === winnerId ? "win" : "loss");
        const quote = window.OpponentIdentity.pickRoundResultLine(
          ident, MATCH.match_seed, MATCH.round_index, outcome);
        if (quote) whoWrap.appendChild(el("span", "mr-quote", quote));
      }
    }
    row.append(whoWrap, buildDealMini(deal), el("span", "mr-pts", deal ? signed(deal.match_points) : "—"));
    list.appendChild(row);
  }
}

// ── V5.9.4 round transition: keep up to 4 cards, refresh new ones to 7 ──────
// The player chooses up to RETAIN_MAX cards to carry into the next round; the
// rest are dropped back to the eligible pool, and the system draws fresh cards
// (canonically REFRESH_COUNT=3 when 4 are kept) to refill to HAND_SIZE. Used
// cards never come back; an exhausted pool just refills with fewer cards.
let retainSelection = new Set();

function updateRetainCount() {
  const cnt = $("retain-count");
  if (cnt) cnt.textContent = `已保留 ${retainSelection.size} / ${RETAIN_MAX}`;
}
function toggleRetain(id) {
  if (!id || !companyById(id)) return;
  if (retainSelection.has(id)) {
    retainSelection.delete(id);
  } else {
    if (retainSelection.size >= RETAIN_MAX) { flashHint(`最多保留 ${RETAIN_MAX} 张手牌。`); return; }
    retainSelection.add(id);
  }
  renderRetainList();
}
function renderRetainList() {
  const host = $("retain-list");
  if (!host) return;
  host.textContent = "";
  const hand = Array.isArray(MATCH.hand) ? MATCH.hand : [];
  for (const id of hand) {
    const c = companyById(id);
    if (!c) continue;
    const chip = el("button", "retain-chip" + (retainSelection.has(id) ? " retained" : ""));
    chip.type = "button";
    chip.dataset.id = id;
    // Reuse the SAME arena tier class/color tokens + tier pill as the hand cards
    // so the player can tell Legendary / Elite / Core / Specialist / White apart.
    applyArenaTier(chip, c);
    chip.setAttribute("aria-pressed", retainSelection.has(id) ? "true" : "false");
    chip.setAttribute("aria-label", `${c.ticker} ${cnName(c)}`);
    chip.append(
      arenaTierBadge(c, "rc-tier"),
      el("span", "rc-tk", c.ticker),
      el("span", "rc-nm", cnName(c)),
    );
    chip.addEventListener("click", () => toggleRetain(id));
    host.appendChild(chip);
  }
  updateRetainCount();
}
// V5.9.4.1 flow: the round rests on its result; the player opens the retain modal
// by clicking Keep & Next. The last round has no retain step, so it goes straight
// to settlement.
function onKeepNext() {
  if (!MATCH || !window.MatchEngine) return;
  const isLast = MATCH.round_index >= MATCH.max_rounds;
  if (isLast) { nextRound(); return; }
  enterRetainPhase();
}
function enterRetainPhase() {
  retainSelection = new Set();
  const overlay = $("retain-overlay");
  if (overlay) overlay.style.display = "flex";
  // While the modal is open its own confirm owns Keep & Next, so the turn-bar
  // button is hidden to avoid a second (scrim-covered) duplicate.
  const nb = $("next-round-btn");
  if (nb) nb.style.display = "none";
  renderRetainList();
}
function exitRetainPhase() {
  retainSelection = new Set();
  const overlay = $("retain-overlay");
  if (overlay) overlay.style.display = "none";
}
// Close the modal WITHOUT advancing — returns to the round-result state and
// re-shows the Keep & Next button so the player can keep reviewing the round.
function closeRetainModal() {
  exitRetainPhase();
  if (MATCH && window.MatchEngine && MATCH.phase === window.MatchEngine.PHASE.ROUND_RESULT) {
    const nb = $("next-round-btn");
    if (nb) nb.style.display = "";
  }
}
// Apply the player's retain choice and refresh the hand back to HAND_SIZE.
function applyRetainAndRefresh() {
  if (!MATCH) return;
  if (!Array.isArray(MATCH.hand)) MATCH.hand = [];
  const used = usedSet();
  const retained = [];
  for (const id of MATCH.hand) {
    if (retained.length >= RETAIN_MAX) break;
    if (retainSelection.has(id) && companyById(id) && !used.has(id)) retained.push(id);
  }
  MATCH.hand = retained.slice();
  HAND = MATCH.hand;
  const need = Math.max(0, HAND_SIZE - MATCH.hand.length);
  if (need > 0) {
    const fresh = drawEligible(need);
    MATCH.hand = MATCH.hand.concat(fresh);
    HAND = MATCH.hand;
  }
  retainSelection = new Set();
  renderHand();
}

function nextRound() {
  if (!MATCH) return;
  clearTurnTimers();
  const wasLastRound = MATCH.round_index >= MATCH.max_rounds;
  // Apply the keep-4 / refresh-3 transition BEFORE advancing (not on settlement).
  if (!wasLastRound) applyRetainAndRefresh();
  window.MatchEngine.nextRound(MATCH);
  persistMatch();
  if (MATCH.phase === window.MatchEngine.PHASE.MATCH_COMPLETE) {
    showEndScreen();
    return;
  }
  // New round: reset the table selection (NOT the match state / queue).
  exitRetainPhase();
  resetShowdown(); // table returns from Showdown mode to the deal table
  const log = $("turn-feedback");
  if (log) { log.textContent = ""; log.classList.remove("resolved", "collapsing"); log.style.display = "none"; }
  $("round-result").classList.remove("show");
  $("next-round-btn").style.display = "none";
  $("play-deal-btn").style.display = "";
  refreshSeatPresence(null);
  setSeatState(1, "等待出牌 · Ready", null);
  setSeatState(2, "等待出牌 · Ready", null);
  renderRoundPill();
  renderScoreboard();
  updateResourceButtons(); // new round restored the per-round Draw allowance
  clearSelection();
  updatePlayDealButton();
}

// ── End screen / settlement (staggered reveal, no animation library) ────────
let endTimers = [];
function clearEndTimers() { endTimers.forEach(clearTimeout); endTimers = []; }

function showEndScreen() {
  const screen = $("end-screen");
  screen.style.display = "flex";
  $("end-calc").style.display = "";
  $("end-content").style.display = "none";
  clearEndTimers();
  // 1) "Calculating deal results…" beat, then reveal the settlement in stages.
  endTimers.push(setTimeout(() => {
    $("end-calc").style.display = "none";
    $("end-content").style.display = "";
    buildEndContent();
    revealStaged();
  }, 900));
}

function revealStaged() {
  // The verdict ceremony reveals top-down: who won → how (trajectory) → which
  // deals mattered (best deals) → final scores → detailed review. The actions row
  // is shown from the start so the player can always leave / replay.
  reveal("reveal-verdict", 0);
  reveal("reveal-trajectory", 520);
  reveal("reveal-best", 1040);
  reveal("reveal-totals", 1500);
  reveal("reveal-review", 1860);
}
function reveal(id, delay) {
  const node = $(id);
  if (!node) return;
  endTimers.push(setTimeout(() => node.classList.add("in"), delay));
}

function vtagShort(level) { return ({ green: "绿", yellow: "黄", red: "红" })[level] || "—"; }

function buildDealChip(deal, addedFrom) {
  const chip = el("div", "deal-chip");
  const dealEl = el("span", "dc-deal");
  dealEl.append(el("span", "a", deal.acquirer_ticker || "—"), el("span", "ar", "→"), el("span", "t", deal.target_ticker || "—"));
  chip.append(dealEl);
  const epsText = pct(deal.accretion_dilution_pct);
  chip.append(el("span", `dc-eps ${epsText === "-" ? "na" : (deal.is_accretive ? "accretive" : "dilutive")}`,
    epsText === "-" ? "数据不足" : epsText));
  chip.append(el("span", `dc-vtag ${deal.viability_level || "green"}`, vtagShort(deal.viability_level)));
  chip.append(el("span", "dc-mp", `${signed(deal.match_points)} MP`));
  chip.title = "点一下加入候选队列复盘";
  chip.addEventListener("click", () => {
    const ok = addDealToQueue(deal.acquirer_id, deal.target_id, addedFrom);
    chip.style.borderColor = ok ? "rgba(63,185,80,0.7)" : "";
  });
  return chip;
}

// ── V5.10.3 Match Ceremony builders ─────────────────────────────────────────
// Every value below is READ from the existing match state (rankings / winner /
// round records / bestDealFor) — nothing is recomputed, fetched, or stored anew.
// All dynamic text uses el()/textContent; missing fields fall back to a muted
// placeholder so the ceremony never white-screens.

// 1) Verdict header: spotlight the winner identity, the final score, the line.
function buildVerdict() {
  const stage = $("verdict-stage");
  const sigil = $("verdict-sigil");
  const winnerEl = $("end-winner");
  const scoreEl = $("verdict-score");
  const lineEl = $("verdict-line");
  if (!stage || !winnerEl) return;
  const ranking = window.MatchEngine.rankings(MATCH);
  const win = window.MatchEngine.winner(MATCH);

  stage.classList.remove("win-you", "win-bot", "win-draw");
  if (sigil) sigil.textContent = "";
  winnerEl.textContent = "";
  if (win === "draw") {
    stage.classList.add("win-draw");
    winnerEl.className = "end-winner draw";
    winnerEl.textContent = "平局 · Split Decision";
  } else if (win === "player") {
    stage.classList.add("win-you");
    winnerEl.className = "end-winner you";
    winnerEl.textContent = "你赢得了投委会 · You Won the Committee";
  } else {
    stage.classList.add("win-bot");
    winnerEl.className = "end-winner bot";
    const ident = opponentIdentity(win);
    if (ident) {
      winnerEl.textContent = `${ident.displayName} · ${ident.rankCn} 赢得本场`;
      if (sigil) renderSigil(sigil, ident, 44);
    } else {
      winnerEl.textContent = `${participantName(win)} 获胜`;
    }
  }

  // Final score line in ranking order (highest first): "Name 312 · 你 165 · …".
  if (scoreEl) {
    scoreEl.textContent = ranking
      .map((r) => `${participantNameShort(r.id)} ${r.points} MP`)
      .join("　·　");
  }

  // Final scripted line — finite, deterministic from (seed, outcome, winner id).
  if (lineEl) {
    lineEl.textContent = "";
    if (window.OpponentIdentity && typeof window.OpponentIdentity.pickFinalLine === "function") {
      const seed = (MATCH && MATCH.match_seed != null) ? MATCH.match_seed : 1;
      let line = "";
      if (win === "player") line = window.OpponentIdentity.pickFinalLine("player", null, seed);
      else if (win === "draw") line = window.OpponentIdentity.pickFinalLine("draw", null, seed);
      else line = window.OpponentIdentity.pickFinalLine("banker", opponentIdentity(win), seed);
      if (line) lineEl.textContent = line;
    }
  }
}

// 2) Five-round trajectory: one node per round showing that round's winner + the
// winning deal's MP. Nodes won by the eventual match winner get a subtle ring.
function buildTrajectory() {
  const host = $("end-trajectory");
  if (!host) return;
  host.textContent = "";
  const matchWin = window.MatchEngine.winner(MATCH);
  const rounds = MATCH.rounds.slice().sort((a, b) => a.round - b.round);
  const maxRounds = (MATCH && MATCH.max_rounds) || window.MatchEngine.MAX_ROUNDS;
  for (let i = 0; i < maxRounds; i++) {
    const roundNo = i + 1;
    const rec = rounds.find((r) => r.round === roundNo) || null;
    const winnerId = rec ? window.MatchEngine.roundWinner(rec) : "draw";
    const cls = winnerId === "player" ? "win-you" : (winnerId === "draw" ? "win-draw" : "win-bot");
    const node = el("div", `traj-node ${cls}`);
    if (winnerId !== "draw" && matchWin !== "draw" && winnerId === matchWin) node.classList.add("match-winner");
    if (winnerId !== "draw" && winnerId !== "player") {
      const ident = opponentIdentity(winnerId);
      if (ident) applyRankVisual(node, ident.difficulty);
    }
    node.appendChild(el("div", "traj-round", `回合 ${roundNo}`));
    node.appendChild(el("div", "traj-dot", String(roundNo)));
    const whoText = winnerId === "draw" ? "平局"
      : (winnerId === "player" ? "你" : participantNameShort(winnerId));
    node.appendChild(el("div", "traj-who", whoText));
    const winDeal = (rec && winnerId !== "draw") ? rec[winnerId] : null;
    node.appendChild(el("div", "traj-mp" + (winDeal ? "" : " draw"),
      winDeal ? `${signed(winDeal.match_points)} MP` : "—"));
    host.appendChild(node);
  }
}

// 3) Best deals: one highlight card per participant; the single highest-MP best
// deal across all three is tagged "Deal of the Match".
function buildBestCard(id, deal, domId) {
  const card = el("div", `best-card owner-${id === "player" ? "you" : "bot"}`);
  if (id !== "player") {
    const ident = opponentIdentity(id);
    if (ident) applyRankVisual(card, ident.difficulty);
  }
  if (deal && id === domId) {
    card.classList.add("dom");
    card.appendChild(el("div", "best-dom-badge", "本场最佳交易 · Deal of the Match"));
  }
  const owner = el("div", `best-owner${id === "player" ? " you" : ""}`);
  if (id === "player") {
    owner.textContent = "你 · You";
  } else {
    const ident = opponentIdentity(id);
    if (ident) {
      owner.appendChild(el("span", "best-owner-name", ident.displayName));
      owner.appendChild(el("span", "best-owner-rank", ` · ${ident.rankCn}`));
    } else {
      owner.textContent = participantName(id);
    }
  }
  card.appendChild(owner);

  if (!deal) {
    card.appendChild(el("div", "best-deal", "—"));
    card.appendChild(el("div", "best-empty", "本局无已出交易 · No deal"));
    return card;
  }

  const dealEl = el("div", "best-deal");
  dealEl.append(el("span", "a", deal.acquirer_ticker || "—"), el("span", "ar", "→"), el("span", "t", deal.target_ticker || "—"));
  card.appendChild(dealEl);

  const mid = el("div", "best-mid");
  const epsText = pct(deal.accretion_dilution_pct);
  const epsCls = epsText === "-" ? "na" : (deal.is_accretive ? "accretive" : "dilutive");
  const epsBlock = el("div", "best-eps-wrap");
  epsBlock.appendChild(el("div", `best-eps ${epsCls}`, epsText === "-" ? "数据不足" : epsText));
  epsBlock.appendChild(el("div", "best-eps-lbl", "EPS 增厚/摊薄"));
  mid.appendChild(epsBlock);
  mid.appendChild(el("span", "best-mp", `${signed(deal.match_points)} MP`));
  card.appendChild(mid);

  const foot = el("div", "best-foot");
  const via = el("div", `best-via ${deal.viability_level || "green"}`);
  via.append(el("span", "via-lamp"), el("span", null, viabilityShort(deal.viability_level)));
  foot.appendChild(via);
  card.appendChild(foot);
  return card;
}

function buildBestDeals() {
  const host = $("end-best-deals");
  if (!host) return;
  host.textContent = "";
  const bests = {};
  let domId = null;
  let domMp = null;
  for (const id of ["player", "robot_1", "robot_2"]) {
    const best = window.MatchEngine.bestDealFor(MATCH, id);
    bests[id] = best;
    if (best) {
      const mp = numOrZero(best.match_points);
      if (domMp === null || mp > domMp) { domMp = mp; domId = id; }
    }
  }
  for (const id of ["player", "robot_1", "robot_2"]) {
    host.appendChild(buildBestCard(id, bests[id], domId));
  }
}

function buildEndContent() {
  // Identities may not have been refreshed if the match completes on restore.
  refreshOpponentIdentities();

  // 1) Verdict header, 2) trajectory, 3) best deals — the main ceremony view.
  buildVerdict();
  buildTrajectory();
  buildBestDeals();

  // 4a) Final Match Points totals (the authoritative scoreboard, ranking order).
  const totals = $("end-totals");
  totals.textContent = "";
  const ranking = window.MatchEngine.rankings(MATCH);
  const win = window.MatchEngine.winner(MATCH);
  for (const r of ranking) {
    const chip = el("div", "et-chip" + (r.id === win && win !== "draw" ? " winner" : ""));
    chip.append(el("span", "et-name", participantName(r.id)), el("span", "et-pts", `${r.points}`));
    totals.appendChild(chip);
  }

  // 4b) Detailed review (collapsible): full round table + 15-deal compact review.
  // Information is preserved, just demoted below the trajectory / best deals.
  const roundsHost = $("end-rounds");
  roundsHost.textContent = "";
  const header = el("div", "end-round-row");
  header.append(el("span", "erh", "回合"), el("span", "erh", "你 · You"),
    el("span", "erh", participantName("robot_1")), el("span", "erh", participantName("robot_2")));
  roundsHost.appendChild(header);
  for (const rec of MATCH.rounds.slice().sort((a, b) => a.round - b.round)) {
    const winnerId = window.MatchEngine.roundWinner(rec);
    const row = el("div", "end-round-row");
    row.appendChild(el("span", "er-label", `R${rec.round}`));
    for (const id of ["player", "robot_1", "robot_2"]) {
      const deal = rec[id];
      const cell = el("span", "er-cell" + (id === winnerId ? " win" : ""));
      if (deal) {
        cell.appendChild(el("span", "pts", `${signed(deal.match_points)}`));
        cell.appendChild(el("span", "who", ` ${deal.acquirer_ticker}→${deal.target_ticker}`));
      } else {
        cell.appendChild(el("span", "who", "—"));
      }
      row.appendChild(cell);
    }
    roundsHost.appendChild(row);
  }

  // Compact review: each participant's 5 deals as small chips + best deal.
  const review = $("end-review");
  review.textContent = "";
  for (const id of ["player", "robot_1", "robot_2"]) {
    const p = MATCH.participants[id];
    const part = el("div", "er-part");
    const head = el("div", "er-part-head");
    head.append(el("span", "er-part-name", participantName(id)), el("span", "er-part-total", `${p.points} MP`));
    part.appendChild(head);
    const best = window.MatchEngine.bestDealFor(MATCH, id);
    const bestLine = el("div", "er-part-best");
    if (best) {
      bestLine.append(document.createTextNode("最佳交易："));
      bestLine.append(el("b", null, `${best.acquirer_ticker}→${best.target_ticker} (${signed(best.match_points)} MP)`));
    } else {
      bestLine.textContent = "本局无已出交易。";
    }
    part.appendChild(bestLine);
    const chips = el("div", "er-chips");
    const addedFrom = id === "player" ? "match_player" : `robot_${p.difficulty}`;
    const deals = MATCH.deals.filter((d) => d.participant === id).sort((a, b) => a.round - b.round);
    for (const d of deals) chips.appendChild(buildDealChip(d, addedFrom));
    part.appendChild(chips);
    review.appendChild(part);
  }
}

function addBestDeals() {
  let added = 0;
  for (const id of ["player", "robot_1", "robot_2"]) {
    const best = window.MatchEngine.bestDealFor(MATCH, id);
    if (!best) continue;
    const p = MATCH.participants[id];
    const addedFrom = id === "player" ? "match_player" : `robot_${p.difficulty}`;
    if (addDealToQueue(best.acquirer_id, best.target_id, addedFrom)) added++;
  }
  const btn = $("end-add-best");
  if (btn) { btn.disabled = true; btn.textContent = added ? `已加入 ${added} 笔 ✓` : "最佳交易已在候选 ✓"; }
}

function playAgain() {
  clearEndTimers();
  clearTurnTimers();
  $("end-screen").style.display = "none";
  // Play Again is the ONLY reset of match state (Clear Deal never resets it). A
  // fresh seed → a new draw order → a different opening hand; old used_cards /
  // round state never carry over.
  MATCH = startNewMatch(MATCH_CONFIG);
  initialDeal(); // fresh hand from the new seeded order + empty used pile
  persistMatch();
  const addBtn = $("end-add-best");
  if (addBtn) { addBtn.disabled = false; addBtn.textContent = "把最佳交易加入候选 · Add Best Deals"; }
  exitRetainPhase();
  resetShowdown(); // a fresh match starts on the deal table, not a stale Showdown
  const log = $("turn-feedback");
  if (log) { log.textContent = ""; log.classList.remove("resolved", "collapsing"); log.style.display = "none"; }
  $("round-result").classList.remove("show");
  $("next-round-btn").style.display = "none";
  $("play-deal-btn").style.display = "";
  refreshSeatPresence(null);
  setSeatState(1, "等待出牌 · Ready", null);
  setSeatState(2, "等待出牌 · Ready", null);
  renderSeats();
  renderScoreboard();
  renderRoundPill();
  updateResourceButtons(); // fresh match restored both Draw + Reshuffle allowances
  clearSelection();
  updatePlayDealButton();
}

// ── Resume an in-progress match's visible state after a restore ──────────────
function syncMatchView() {
  // Normalize a restored/legacy match that predates the V5.9.3 resource counters.
  if (typeof MATCH.draw_allowance !== "number") MATCH.draw_allowance = window.MatchEngine.DRAW_PER_ROUND;
  if (typeof MATCH.reshuffle_allowance !== "number") MATCH.reshuffle_allowance = window.MatchEngine.RESHUFFLE_PER_MATCH;
  renderSeats();
  renderScoreboard();
  renderRoundPill();
  updateResourceButtons();
  const phase = MATCH.phase;
  const P = window.MatchEngine.PHASE;
  if (phase === P.MATCH_COMPLETE) {
    showEndScreen();
  } else if (phase === P.ROUND_RESULT || phase === P.ROBOTS_PLAYING) {
    // Mid-round-result on refresh: skip the staged reveal, show the final result
    // and the Keep & Next button. V5.9.4.1 flow fix: do NOT auto-open the retain
    // modal — it opens only when the player clicks Keep & Next.
    clearTurnTimers();
    if (phase === P.ROBOTS_PLAYING) { MATCH.phase = P.ROUND_RESULT; persistMatch(); }
    setSeatState(1, "已出牌 · Played", "played");
    setSeatState(2, "已出牌 · Played", "played");
    renderRoundResult();
    // Restore the Showdown settled (no staged flip) so a mid-round-result refresh
    // shows the three result cards + winner immediately.
    const rec = MATCH.rounds.find((r) => r.round === MATCH.round_index);
    showShowdown(rec, false);
    $("play-deal-btn").style.display = "none";
    $("next-round-btn").style.display = "";
    const isLast = MATCH.round_index >= MATCH.max_rounds;
    $("next-round-btn").textContent = isLast
      ? "查看结算 · Settlement →" : "保留并进入下一回合 · Keep & Next →";
  } else {
    refreshSeatPresence(null);
  }
  updatePlayDealButton();
}

async function init() {
  $("reverse-btn").addEventListener("click", reverseDirection);
  $("clear-deal-btn").addEventListener("click", clearSelection);
  $("rc-ticket-btn").addEventListener("click", openTicket);
  $("rc-queue-btn").addEventListener("click", () => addCurrentToQueue("match_player"));
  $("tk-queue-btn").addEventListener("click", () => addCurrentToQueue("ticket"));
  $("ticket-close").addEventListener("click", closeTicket);
  $("ticket-overlay").addEventListener("click", (e) => { if (e.target.id === "ticket-overlay") closeTicket(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeTicket(); });
  $("hand-draw").addEventListener("click", drawOne);
  $("hand-rotate").addEventListener("click", rotateHand);
  const pile = $("draw-pile");
  pile.addEventListener("click", drawOne);
  pile.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drawOne(); } });
  $("play-deal-btn").addEventListener("click", playDeal);
  // Keep & Next rests on the round result, then opens the retain modal on click.
  $("next-round-btn").addEventListener("click", onKeepNext);
  $("retain-confirm-btn").addEventListener("click", nextRound);
  $("retain-close").addEventListener("click", closeRetainModal);
  $("retain-cancel-btn").addEventListener("click", closeRetainModal);
  $("retain-overlay").addEventListener("click", (e) => { if (e.target.id === "retain-overlay") closeRetainModal(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("retain-overlay").style.display === "flex") closeRetainModal();
  });
  $("end-play-again").addEventListener("click", playAgain);
  $("end-add-best").addEventListener("click", addBestDeals);
  attachSlotDropZone($("slot-acq"), "acq");
  attachSlotDropZone($("slot-tgt"), "tgt");

  // Build / restore the match from the setup config. A NEW match always starts
  // with a fresh seed and an EMPTY deal table — it never inherits the War Room's
  // current acquirer/target selection (V5.9.6.2 state isolation). Only a genuine
  // in-progress match (same session, e.g. page refresh) is restored as-is.
  MATCH_CONFIG = loadSetupConfig();
  MATCH = restoreMatchState(MATCH_CONFIG) || startNewMatch(MATCH_CONFIG);
  selected = { acq: null, tgt: null }; // clean deal table; ignore any URL ?acq/?tgt

  window.DealQueue.subscribe(renderQueue);
  renderQueue();

  await Promise.all([loadCards(), loadPairs()]);
  ensureHand();
  // NOTE: the Match deliberately does NOT deep-link a deal from the URL. Start
  // Match is a fresh game with an empty table; the player picks from the hand.
  syncMatchView();
  persistMatch(); // store the freshly dealt / normalized hand + lifecycle fields
}

document.addEventListener("DOMContentLoaded", init);
