// V5.2 Deal Arena Lite front end.
//
// A lightweight card table over the SAME real seed deck and the SAME
// deterministic A/D engine as Deal Studio. The table only shows light info:
// it never renders source_meta, the full economics table, or audit notes.
//
// Hard boundaries (V5.2): no bots, no settlement leaderboard, no favorites,
// no Excel/PPA, no runtime fetch, no LLM. Pure read of the local deck plus a
// pure compute call to /api/modeling/ma/calculate.

const API = "";

// Fixed light-table deal terms. These mirror Deal Studio's defaults so an
// Arena deal is the SAME deterministic result Deal Studio would produce for
// the same two companies. The A/D engine formula and the default synergy
// constants are NOT changed here.
const ARENA_DEAL_TERMS = {
  deal_type: "full_acquisition",
  premium: 0.30,
  cash_pct: 0.5,
  stock_pct: 0.5,
  financing_cost: 0.05,
  tax_rate: 0.25,
  synergy_mode: "default", // V5.1 default cost synergy
};

let CARDS = [];
// V5.2.2 precomputed directed-pair lookup map, keyed by `${acqId}__${tgtId}`.
// Built once from /api/modeling/ma/arena/pairs; the runtime only reads it.
let PAIRS_INDEX = {};
// V5.5 Settlement Board: the two deterministic rankings + tension callout, as
// returned by the SAME /api/modeling/ma/arena/pairs endpoint (additive field).
// The front end only renders them; it never re-sorts via per-pair calculate calls.
let BOARDS = null;
// V5.7.0.1 ready gate. The Settlement Board's tier pips need the deck (CARDS)
// to resolve a ticker -> arena_tier, while the rows themselves come from BOARDS.
// These two loads race (loadCards / loadPairs run concurrently in init), so we
// track each independently and only render tier-dependent rows once both have
// settled — regardless of which finished first. No timers, no payload changes.
let cardsLoaded = false;
let pairsLoaded = false;
let selected = { acq: null, tgt: null };
// V5.8 Deal Review Queue: the LIGHT pair last rendered on the result card. Used
// only to build a queue summary on demand — never re-computed, never heavy.
let currentLight = null;

// V5.6 Tabletop shell state. All front-end-only: no backend user state, no
// persistence, no login. HAND is a working tray drawn deterministically from
// the deck; DRAG_ID tracks the card currently being dragged.
let HAND = [];
const HAND_SIZE = 7;
let handOffset = 0;
let DRAG_ID = null;

// V5.11.2.1 War Room deck filter/sort. Pure presentation state over the loaded
// deck — it changes ONLY what the binder shows (count, order, which cards are
// visible), never the deck truth, the pairs payload, Match Points, the robot,
// Settlement or the Queue. `tier` matches arena_tier; `sector` matches the
// localized sector label; sort `default` keeps the deck's designed order.
let deckFilter = { tier: "all", sector: "all" };
let deckSort = { key: "default", dir: "desc" };
// Tier ranking for the Tier sort: gold > red > blue > green > white.
const TIER_RANK = { gold: 5, red: 4, blue: 3, green: 2, white: 1 };
// Natural default direction per sort key (cap big->small, tier high->low, name A->Z).
const SORT_DEFAULT_DIR = { default: "desc", cap: "desc", tier: "desc", name: "asc" };

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
  node.classList.remove("arena-tier", "tier-gold", "tier-red", "tier-blue", "tier-green", "tier-white");
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

// Light "feel of size": market cap = share_price x shares (both deck fields).
// Shown as a $T/$B sense, not a precise valuation.
function marketCapSense(company) {
  const cap = Number(company.share_price) * Number(company.shares); // USD mm
  if (!isFinite(cap) || cap <= 0) return "-";
  if (cap >= 1_000_000) return `$${(cap / 1_000_000).toFixed(2)}T`;
  return `$${fmt(cap)}B`;
}

// Numeric market cap for sorting. Graceful fallback: a missing/invalid
// share_price or shares yields 0 (sorts to the bottom of a descending list)
// rather than throwing or producing NaN comparisons.
function marketCapNum(c) {
  const cap = Number(c?.share_price) * Number(c?.shares);
  return isFinite(cap) && cap > 0 ? cap : 0;
}

function prettyTag(tag) {
  return String(tag || "").replace(/_/g, " ");
}

// V5.9.6 localization accessors — read the shared deterministic display map with
// a graceful fallback to the English deck fields if the module is absent.
function cnName(c) {
  return (window.CardLocalization && window.CardLocalization.nameCn(c)) || c?.name || c?.ticker || "—";
}
function cnSector(c) {
  return (window.CardLocalization && window.CardLocalization.sectorCn(c)) || c?.sector || "—";
}
function enName(c) {
  return (window.CardLocalization && window.CardLocalization.enName(c)) || c?.name || "";
}

async function loadCards() {
  try {
    const resp = await fetch(`${API}/api/modeling/ma/samples`);
    const data = await resp.json();
    CARDS = data.companies || [];
  } catch (e) {
    CARDS = [];
    showError("无法加载公司牌 / Could not load the company deck.");
  }
  cardsLoaded = true; // set even on error so the board never waits forever
  populateDeckFilters(); // sector options come from the live deck
  renderDeck();
  renderSettlementWhenReady(); // deck is now available for tier pips
}

