// V5.9.2 Match Setup — pick two robot opponents + difficulties, then hand the
// match config to the formal Match table.
//
// Front-end only. The ONLY randomness here is a controlled session-seeded LCG
// used exclusively for the "Randomize difficulty" UI convenience — it never
// touches any financial calculation, the engine, or the robot strategy. We avoid
// a runtime RNG so the pick is reproducible within a session and monkeypatchable
// in tests. No network, no LLM, no innerHTML interpolation.
(function () {
  "use strict";

  const SETUP_STORAGE_KEY = "ma_match_setup_v1";
  const MATCH_STATE_KEY = "ma_match_state_v1"; // cleared so a new setup starts fresh

  const DIFFICULTIES = (window.RobotOpponent && window.RobotOpponent.DIFFICULTIES) ||
    ["intern", "analyst", "associate", "vp", "md"];
  const DEFAULT_DIFFICULTY = (window.RobotOpponent && window.RobotOpponent.DEFAULT_DIFFICULTY) || "analyst";

  const DIFF_DESC = {
    intern: { name: "实习生 · Intern", desc: "只追 EPS 增厚，不顾可行性——最容易被高 EPS 风险交易吸引。" },
    analyst: { name: "分析师 · Analyst", desc: "偏 EPS，但会软避开最明显的红灯交易。" },
    associate: { name: "高级分析师 · Associate", desc: "在 EPS、可行性与行业故事之间求平衡。" },
    vp: { name: "副总裁 · VP", desc: "重交易叙事，硬性回避红灯（监管死局）。" },
    md: { name: "董事总经理 · MD", desc: "风险调整后最稳的交易，硬性回避红灯。" },
  };

  // Default seats: one mid rung, one strong rung — a readable first match.
  const seatState = [
    { seat: 1, difficulty: "analyst" },
    { seat: 2, difficulty: "vp" },
  ];

  const $ = (id) => document.getElementById(id);

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function normDiff(d) {
    if (window.RobotOpponent && typeof window.RobotOpponent.normalizeDifficulty === "function") {
      return window.RobotOpponent.normalizeDifficulty(d);
    }
    return DIFFICULTIES.indexOf(d) >= 0 ? d : DEFAULT_DIFFICULTY;
  }

  // ── Controlled session-seeded pseudo-random (UI convenience only) ───────────
  // A tiny LCG seeded once from the session start time. Reproducible within the
  // session, never affects finance/strategy, and exposed so tests can override.
  let _seed = (Date.now() >>> 0) || 1;
  function seededInt(n) {
    // LCG (Numerical Recipes constants); returns 0..n-1.
    _seed = (1664525 * _seed + 1013904223) >>> 0;
    return n > 0 ? _seed % n : 0;
  }
  function randomDifficulty() {
    return DIFFICULTIES[seededInt(DIFFICULTIES.length)];
  }

  function setSeatDifficulty(seatIdx, difficulty) {
    seatState[seatIdx].difficulty = normDiff(difficulty);
    renderSeat(seatIdx);
  }

  function renderSeat(seatIdx) {
    const seat = seatState[seatIdx];
    const card = $(`ms-seat-${seat.seat}`);
    if (!card) return;
    card.querySelectorAll(".ms-diff").forEach((row) => {
      const isSel = row.dataset.diff === seat.difficulty;
      row.classList.toggle("selected", isSel);
      const radio = row.querySelector("input");
      if (radio) radio.checked = isSel;
    });
    const pick = $(`ms-seat-pick-${seat.seat}`);
    if (pick) {
      pick.textContent = "";
      pick.append(document.createTextNode("当前难度："));
      pick.append(el("b", null, (DIFF_DESC[seat.difficulty] || {}).name || seat.difficulty));
    }
  }

  function buildSeatCard(seatIdx) {
    const seat = seatState[seatIdx];
    const card = el("div", "ms-seat");
    card.id = `ms-seat-${seat.seat}`;

    const head = el("div", "ms-seat-head");
    head.append(
      el("div", "ms-seat-title", `机器人席位 ${seat.seat} · Robot Seat ${seat.seat}`),
      el("span", "ms-seat-badge", `SEAT ${seat.seat}`),
    );
    card.append(head);
    card.append(el("div", "ms-seat-sub", "选择这名机器人对手的难度档，或随机抽取。"));

    const list = el("div", "ms-diff-list");
    DIFFICULTIES.forEach((d) => {
      const meta = DIFF_DESC[d] || { name: d, desc: "" };
      const row = el("label", "ms-diff");
      row.dataset.diff = d;
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `seat-${seat.seat}-diff`;
      radio.value = d;
      radio.addEventListener("change", () => setSeatDifficulty(seatIdx, d));
      const body = el("div", "ms-diff-body");
      body.append(el("div", "ms-diff-name", meta.name), el("div", "ms-diff-desc", meta.desc));
      row.append(radio, body);
      list.append(row);
    });
    card.append(list);

    const foot = el("div", "ms-seat-foot");
    const rand = el("button", "ms-rand-btn", "随机抽取难度 · Randomize");
    rand.type = "button";
    rand.addEventListener("click", () => setSeatDifficulty(seatIdx, randomDifficulty()));
    const pick = el("span", "ms-seat-pick");
    pick.id = `ms-seat-pick-${seat.seat}`;
    foot.append(rand, pick);
    card.append(foot);
    return card;
  }

  function renderSeats() {
    const host = $("ms-seats");
    if (!host) return;
    host.textContent = "";
    seatState.forEach((_, idx) => host.append(buildSeatCard(idx)));
    seatState.forEach((_, idx) => renderSeat(idx));
  }

  function randomizeAll() {
    seatState.forEach((_, idx) => setSeatDifficulty(idx, randomDifficulty()));
  }

  // V5.9.6.2: the Match starts with a CLEAN deal table — the War Room's current
  // acquirer/target selection (any ?acq/?tgt on this setup URL) is intentionally
  // NOT forwarded to the Match page. (The Deal Review Queue still persists across
  // pages; a queued deal is preview/load only and never auto-seats the table.)
  function startMatch() {
    const config = {
      v: 1,
      robots: seatState.map((s) => ({ seat: s.seat, difficulty: normDiff(s.difficulty) })),
    };
    try {
      sessionStorage.setItem(SETUP_STORAGE_KEY, JSON.stringify(config));
      sessionStorage.removeItem(MATCH_STATE_KEY); // a fresh setup always starts a new match
    } catch (_) { /* private mode: the Match page falls back to defaults */ }
    window.location.href = "/modeling/ma/arena/match/play";
  }

  function init() {
    renderSeats();
    const all = $("ms-randomize-all");
    if (all) all.addEventListener("click", randomizeAll);
    const start = $("ms-start-match");
    if (start) start.addEventListener("click", startMatch);
  }

  document.addEventListener("DOMContentLoaded", init);

  // Exposed for tests/inspection only (e.g. seeding the LCG). Never used by the
  // financial path.
  window.MatchSetup = {
    SETUP_STORAGE_KEY,
    seatState,
    randomDifficulty,
    _setSeed: function (s) { _seed = (s >>> 0) || 1; },
  };
})();
