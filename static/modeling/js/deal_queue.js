// V5.8 Deal Review Queue — front-end-only session shortlist.
//
// A LIGHT review list of "deals I want to keep / compare / revisit this round".
// It is NOT a favorites product: no login, no database, no backend per-user
// state, no runtime file writes. The whole queue is front-end session state and
// it is allowed to vanish on a hard refresh.
//
// Storage boundary (sessionStorage `ma_deal_queue_v1`):
//   * stores ONLY a directed pair key (acquirer->target) plus a small whitelist
//     of light summary fields (tickers, names, deck tier, EPS accretion/dilution
//     %, economic label, viability level/label, synergy status, Pre-PPA marker,
//     added_from, a local session sequence number);
//   * NEVER stores the deck source-metadata trail (field-source maps, filing /
//     quote / company-facts links), raw viability audit details, triggered tag
//     lists, rule identifiers, or a full computed deal result. add() copies only
//     the whitelisted keys, so a heavier object handed in is silently reduced to
//     the light shape (defence in depth);
//   * the data is non-sensitive (public tickers + a derived EPS sign). It is
//     used so the War Room and the Play Table (same tab, same session) can share
//     one shortlist. If sessionStorage is unavailable (private mode / quota) the
//     queue degrades to in-memory only — no error surfaces.
//
// This module owns state + storage only; it touches NO DOM. Each page validates
// every id against its own loaded deck before changing selection, and renders
// rows with safe DOM (textContent), never innerHTML interpolation.
(function () {
  "use strict";

  const STORAGE_KEY = "ma_deal_queue_v1";
  // Concurrency / performance guardrail: a review shortlist, not a database.
  const MAX_ITEMS = 60;

  // The ONLY string fields a queue item may carry. Anything outside this list
  // (e.g. a source-metadata blob) is dropped by sanitize().
  const STRING_FIELDS = [
    "acquirer_id", "acquirer_ticker", "acquirer_name", "acquirer_tier", "acquirer_tier_label",
    "target_id", "target_ticker", "target_name", "target_tier", "target_tier_label",
    "economic_label", "synergy_status", "synergy_status_label", "default_synergy_tier",
    "viability_level", "viability_label", "added_from",
  ];

  let seq = 0;
  let items = [];
  const listeners = [];

  // Directed pair key: A->B and B->A are deliberately DIFFERENT candidates.
  function dirKey(acquirerId, targetId) {
    return `${acquirerId}->${targetId}`;
  }

  function safeStr(v) {
    return v === undefined || v === null ? "" : String(v);
  }

  function safeNum(v) {
    if (typeof v === "number" && isFinite(v)) return v;
    const n = Number(v);
    return isFinite(n) ? n : null;
  }

  // Reduce any candidate object to the light whitelist shape. Returns null when
  // it lacks the directed pair ids (the only required keys).
  function sanitize(raw) {
    const out = {};
    for (const k of STRING_FIELDS) out[k] = safeStr(raw[k]);
    out.accretion_dilution_pct = safeNum(raw.accretion_dilution_pct);
    out.is_accretive = !!raw.is_accretive;
    out.pre_ppa = raw.pre_ppa === false ? false : true;
    if (!out.acquirer_id || !out.target_id) return null;
    return out;
  }

  function load() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.items)) return;
      const seen = new Set();
      const clean = [];
      for (const it of data.items) {
        const s = sanitize(it || {});
        if (!s) continue;
        const k = dirKey(s.acquirer_id, s.target_id);
        if (seen.has(k)) continue; // never load a duplicate pair
        seen.add(k);
        s.added_seq = typeof it.added_seq === "number" ? it.added_seq : clean.length + 1;
        clean.push(s);
        if (clean.length >= MAX_ITEMS) break;
      }
      items = clean;
      let maxSeq = 0;
      for (const it of items) if (it.added_seq > maxSeq) maxSeq = it.added_seq;
      seq = typeof data.seq === "number" && data.seq >= maxSeq ? data.seq : maxSeq;
    } catch (_) {
      items = [];
      seq = 0;
    }
  }

  function persist() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ v: 1, seq, items }));
    } catch (_) {
      /* private mode / quota -> stay in memory only, no error surfaced */
    }
  }

  function snapshot() {
    return items.map((it) => Object.assign({}, it));
  }

  function notify() {
    const snap = snapshot();
    for (const fn of listeners) {
      try { fn(snap); } catch (_) { /* a bad listener never breaks the queue */ }
    }
  }

  function list() {
    return snapshot();
  }

  function has(acquirerId, targetId) {
    const k = dirKey(acquirerId, targetId);
    return items.some((it) => dirKey(it.acquirer_id, it.target_id) === k);
  }

  // Add one candidate. Dedupe is by DIRECTED pair, so AAPL->MSFT and MSFT->AAPL
  // coexist. Returns {ok, reason?} so the caller can show a light hint.
  function add(raw) {
    const s = sanitize(raw || {});
    if (!s) return { ok: false, reason: "invalid" };
    if (s.acquirer_id === s.target_id) return { ok: false, reason: "self" };
    if (has(s.acquirer_id, s.target_id)) return { ok: false, reason: "duplicate" };
    if (items.length >= MAX_ITEMS) return { ok: false, reason: "full" };
    s.added_seq = ++seq;
    items.push(s);
    persist();
    notify();
    return { ok: true, item: Object.assign({}, s) };
  }

  function remove(acquirerId, targetId) {
    const k = dirKey(acquirerId, targetId);
    const before = items.length;
    items = items.filter((it) => dirKey(it.acquirer_id, it.target_id) !== k);
    if (items.length === before) return false;
    persist();
    notify();
    return true;
  }

  function clear() {
    if (!items.length) return;
    items = [];
    persist();
    notify();
  }

  function subscribe(fn) {
    if (typeof fn === "function") listeners.push(fn);
    return function unsubscribe() {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    };
  }

  load();

  // Single global surface. Clear Deal on either table must NEVER call clear():
  // clearing the current deal selection is separate from emptying the shortlist.
  window.DealQueue = { add, remove, clear, list, has, subscribe, key: dirKey, MAX_ITEMS };
})();