// Load the precomputed directed-pair map once. If it fails, PAIRS_INDEX stays
// empty and showDeal() transparently falls back to the calculate API.
async function loadPairs() {
  try {
    const resp = await fetch(`${API}/api/modeling/ma/arena/pairs`);
    const data = await resp.json();
    const index = {};
    for (const p of data.pairs || []) {
      index[pairKey(p.acquirer_id, p.target_id)] = p;
    }
    PAIRS_INDEX = index;
    BOARDS = data.boards || null;
    if (BOARDS && data.pair_count) BOARDS.pair_count = data.pair_count;
  } catch (e) {
    PAIRS_INDEX = {};
    BOARDS = null;
    console.info("[arena] pairs map unavailable; will use calculate fallback");
  }
  pairsLoaded = true;
  renderSettlementWhenReady();
}

// Safe DOM element helper: dynamic text always goes through textContent, never
// innerHTML interpolation (V5.6 Step 0 security fix — no XSS via deck fields).
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

// Shared company-card builder for the deck binder AND the player hand. Every
// dynamic field (ticker / name / sector / tags / cap) is set via textContent;
// the card is draggable (drag-to-deal) and a drop target (A dropped onto B).
function buildCompanyCard(c, variant) {
  const card = el("div", variant === "hand" ? "hand-card" : "co-card");
  applyArenaTier(card, c);
  card.dataset.id = c.id;
  card.setAttribute("role", "button");
  card.setAttribute("tabindex", "0");
  card.setAttribute("draggable", "true");
  card.setAttribute("aria-label", `${c.ticker} ${cnName(c)} ${c.name || ""}`.trim());

  const acqBadge = el("span", "co-badge acq", "买方");
  const tgtBadge = el("span", "co-badge tgt", "标的");
  card.append(acqBadge, tgtBadge, arenaTierBadge(c, "co-tier"),
    el("div", "co-ticker", c.ticker), el("div", "co-name", cnName(c)));
  const en = enName(c);
  if (en) card.append(el("div", "co-en", en));
  card.append(el("div", "co-sub", cnSector(c)));

  const cap = el("div", "co-cap");
  cap.append(document.createTextNode("市值感 "));
  cap.append(el("b", null, marketCapSense(c)));
  card.append(cap);

  const chips = el("div", "co-chips");
  for (const t of (c.tags?.strategic_tags || []).slice(0, 2)) {
    chips.append(el("span", "co-chip", prettyTag(t)));
  }
  card.append(chips);

  card.addEventListener("click", () => onCardClick(c.id));
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCardClick(c.id); }
  });
  attachDragSource(card, c.id);
  attachCardDropZone(card, c.id);
  return card;
}

// V5.11.2.1 deck view = filter then (optionally) sort. Returns a NEW array; it
// never mutates CARDS, so the underlying deck order / truth is preserved and a
// stable original-index tiebreak keeps equal-key sorts deterministic.
function visibleDeckCards() {
  let list = CARDS.filter((c) => {
    if (deckFilter.tier !== "all" && arenaTier(c) !== deckFilter.tier) return false;
    if (deckFilter.sector !== "all" && cnSector(c) !== deckFilter.sector) return false;
    return true;
  });
  if (deckSort.key !== "default") {
    const dir = deckSort.dir === "asc" ? 1 : -1;
    const order = new Map(CARDS.map((c, i) => [c.id, i]));
    list = list.slice().sort((a, b) => {
      let cmp = 0; // comparators are written ascending; `dir` applies direction
      if (deckSort.key === "cap") cmp = marketCapNum(a) - marketCapNum(b);
      else if (deckSort.key === "tier") cmp = (TIER_RANK[arenaTier(a)] || 0) - (TIER_RANK[arenaTier(b)] || 0);
      else if (deckSort.key === "name") cmp = String(a.ticker || "").localeCompare(String(b.ticker || ""));
      if (cmp !== 0) return cmp * dir;
      return (order.get(a.id) || 0) - (order.get(b.id) || 0); // stable tiebreak
    });
  }
  return list;
}

function renderDeck() {
  const grid = $("deck-grid");
  if (!grid) return;
  const countEl = $("deck-count");
  if (countEl) countEl.textContent = String(CARDS.length); // dynamic, never hardcoded
  const visible = visibleDeckCards();
  grid.textContent = "";
  for (const c of visible) grid.appendChild(buildCompanyCard(c, "deck"));
  const empty = $("deck-empty");
  if (empty) empty.style.display = visible.length ? "none" : "";
  const shown = $("deck-shown-count");
  if (shown) shown.textContent = `显示 ${visible.length} / ${CARDS.length} 张`;
  refreshSelectionUI();
}

// Build the Sector filter options from the LIVE deck (not hardcoded), via safe
// DOM only. Preserves the current selection if it still exists after a reload.
function populateDeckFilters() {
  const sel = $("deck-filter-sector");
  if (!sel) return;
  const current = sel.value || "all";
  const sectors = Array.from(new Set(
    CARDS.map((c) => cnSector(c)).filter((s) => s && s !== "—"),
  )).sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
  sel.textContent = "";
  sel.appendChild(el("option", null, "全部行业 · All sectors")).value = "all";
  for (const s of sectors) {
    sel.appendChild(el("option", null, s)).value = s;
  }
  sel.value = (current === "all" || sectors.includes(current)) ? current : "all";
  if (sel.value !== current) deckFilter.sector = sel.value;
}

// Sync the direction toggle label/state with deckSort. The toggle is inert for
// the "default" (designed-order) sort, where direction has no meaning.
function updateSortDirBtn() {
  const btn = $("deck-sort-dir");
  if (!btn) return;
  btn.disabled = deckSort.key === "default";
  btn.textContent = deckSort.dir === "asc" ? "升序 ↑" : "降序 ↓";
  btn.setAttribute(
    "aria-label",
    deckSort.dir === "asc" ? "当前升序，点击切换为降序" : "当前降序，点击切换为升序",
  );
}

// V5.9.1.1 War Room scalability: the deck stays collapsed (a couple of rows with
// internal scroll) so the page is not flooded as the deck grows. Expanding lifts
// the cap to a viewport-bounded height that still scrolls internally — every
// deck card remains reachable in either state. Pure presentation; no result changes.
function toggleDeckExpanded() {
  const scroll = $("deck-scroll");
  const btn = $("deck-toggle");
  if (!scroll || !btn) return;
  const expanded = scroll.classList.toggle("expanded");
  scroll.classList.toggle("collapsed", !expanded);
  btn.setAttribute("aria-expanded", expanded ? "true" : "false");
  btn.textContent = expanded ? "收起" : "展开全部";
}

// ── Player Hand · front-end-only working tray ───────────────────────────────
// A deterministic window over the deck (no randomness). "换一批手牌" rotates the
// window; it is pure presentation and changes no result.
function drawHand() {
  HAND = [];
  const n = Math.min(HAND_SIZE, CARDS.length);
  for (let i = 0; i < n; i++) HAND.push(CARDS[(handOffset + i) % CARDS.length].id);
  renderHand();
}

function rotateHand() {
  if (!CARDS.length) return;
  handOffset = (handOffset + HAND_SIZE) % CARDS.length;
  drawHand();
}

function renderHand() {
  const tray = $("hand-tray");
  if (!tray) return;
  tray.textContent = "";
  for (const id of HAND) {
    const c = companyById(id);
    if (c) tray.appendChild(buildCompanyCard(c, "hand"));
  }
  refreshSelectionUI();
}

// ── Drag-to-deal · A dropped onto B means A → B (A acquires B) ───────────────
function attachDragSource(node, id) {
  node.addEventListener("dragstart", (e) => {
    DRAG_ID = id;
    try {
      e.dataTransfer.setData("text/plain", id);
      e.dataTransfer.effectAllowed = "copy";
    } catch (_) { /* older browsers */ }
    node.classList.add("dragging");
  });
  node.addEventListener("dragend", () => {
    DRAG_ID = null;
    node.classList.remove("dragging");
    document.querySelectorAll(".drag-over").forEach((n) => n.classList.remove("drag-over"));
  });
}

// Read the dragged company id and validate it against the loaded deck. Never
// trust raw dataTransfer / DOM content: an unknown id yields null (no-op).
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

// Single funnel for changing the deal. Validates both ids against the deck and
// rejects a self-deal, then refreshes the table + light result and closes any
// open ticket so a stale direction can never linger.
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

// Click fallback (touchpad / mobile / keyboard): first pick -> acquirer, second
// -> target. Clicking a selected card deselects it; a further click replaces
// the target. Routed through applySelection so the ticket closes on change.
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
  applySelection();
}

// Read-only deep link: /modeling/ma/arena?acq=<id>&tgt=<id> seats that deal on
// the table. Ids are validated against the deck; unknown ones are ignored.
function deepLinkInit() {
  try {
    const params = new URLSearchParams(window.location.search);
    const acq = params.get("acq");
    const tgt = params.get("tgt");
    if ((acq && companyById(acq)) || (tgt && companyById(tgt))) {
      setDeal(companyById(acq) ? acq : null, companyById(tgt) ? tgt : null);
    }
  } catch (_) { /* malformed query string -> ignore */ }
}

function renderSlot(side, c) {
  const body = $(`slot-${side}-body`);
  const slot = $(`slot-${side}`);
  if (!body) return;
  body.textContent = "";
  if (slot) clearArenaTierClasses(slot);
  if (!c) {
    body.appendChild(el("div", "slot-empty",
      side === "acq" ? "拖入买方牌，或点选一张公司牌" : "拖入标的牌，或再点一张公司牌"));
    return;
  }
  if (slot) applyArenaTier(slot, c);
  body.append(
    el("div", "slot-ticker", c.ticker),
    el("div", "slot-name", cnName(c)),
  );
  const en = enName(c);
  if (en) body.append(el("div", "slot-en", en));
  body.append(
    el("div", "slot-sub", cnSector(c)),
    el("div", "slot-cap", `市值感 ${marketCapSense(c)}`),
    arenaTierBadge(c, "slot-tier"),
  );
}

function refreshSelectionUI() {
  renderSlot("acq", companyById(selected.acq));
  renderSlot("tgt", companyById(selected.tgt));

  document.querySelectorAll(".co-card, .hand-card").forEach((node) => {
    node.classList.toggle("sel-acq", node.dataset.id === selected.acq);
    node.classList.toggle("sel-tgt", node.dataset.id === selected.tgt);
  });

  $("slot-acq").classList.toggle("filled", !!selected.acq);
  $("slot-tgt").classList.toggle("filled", !!selected.tgt);
  $("reverse-btn").disabled = !(selected.acq && selected.tgt);
  $("clear-btn").disabled = !(selected.acq || selected.tgt);

  // Hand off the current selection to the formal tabletop via query string.
  const q = [];
  if (selected.acq) q.push(`acq=${encodeURIComponent(selected.acq)}`);
  if (selected.tgt) q.push(`tgt=${encodeURIComponent(selected.tgt)}`);
  const qs = q.length ? `?${q.join("&")}` : "";
  const startBtn = $("start-tabletop-btn");
  if (startBtn) startBtn.href = "/modeling/ma/arena/play" + qs;
  // V5.9.6.2+: Start Match always begins a clean game — the Match deal table
  // starts empty and the War Room's current selection is intentionally NOT
  // seated there (Match Setup ignores any ?acq/?tgt). The query string is kept
  // on the href only so deep-link parity with the sandbox link is preserved.
  const matchBtn = $("start-match-btn");
  if (matchBtn) matchBtn.href = "/modeling/ma/arena/match/setup" + qs;

  if (!selected.acq && !selected.tgt) {
    flashHint("把一张公司牌拖到另一张牌上：A 拖到 B 表示「A 收购 B」。也可以直接点牌选买方与标的。");
  } else if (!selected.tgt) {
    flashHint("已就位买方，再拖入或点选一张标的牌。");
  } else if (!selected.acq) {
    flashHint("已就位标的，再拖入或点选一张买方牌。");
  } else {
    flashHint("用 ⇄ 反转方向（买方↔标的），结果会重新计算。");
  }
}

function buildPayload() {
  return {
    acquirer: { sample_id: selected.acq },
    target: { sample_id: selected.tgt },
    deal: { ...ARENA_DEAL_TERMS },
    currency: "USD",
  };
}

// Lookup-first flow: prefer the precomputed light pair, fall back to the live
// calculate path only when the pair is missing. The fallback is explicit in
// the code path (it logs and maps the full result into the same light shape),
// never a silent crash.
async function showDeal() {
  showError("");
  const light = PAIRS_INDEX[pairKey(selected.acq, selected.tgt)];
  if (light) {
    renderLight(light);
    return;
  }
  await calculateFallback();
}

// Fallback: same deck ids + Arena terms through /api/modeling/ma/calculate.
// Used when a precomputed pair is absent (e.g. pairs map failed to load).
async function calculateFallback() {
  console.info("[arena] precomputed pair missing; falling back to /api/modeling/ma/calculate", selected);
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
  renderLight(toLight(data.result));
}

// Map a full calculate result into the compact light shape the card renders,
// so the precomputed path and the fallback path share one renderer. Viability
// is carried as its own fields, never merged into the economic ones.
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
    viability_flags_top: (via.flags || []).slice(0, 2).map((f) => ({
      severity: f.severity, category: f.category, title: f.title, rule_id: f.rule_id,
    })),
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
  chips.innerHTML = "";

  // 1) Three-state synergy status (engine-derived label).
  const synChip = document.createElement("span");
  synChip.className = `chip ${SYNERGY_CHIP_CLASS[p.synergy_status] || ""}`;
  synChip.textContent = p.synergy_status_label;
  chips.appendChild(synChip);

  // 2) Default cost synergy tier (高/中/低). Light chip only.
  const tierChip = document.createElement("span");
  tierChip.className = "chip";
  tierChip.textContent = p.default_synergy_tier
    ? `默认协同：${tierLabel(p.default_synergy_tier)}`
    : "默认协同：不可用";
  chips.appendChild(tierChip);

  // 3) Derived economic chip ONLY (not packaged as an Overall Score; viability
  //    is kept separate and never merged into this).
  const econChip = document.createElement("span");
  econChip.className = `chip ${p.is_accretive ? "econ-pos" : "econ-neg"}`;
  econChip.textContent = p.is_accretive ? "经济性：增厚" : "经济性：摊薄";
  chips.appendChild(econChip);

  // 4) Pre-PPA light chip.
  const ppaChip = document.createElement("span");
  ppaChip.className = "chip pre-ppa";
  ppaChip.textContent = `${p.pre_ppa_chip?.label || "Pre-PPA"} · 未计PPA`;
  ppaChip.title = p.pre_ppa_chip?.detail || "";
  chips.appendChild(ppaChip);

  renderViability(p);

  // Deep link into Deal Studio carrying the current acquirer/target.
  $("rc-studio-btn").href =
    `/modeling/ma?acq=${encodeURIComponent(selected.acq)}&tgt=${encodeURIComponent(selected.tgt)}`;

  updateQueueButtons();
}

// Viability is a SEPARATE axis: its own chip row, never merged with the
// economic chips above and never affecting the EPS headline.
function renderViability(p) {
  const box = $("rc-viability-chips");
  box.innerHTML = "";
  const level = p.viability_level || "green";

  const levelChip = document.createElement("span");
  levelChip.className = `vchip level ${level}`;
  levelChip.textContent = p.viability_label || "现实可行性：—";
  box.appendChild(levelChip);

  // Show at most 2 short flag titles (skip the pure-green informational flag).
  const flags = (p.viability_flags_top || []).filter((f) => f.severity !== "green");
  for (const f of flags.slice(0, 2)) {
    const chip = document.createElement("span");
    chip.className = `vchip ${f.severity || ""}`;
    chip.textContent = f.title;
    box.appendChild(chip);
  }
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

// ── V5.5 Settlement Board · dual deterministic result layer ─────────────────
// Renders the two independent rankings the backend already computed. Economic
// and Viability are separate boards — there is no merged overall score. Rows
// are built with DOM + textContent (never innerHTML interpolation), and every
// pair id is validated against the loaded deck before it can change selection.
const VIA_TAG_CLASS = { green: "via-green", yellow: "via-yellow", red: "via-red" };

// V5.7.0.1 race gate. Called whenever either load (deck or boards) settles.
// Tier pips depend on the deck, so when there ARE boards to draw we hold the
// first render until CARDS is also loaded. If pairs failed (BOARDS null) the
// empty-state message needs no deck, so we render as soon as pairs settle.
// Net effect: cards-first and pairs-first both end at a board WITH tier pips,
// and a genuine pairs failure still shows its empty state promptly.
function renderSettlementWhenReady() {
  if (!pairsLoaded) return;           // board outcome not known yet
  if (BOARDS && !cardsLoaded) return; // have rows but no deck -> wait for pips
  renderSettlement();
}

function renderSettlement() {
  const countEl = $("sb-pair-count");
  if (countEl) countEl.textContent = (BOARDS && BOARDS.pair_count) ? BOARDS.pair_count : "—";

  const econBox = $("sb-board-econ");
  const viaBox = $("sb-board-via");
  if (!econBox || !viaBox) return;

  if (!BOARDS || !(BOARDS.economic || []).length) {
    econBox.innerHTML = "";
    viaBox.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "sb-empty";
    empty.textContent = "结算榜暂不可用（precomputed pairs 未加载）。";
    econBox.appendChild(empty);
    renderTension();
    return;
  }

  renderBoard(econBox, BOARDS.economic || [], "econ");
  renderBoard(viaBox, BOARDS.viability || [], "via");
  renderTension();
}

function renderTension() {
  const box = $("sb-tension");
  if (!box) return;
  const tension = (BOARDS && BOARDS.tension) || [];
  if (!tension.length) {
    box.style.display = "none";
    box.textContent = "";
    return;
  }
  box.style.display = "";
  box.textContent = "";
  box.appendChild(el("b", null, "反差观察："));
  const names = tension.map((p) => `${p.acquirer_ticker}→${p.target_ticker}`).join("、");
  box.appendChild(el("span", null,
    `${names} 经济性靠前，但现实可行性偏“需审查/高风险”——增厚与可行性是两条独立的轴，仅供解释，不参与排序。`));
}

function renderBoard(box, rows, kind) {
  box.innerHTML = "";
  rows.forEach((p, i) => box.appendChild(buildBoardRow(p, i + 1, kind)));
}

// One deal row. The whole row loads the pair; the trailing button loads it and
// opens the Deal Ticket. Both reuse the existing selection + ticket paths.
function buildBoardRow(p, rank, kind) {
  const row = document.createElement("div");
  row.className = "sb-row";
  row.dataset.acq = p.acquirer_id;
  row.dataset.tgt = p.target_id;

  const rankEl = document.createElement("span");
  rankEl.className = "sb-rank";
  rankEl.textContent = `#${rank}`;

  const deal = document.createElement("span");
  deal.className = "sb-deal";
  const acq = document.createElement("span"); acq.className = "sb-acq";
  const acqCard = companyById(p.acquirer_id);
  if (acqCard) acq.appendChild(el("span", `tier-pip arena-tier tier-${arenaTier(acqCard)}`));
  acq.appendChild(document.createTextNode(p.acquirer_ticker || "—"));
  const arrow = document.createElement("span"); arrow.className = "sb-arrow"; arrow.textContent = "→";
  const tgt = document.createElement("span"); tgt.className = "sb-tgt";
  const tgtCard = companyById(p.target_id);
  if (tgtCard) tgt.appendChild(el("span", `tier-pip arena-tier tier-${arenaTier(tgtCard)}`));
  tgt.appendChild(document.createTextNode(p.target_ticker || "—"));
  deal.append(acq, arrow, tgt);

  const eps = document.createElement("span");
  const epsText = pct(p.accretion_dilution_pct);
  if (epsText === "-") {
    eps.className = "sb-eps na";
    eps.textContent = "数据不足";
  } else {
    eps.className = `sb-eps ${p.is_accretive ? "accretive" : "dilutive"}`;
    eps.textContent = epsText;
  }

  const tags = document.createElement("span");
  tags.className = "sb-tags";
  if (kind === "via") {
    // Viability board: level + risk-flag count chip, then a short summary.
    const n = Number(p.viability_flags_count || 0);
    addBoardTag(tags, `${shortViaLabel(p)} · ${n === 0 ? "无风险旗标" : n + " 项关注"}`, VIA_TAG_CLASS[p.viability_level] || "");
    const sum = document.createElement("span");
    sum.className = "sb-via-summary";
    sum.textContent = p.viability_summary || "";
    sum.title = p.viability_summary || "";
    tags.appendChild(sum);
  } else {
    // Economic board: synergy status, default tier, Pre-PPA, viability chip.
    addBoardTag(tags, p.synergy_status_label, "syn");
    addBoardTag(tags, p.default_synergy_tier ? `默认协同：${tierLabel(p.default_synergy_tier)}` : "默认协同：不可用", "");
    addBoardTag(tags, "未计PPA", "");
    addBoardTag(tags, shortViaLabel(p), VIA_TAG_CLASS[p.viability_level] || "");
  }

  const actions = el("span", "sb-actions");
  const queueBtn = el("button", "sb-queue", "加入");
  queueBtn.type = "button";
  queueBtn.title = "加入候选交易队列";
  queueBtn.addEventListener("click", (e) => {
    e.stopPropagation(); // don't trigger the row load
    addToQueue(p, "settlement");
  });
  const btn = el("button", "sb-ticket", "票据");
  btn.type = "button";
  btn.addEventListener("click", (e) => {
    e.stopPropagation(); // don't double-trigger the row click
    selectPairFromBoard(p.acquirer_id, p.target_id, true);
  });
  actions.append(queueBtn, btn);

  row.append(rankEl, deal, eps, tags, actions);
  row.addEventListener("click", () => selectPairFromBoard(p.acquirer_id, p.target_id, false));
  return row;
}

function addBoardTag(container, text, cls) {
  if (!text) return;
  const tag = document.createElement("span");
  tag.className = `sb-tag ${cls || ""}`;
  tag.textContent = text;
  container.appendChild(tag);
}

// Strip the redundant "现实可行性：" prefix for the compact board chips.
function shortViaLabel(p) {
  const label = p.viability_label || "";
  return label.replace("现实可行性：", "可行性 ") || "可行性 —";
}

// Load a board pick into the Arena selection. Inputs are validated against the
// loaded deck (never trusted blindly), so a stray id cannot change state.
function selectPairFromBoard(acqId, tgtId, openTk) {
  if (!companyById(acqId) || !companyById(tgtId) || acqId === tgtId) return;
  setDeal(acqId, tgtId); // shared funnel: validates, refreshes, closes ticket
  const card = $("result-card");
  if (card && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "center" });
  if (openTk) openTicket();
}

function setBoardTab(board) {
  document.querySelectorAll(".sb-tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.board === board);
  });
  $("sb-board-econ").style.display = board === "econ" ? "" : "none";
  $("sb-board-via").style.display = board === "via" ? "" : "none";
}

// ── V5.4 Deal Ticket · mid-density review overlay ───────────────────────────
// The ticket is the MIDDLE information-density tier: richer than the Arena
// light card, lighter than Deal Studio. It is opened on demand and reuses the
// SAME /api/modeling/ma/calculate full result (same Arena terms via
// buildPayload) as the light card and Deal Studio — it never re-implements EPS
// math, so all three tiers show the same accretion/dilution number.
let ticketReqId = 0;

function addChip(container, text, cls) {
  const chip = document.createElement("span");
  chip.className = `chip ${cls || ""}`;
  chip.textContent = text;
  container.appendChild(chip);
  return chip;
}

function closeTicket() {
  $("ticket-overlay").style.display = "none";
}

async function openTicket() {
  if (!selected.acq || !selected.tgt) return;
  const overlay = $("ticket-overlay");
  overlay.style.display = "flex";
  $("ticket-loading").style.display = "";
  $("ticket-body").style.display = "none";
  $("ticket-error").style.display = "none";

  const acq = companyById(selected.acq);
  const tgt = companyById(selected.tgt);
  $("ticket-title").textContent =
    `Deal Ticket · ${acq ? acq.ticker : "—"} 收购 ${tgt ? tgt.ticker : "—"}`;
  // Deep link carries the CURRENT direction; reversing then reopening shows the
  // new direction because the title and link are rebuilt from `selected`.
  $("tk-studio-btn").href =
    `/modeling/ma?acq=${encodeURIComponent(selected.acq)}&tgt=${encodeURIComponent(selected.tgt)}`;

  // Guard against a stale response overwriting a newer one (e.g. reverse then
  // reopen quickly): only the latest request id is allowed to render.
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
  if (reqId !== ticketReqId) return; // a newer request superseded this one
  if (!data || data.status !== "ok" || !data.result) {
    const msg = ((data && data.flags) || []).map((f) => f.message).join(" ");
    showTicketError(msg || "计算失败 / Calculation failed.");
    return;
  }
  renderTicket(data.result);
}

function showTicketError(msg) {
  $("ticket-loading").style.display = "none";
  $("ticket-body").style.display = "none";
  const el = $("ticket-error");
  el.style.display = "";
  el.textContent = msg;
}

// Render the mid-density ticket from the full calculate result. Economic and
// Viability live in physically separate blocks; there is no combined score.
function renderTicket(r) {
  $("ticket-loading").style.display = "none";
  $("ticket-error").style.display = "none";
  $("ticket-body").style.display = "";

  // A. 交易摘要 — EPS headline + the same light chips as the result card.
  const epsEl = $("tk-eps-val");
  epsEl.textContent = pct(r.accretion_dilution);
  epsEl.className = `tk-eps-val ${r.is_accretive ? "accretive" : "dilutive"}`;

  const ctx = r.synergy_context || {};
  const def = ctx.default_cost_synergy;
  const chips = $("tk-summary-chips");
  chips.innerHTML = "";
  addChip(chips, r.synergy_status_label, SYNERGY_CHIP_CLASS[r.synergy_status] || "");
  addChip(chips, def ? `默认协同：${tierLabel(def.synergy_tier)}` : "默认协同：不可用", "");
  addChip(chips, r.is_accretive ? "经济性：增厚" : "经济性：摊薄", r.is_accretive ? "econ-pos" : "econ-neg");
  const ppaChip = addChip(chips, `${r.pre_ppa_chip?.label || "Pre-PPA"} · 未计PPA`, "pre-ppa");
  ppaChip.title = r.pre_ppa_chip?.detail || "";

  // B. 经济性拆解 — mid-density fields. Lighter than Deal Studio's full table
  // (no new_shares / pro-forma shares / source_meta), enough to explain why.
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
  grid.innerHTML = "";
  for (const [label, value, sub] of cells) {
    const cell = document.createElement("div");
    cell.className = "tk-cell";
    const l = document.createElement("div"); l.className = "tk-cell-label"; l.textContent = label;
    const v = document.createElement("div"); v.className = "tk-cell-value"; v.textContent = value;
    const s = document.createElement("div"); s.className = "tk-cell-sub"; s.textContent = sub;
    cell.append(l, v, s);
    grid.appendChild(cell);
  }

  renderTicketViability(r.viability_context);
}

// C. 现实可行性 — its own block. Level + summary + full flag list (title +
// message + small rule_id / triggered_tags). Never merged into EPS.
function renderTicketViability(via) {
  const levelEl = $("tk-via-level");
  const summaryEl = $("tk-via-summary");
  const flagsEl = $("tk-via-flags");
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
    const card = document.createElement("div");
    card.className = `tk-flag ${f.severity || ""}`;

    const title = document.createElement("div");
    title.className = "tk-flag-title";
    title.textContent = f.title || "";
    const cat = document.createElement("span");
    cat.className = "tk-flag-cat";
    cat.textContent = f.category || "";
    title.appendChild(cat);

    const msg = document.createElement("div");
    msg.className = "tk-flag-msg";
    msg.textContent = f.message || "";

    const meta = document.createElement("div");
    meta.className = "tk-flag-meta";
    const tags = (f.triggered_tags || []).join(", ");
    meta.textContent = `rule: ${f.rule_id || "-"}${tags ? " · tags: " + tags : ""}`;

    card.append(title, msg, meta);
    flagsEl.appendChild(card);
  }
}

// ── V5.8 Deal Review Queue · 候选交易队列 ────────────────────────────────────
// A front-end-only shortlist of "deals I want to revisit this round" backed by
// the shared window.DealQueue (sessionStorage). Adding a candidate reuses light
// data already on the page (current result card, settlement board row) — it
// NEVER triggers a calculate. Every id is deck-validated before it can change
// selection, and rows are built with safe DOM (textContent), no innerHTML.
const QUEUE_FROM_LABEL = {
  war_room: "来自 War Room",
  play_table: "来自 牌桌",
  ticket: "来自 票据",
  settlement: "来自 结算榜",
};

function tierClassName(t) {
  return ARENA_TIERS.has(t) ? t : "white";
}

// Resolve a queue added_from into a display label. Robot sources (robot_md etc.)
// are mapped to a "机器人 · <难度>" label; window.RobotOpponent may be absent on
// the War Room page, so fall back to the raw difficulty suffix.
function queueFromLabel(from) {
  if (from && from.indexOf("robot") === 0) {
    const diff = from.replace("robot_", "");
    const meta = window.RobotOpponent && window.RobotOpponent.meta(diff);
    return "机器人 · " + (meta ? meta.short : diff || "Robot");
  }
  return QUEUE_FROM_LABEL[from] || "来自 牌桌";
}

function shortViaLabelStr(label) {
  return (label || "").replace("现实可行性：", "可行性 ") || "可行性 —";
}

// Build a light queue item from any source that carries acquirer_id/target_id
// plus the compact economic+viability summary (the result card light pair, or a
// settlement board pair). Ticker/name/tier are re-read from the validated deck
// card, never trusted from the source object.
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

function addToQueue(src, addedFrom) {
  const item = queueItemFrom(src, addedFrom);
  if (!item) return;
  if (window.DealQueue.has(item.acquirer_id, item.target_id)) {
    flashHint("已在候选队列 · Already in Deal Review Queue。");
    updateQueueButtons();
    return;
  }
  const res = window.DealQueue.add(item);
  if (!res.ok && res.reason === "full") {
    flashHint("候选队列已满，先移除一些再加入。");
  }
}

// Add the deal currently seated on the table (its light pair). Used by the
// result-card and Deal Ticket "加入候选" buttons.
function addCurrentToQueue(addedFrom) {
  if (!currentLight || !selected.acq || !selected.tgt) return;
  addToQueue(
    Object.assign({}, currentLight, { acquirer_id: selected.acq, target_id: selected.tgt }),
    addedFrom,
  );
}

// Reflect membership on the add buttons so a deal already in the queue shows as
// added (and can't be double-added). Driven by selection AND queue changes.
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
  const card = $("result-card");
  if (card && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "center" });
}

function addQueueTag(container, text, cls) {
  if (!text) return;
  container.appendChild(el("span", `q-tag ${cls || ""}`.trim(), text));
}

function buildQueueRow(it) {
  const row = el("div", "queue-row");
  row.dataset.acq = it.acquirer_id;
  row.dataset.tgt = it.target_id;

  const seqEl = el("span", "q-seq", `#${it.added_seq}`);

  const deal = el("span", "q-deal");
  const acq = el("span", "q-acq");
  acq.appendChild(el("span", `tier-pip arena-tier tier-${tierClassName(it.acquirer_tier)}`));
  acq.appendChild(document.createTextNode(it.acquirer_ticker || "—"));
  const arrow = el("span", "q-arrow", "→");
  const tgt = el("span", "q-tgt");
  tgt.appendChild(el("span", `tier-pip arena-tier tier-${tierClassName(it.target_tier)}`));
  tgt.appendChild(document.createTextNode(it.target_ticker || "—"));
  deal.append(acq, arrow, tgt);

  const epsText = pct(it.accretion_dilution_pct);
  const eps = el("span", `q-eps ${epsText === "-" ? "na" : (it.is_accretive ? "accretive" : "dilutive")}`,
    epsText === "-" ? "数据不足" : epsText);

  const tags = el("span", "q-tags");
  addQueueTag(tags, it.economic_label || (it.is_accretive ? "经济性：增厚" : "经济性：摊薄"),
    it.is_accretive ? "econ-pos" : "econ-neg");
  addQueueTag(tags, shortViaLabelStr(it.viability_label), VIA_TAG_CLASS[it.viability_level] || "");
  if (it.default_synergy_tier) {
    addQueueTag(tags, `默认协同：${tierLabel(it.default_synergy_tier)}`, "");
  }
  addQueueTag(tags, queueFromLabel(it.added_from), "q-from");

  const remove = el("button", "q-remove", "✕");
  remove.type = "button";
  remove.title = "从候选队列移除";
  remove.setAttribute("aria-label", "移除该候选");
  remove.addEventListener("click", (e) => {
    e.stopPropagation();
    window.DealQueue.remove(it.acquirer_id, it.target_id);
  });

  row.append(seqEl, deal, eps, tags, remove);
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

async function init() {
  // Static UI wiring (safe before data loads).
  $("reverse-btn").addEventListener("click", reverseDirection);
  $("clear-btn").addEventListener("click", clearSelection);
  $("rc-ticket-btn").addEventListener("click", openTicket);
  $("rc-queue-btn").addEventListener("click", () => addCurrentToQueue("war_room"));
  $("tk-queue-btn").addEventListener("click", () => addCurrentToQueue("ticket"));
  $("ticket-close").addEventListener("click", closeTicket);
  $("ticket-overlay").addEventListener("click", (e) => {
    if (e.target.id === "ticket-overlay") closeTicket();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTicket();
  });
  document.querySelectorAll(".sb-tab").forEach((b) => {
    b.addEventListener("click", () => setBoardTab(b.dataset.board));
  });
  attachSlotDropZone($("slot-acq"), "acq");
  attachSlotDropZone($("slot-tgt"), "tgt");
  $("hand-rotate").addEventListener("click", rotateHand);
  $("deck-toggle").addEventListener("click", toggleDeckExpanded);

  // V5.11.2.1 deck filter/sort controls. Each only re-renders the binder; the
  // deck data, selection, slots, pairs, Settlement and Queue are untouched.
  const tierSel = $("deck-filter-tier");
  if (tierSel) tierSel.addEventListener("change", () => { deckFilter.tier = tierSel.value; renderDeck(); });
  const secSel = $("deck-filter-sector");
  if (secSel) secSel.addEventListener("change", () => { deckFilter.sector = secSel.value; renderDeck(); });
  const sortSel = $("deck-sort");
  if (sortSel) sortSel.addEventListener("change", () => {
    deckSort.key = sortSel.value;
    deckSort.dir = SORT_DEFAULT_DIR[deckSort.key] || "desc";
    updateSortDirBtn();
    renderDeck();
  });
  const dirBtn = $("deck-sort-dir");
  if (dirBtn) dirBtn.addEventListener("click", () => {
    deckSort.dir = deckSort.dir === "asc" ? "desc" : "asc";
    updateSortDirBtn();
    renderDeck();
  });
  updateSortDirBtn();

  // Compact precomputed data drives the board (lookup-first, no per-pair
  // calculate calls). The deck must be loaded before the hand is drawn or a deep link is
  // seated, so that selection ids can be validated against it.
  // V5.8 Deal Review Queue: render the shortlist and keep it in sync. The queue
  // is shared session state, so it survives the War Room <-> Play Table handoff.
  window.DealQueue.subscribe(renderQueue);
  renderQueue();

  loadPairs();
  await loadCards();
  drawHand();
  deepLinkInit();
}

document.addEventListener("DOMContentLoaded", init);
