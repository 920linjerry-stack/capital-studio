// V5.9.2 Match Loop Shell — deterministic five-round match state + Match Points.
//
// This module owns the GAME LOOP only. It is the front-end-only rules layer that
// turns the existing Arena sandbox (deck + precomputed pairs + deterministic
// Robot Opponent) into a playable five-round match: who is at the table, whose
// turn it is, which deals were played, and a local in-match scoreboard.
//
// Hard boundaries (mirrors robot_opponent.js / deal_queue.js):
//   * No LLM, no network call, no random number generator, no dynamic code
//     execution, no DOM.
//   * It NEVER recomputes EPS / synergy / viability — it only READS the existing
//     LIGHT compact-pair fields the page already loaded.
//   * `match_points` is a LOCAL in-match game score ONLY. It is NOT a single
//     merged product-wide total, NOT an investment rating, NOT written into the
//     Economic or Viability ranking layer, NOT sent to the server engine
//     endpoint, and never appears on the precomputed pair feed. It exists purely
//     so a match can have a winner; it is deterministic and explainable (a fixed
//     weighted sum over light fields).
//   * It stores NO source-metadata, field-source maps, filing URLs, full result
//     or audit trail — match deals carry only light ids + tickers + the score.
(function () {
  "use strict";

  const MAX_ROUNDS = 5;

  // V5.9.3 Game-rule resources (first-pass, simple counters — NOT a deck-burn
  // system). Draw is a PER-ROUND allowance (reset every new round); Reshuffle is
  // a WHOLE-MATCH allowance (shared across all five rounds). These gate the hand
  // controls only; they never touch the A/D engine, Match Points, or any result.
  const DRAW_PER_ROUND = 1;
  const RESHUFFLE_PER_MATCH = 2;

  // Turn phases of a single round / the whole match.
  const PHASE = {
    WAITING_PLAYER: "waiting_player",
    ROBOTS_PLAYING: "robots_playing",
    ROUND_RESULT: "round_result",
    MATCH_COMPLETE: "match_complete",
  };

  const PARTICIPANTS = ["player", "robot_1", "robot_2"];

  // ── Match Points · deterministic, explainable LOCAL game score ──────────────
  // A fixed weighted sum over LIGHT compact-pair fields. Same inputs always give
  // the same integer. This is a game score, never an investment rating.
  const VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 };
  const SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 };
  const TIER_RANK = { gold: 5, red: 4, blue: 3, green: 2, white: 1 };

  // ── V5.10.4 Size Feasibility / Reverse-Whale guardrail ──────────────────────
  // Match Points is an investment-committee-style GAME score, not the EPS truth.
  // The EPS engine can legitimately show a small acquirer buying a mega target as
  // hugely accretive (a small-EPS-base artifact); but a committee would never wave
  // such a "reverse whale" through — financing capacity, shareholder approval,
  // control, governance and integration risk all bite. So MP is constrained by a
  // deterministic SIZE FEASIBILITY band based on target/acquirer market cap. This
  // NEVER touches EPS / synergy / viability truth — it only reshapes the game
  // score, and only DOWNWARD (it can never reward a deal). The bands progress from
  // "feasible" (target <= acquirer, untouched) to "extreme" (target far larger,
  // strongly capped). A `penalty` trims; a `cap` is a hard MP ceiling so a huge
  // paper EPS can never make a scale-infeasible deal a top deal. Bands are matched
  // by `ratio <= max` (ascending), first match wins.
  const SIZE_FEASIBILITY_BANDS = [
    { max: 1.0, band: "feasible", penalty: 0, cap: null },
    { max: 1.5, band: "minor", penalty: -4, cap: null },
    { max: 2.0, band: "moderate", penalty: -8, cap: 52 },
    { max: 3.0, band: "reverse_whale", penalty: -10, cap: 36 },
    { max: 4.0, band: "severe", penalty: -12, cap: 24 },
    { max: Infinity, band: "extreme", penalty: -14, cap: 14 },
  ];
  const SIZE_BAND_LABEL = {
    minor: "规模可行性 · 体量略大",
    moderate: "规模可行性 · 反向收购顾虑",
    reverse_whale: "规模可行性 · 蛇吞象封顶",
    severe: "规模可行性 · 规模严重不匹配封顶",
    extreme: "规模可行性 · 规模不可行封顶",
  };

  function numOr(v, fallback) {
    return typeof v === "number" && isFinite(v) ? v : fallback;
  }

  // Market cap "sense" from the static card (share_price * shares). Returns null
  // when either field is missing / non-finite / non-positive, so a data gap never
  // crashes and simply skips the size adjustment (conservative fallback).
  function marketCapOf(card) {
    if (!card) return null;
    const price = Number(card.share_price);
    const sh = Number(card.shares);
    if (!isFinite(price) || !isFinite(sh)) return null;
    const cap = price * sh;
    return cap > 0 ? cap : null;
  }

  // Directed size ratio = target market cap / acquirer market cap. > 1 means the
  // target is larger than the buyer (a reverse-whale lean). null when either side
  // lacks a usable market cap. Directional: sizeRatio(A,B) !== sizeRatio(B,A).
  function sizeRatio(acqCard, tgtCard) {
    const a = marketCapOf(acqCard);
    const t = marketCapOf(tgtCard);
    if (!a || !t) return null;
    return t / a;
  }

  // Map a directed size ratio to its feasibility band, or null when the ratio is
  // unavailable / invalid (missing market cap) — caller then applies no change.
  function sizeFeasibilityBand(ratio) {
    if (typeof ratio !== "number" || !isFinite(ratio) || ratio <= 0) return null;
    for (const b of SIZE_FEASIBILITY_BANDS) {
      if (ratio <= b.max) return b;
    }
    return SIZE_FEASIBILITY_BANDS[SIZE_FEASIBILITY_BANDS.length - 1];
  }

  // Bounded saturating EPS transform (same family as robot_opponent.js): keeps
  // "more accretive scores higher" while stopping one +400% outlier from
  // dominating the whole game score.
  function epsSignal(eps) {
    return eps / (1 + Math.abs(eps));
  }

  function tierRankOf(card) {
    return card ? (TIER_RANK[card.arena_tier] || 1) : 1;
  }

  // "Story" relatedness from static deck tags only (no new judgement). Same as
  // the robot's relatedness read so the two layers tell one consistent story.
  function relatedness(acqCard, tgtCard) {
    if (!acqCard || !tgtCard) return 0;
    let score = 0;
    if (acqCard.sector && acqCard.sector === tgtCard.sector) score += 1;
    if (acqCard.industry && acqCard.industry === tgtCard.industry) score += 1;
    return score; // 0, 1, or 2
  }

  // Return a deterministic, explainable breakdown of the match points for one
  // light pair. `cardById` is optional; without it the story/tier terms are 0.
  function matchPointsBreakdown(pair, cardById) {
    const parts = [];
    if (!pair) return { total: 0, parts };

    const eps = numOr(pair.accretion_dilution_pct, null);
    if (eps === null) {
      // A data-insufficient deal scores a small floor, never participates as a
      // strong economic play. Deterministic.
      parts.push({ key: "eps", label: "经济性 · 数据不足", value: 0 });
    } else {
      const econ = Math.round(epsSignal(eps) * 40); // economic axis: roughly ±40
      parts.push({ key: "eps", label: "经济性 · EPS 信号", value: econ });
      if (pair.is_accretive) parts.push({ key: "accretive", label: "增厚加成", value: 8 });
      else if (eps < -0.5) parts.push({ key: "weak_econ", label: "经济性极弱 · 罚分", value: -10 });
    }

    const level = pair.viability_level;
    if (level in VIA_LEVEL_POINTS) {
      const label = level === "red" ? "可行性 · 红灯罚分"
        : level === "yellow" ? "可行性 · 黄灯" : "可行性 · 绿灯";
      parts.push({ key: "viability", label, value: VIA_LEVEL_POINTS[level] });
    }
    const flags = numOr(pair.viability_flags_count, 0);
    if (flags > 0) parts.push({ key: "flags", label: "可行性风险旗 · 罚分", value: -Math.min(12, flags * 4) });

    const syn = SYNERGY_TIER_POINTS[pair.default_synergy_tier] || 0;
    if (syn) parts.push({ key: "synergy", label: "默认协同档", value: syn });
    if (pair.synergy_status === "self_accretive" || pair.synergy_status === "synergy_supported") {
      parts.push({ key: "synergy_status", label: "协同支持", value: 4 });
    }

    if (typeof cardById === "function") {
      const acqCard = cardById(pair.acquirer_id);
      const tgtCard = cardById(pair.target_id);
      const rel = relatedness(acqCard, tgtCard);
      if (rel) parts.push({ key: "story", label: "同业故事加成", value: rel * 5 });
      const tierBonus = Math.round((tierRankOf(acqCard) + tierRankOf(tgtCard)) - 2); // 0..8
      if (tierBonus) parts.push({ key: "tier", label: "Card Tier 牌面加成", value: tierBonus });
    }

    // Economic + viability + story subtotal before the size feasibility guardrail.
    let total = 0;
    for (const p of parts) total += p.value;

    // V5.10.4 size feasibility / reverse-whale guardrail. Computed LAST so its
    // penalty + ceiling bind on the full economic score (a high paper EPS can
    // never lift a scale-infeasible deal past the band cap). cardById gated and
    // ratio-guarded: missing market cap => no change (conservative fallback). The
    // adjustment is recorded as a single net-delta part so the breakdown still
    // sums to `total`, and it is strictly <= 0 (never rewards a deal).
    if (typeof cardById === "function") {
      const ratio = sizeRatio(cardById(pair.acquirer_id), cardById(pair.target_id));
      const b = sizeFeasibilityBand(ratio);
      if (b && b.band !== "feasible") {
        let adjusted = total + b.penalty;
        if (b.cap !== null) adjusted = Math.min(adjusted, b.cap);
        const delta = adjusted - total;
        if (delta !== 0) {
          parts.push({
            key: "size_feasibility",
            label: SIZE_BAND_LABEL[b.band] || "规模可行性",
            value: delta,
            ratio: Math.round(ratio * 100) / 100,
            band: b.band,
          });
          total = adjusted;
        }
      }
    }
    return { total, parts };
  }

  function matchPoints(pair, cardById) {
    return matchPointsBreakdown(pair, cardById).total;
  }

  // ── Match lifecycle ─────────────────────────────────────────────────────────
  function normalizeDifficulty(d) {
    if (window.RobotOpponent && typeof window.RobotOpponent.normalizeDifficulty === "function") {
      return window.RobotOpponent.normalizeDifficulty(d);
    }
    const allowed = ["intern", "analyst", "associate", "vp", "md"];
    return allowed.indexOf(d) >= 0 ? d : "analyst"; // illegal difficulty -> Analyst
  }

  function dirKey(acquirerId, targetId) {
    return `${acquirerId}->${targetId}`;
  }

  // ── V5.9.6.2 seeded opening hand / draw order ───────────────────────────────
  // A deterministic PRNG (mulberry32) + Fisher–Yates shuffle used ONLY to lay out
  // the per-match card draw order. This is a GAME shuffle, never a financial
  // judgement: it does not touch EPS / synergy / viability / Match Points / robot
  // strategy — those stay deterministic from the frozen deck. Same seed always
  // yields the same order (replayable / restorable); a new match gets a new seed.
  function mulberry32(seed) {
    let a = (seed >>> 0) || 1;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // Deterministic shuffle of an id list under a seed (input array not mutated).
  function seededShuffle(ids, seed) {
    const arr = Array.isArray(ids) ? ids.slice() : [];
    const rand = mulberry32(seed);
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
    }
    return arr;
  }
  // The per-match draw order = a seeded shuffle of the deck ids.
  function buildDrawOrder(seed, ids) {
    return seededShuffle(ids, seed);
  }

  // Build a fresh match from a setup config { robots: [{difficulty}, {difficulty}] }.
  // The pure engine stays hand/used/seed agnostic — the front-end attaches the
  // per-match game seed + draw order + hand lifecycle fields (see startNewMatch).
  function createMatch(config) {
    const robots = (config && Array.isArray(config.robots)) ? config.robots : [];
    const diff1 = normalizeDifficulty(robots[0] && robots[0].difficulty);
    const diff2 = normalizeDifficulty(robots[1] && robots[1].difficulty);
    return {
      match_started: true,
      round_index: 1,
      max_rounds: MAX_ROUNDS,
      phase: PHASE.WAITING_PLAYER,
      // V5.9.3 resource counters: Draw resets each round, Reshuffle is match-wide.
      draw_allowance: DRAW_PER_ROUND,
      reshuffle_allowance: RESHUFFLE_PER_MATCH,
      participants: {
        player: { id: "player", kind: "player", name: "你 · You", points: 0 },
        robot_1: { id: "robot_1", kind: "robot", difficulty: diff1, points: 0 },
        robot_2: { id: "robot_2", kind: "robot", difficulty: diff2, points: 0 },
      },
      // One record per round: { round, player, robot_1, robot_2 } where each is a
      // light deal record or null.
      rounds: [],
      // Flat list of all played deals this match (<= 3 * MAX_ROUNDS = 15).
      deals: [],
    };
  }

  // ── V5.9.3 hand resources (Draw per round / Reshuffle per match) ────────────
  // Defensive readers normalize a restored/legacy state that predates these
  // counters, so an old in-progress match never produces NaN allowances.
  function drawRemaining(state) {
    if (!state) return 0;
    return typeof state.draw_allowance === "number" && isFinite(state.draw_allowance)
      ? Math.max(0, state.draw_allowance) : DRAW_PER_ROUND;
  }
  function reshuffleRemaining(state) {
    if (!state) return 0;
    return typeof state.reshuffle_allowance === "number" && isFinite(state.reshuffle_allowance)
      ? Math.max(0, state.reshuffle_allowance) : RESHUFFLE_PER_MATCH;
  }
  function canDraw(state) { return drawRemaining(state) > 0; }
  function canReshuffle(state) { return reshuffleRemaining(state) > 0; }
  // Consume one Draw / Reshuffle. Returns true when it was spent, false when the
  // allowance was already exhausted (caller shows a light hint, no error).
  function useDraw(state) {
    if (!canDraw(state)) return false;
    state.draw_allowance = drawRemaining(state) - 1;
    return true;
  }
  function useReshuffle(state) {
    if (!canReshuffle(state)) return false;
    state.reshuffle_allowance = reshuffleRemaining(state) - 1;
    return true;
  }

  function currentRoundRecord(state) {
    let rec = state.rounds.find((r) => r.round === state.round_index);
    if (!rec) {
      rec = { round: state.round_index, player: null, robot_1: null, robot_2: null };
      state.rounds.push(rec);
    }
    return rec;
  }

  // A light, provenance-free deal record. Only ids + tickers + the local score.
  function dealRecord(participant, round, pair, cardById) {
    const acqCard = typeof cardById === "function" ? cardById(pair.acquirer_id) : null;
    const tgtCard = typeof cardById === "function" ? cardById(pair.target_id) : null;
    return {
      participant,
      round,
      acquirer_id: pair.acquirer_id,
      target_id: pair.target_id,
      acquirer_ticker: pair.acquirer_ticker || (acqCard && acqCard.ticker) || "",
      target_ticker: pair.target_ticker || (tgtCard && tgtCard.ticker) || "",
      accretion_dilution_pct: numOr(pair.accretion_dilution_pct, null),
      is_accretive: !!pair.is_accretive,
      viability_level: pair.viability_level || "green",
      match_points: matchPoints(pair, cardById),
    };
  }

  // All directed keys already played by anyone this match (used to keep robots
  // from copying a deal already on the board).
  function playedKeys(state) {
    return state.deals.map((d) => dirKey(d.acquirer_id, d.target_id));
  }

  // V5.10.2.4 — the companies still in the player's CURRENT hand. Robots may not
  // use these (they belong to the player this round). A card the player has
  // already played this round has left the hand into the used pile, so it is NOT
  // here and is free for a robot to use (used-card unlock). Hand-agnostic when no
  // hand exists (legacy / sandbox), so robots fall back to the full board.
  function currentHandCompanies(state) {
    const set = new Set();
    const hand = Array.isArray(state && state.hand) ? state.hand : [];
    for (const id of hand) if (id) set.add(id);
    return set;
  }

  // Union of any number of id sets/arrays into one fresh Set (skips falsy ids).
  function unionCompanies() {
    const out = new Set();
    for (let i = 0; i < arguments.length; i++) {
      const s = arguments[i];
      if (!s) continue;
      if (typeof s.forEach === "function") s.forEach((id) => { if (id) out.add(id); });
      else if (Array.isArray(s)) for (const id of s) if (id) out.add(id);
    }
    return out;
  }

  // Deterministically pick one robot deal, trying each company-exclusion set in
  // priority order (strictest first); the first that yields a candidate wins. The
  // directed-key exclusion (`baseExclude`) always applies on top. With 45 cards /
  // 1980 pairs the strictest set practically always succeeds — the relaxation
  // chain only guards a pathologically exhausted board so a round never crashes /
  // white-screens. A relaxation is logged (debug-safe), never written into match
  // state, and stays deterministic (same inputs -> same level -> same pick).
  function robotPickWithFallback(select, difficulty, pairs, baseExclude, cardById, companyLevels) {
    const levels = (Array.isArray(companyLevels) && companyLevels.length) ? companyLevels : [new Set()];
    for (let i = 0; i < levels.length; i++) {
      const pick = select(difficulty, pairs, baseExclude, { cardById, excludedCompanies: levels[i] });
      if (pick && pick.acquirer_id && pick.target_id) {
        if (i > 0 && typeof console !== "undefined" && console.info) {
          console.info("[match] robot company-overlap exclusion relaxed (level " + i + ")");
        }
        return pick;
      }
    }
    return null;
  }

  // Player plays one deal for the current round. `getPair(acqId,tgtId)` returns a
  // light compact pair (or null). Returns { ok, reason? }.
  function playerPlay(state, acquirerId, targetId, getPair, cardById) {
    if (!state || state.phase !== PHASE.WAITING_PLAYER) return { ok: false, reason: "phase" };
    if (!acquirerId || !targetId || acquirerId === targetId) return { ok: false, reason: "invalid" };
    const pair = typeof getPair === "function" ? getPair(acquirerId, targetId) : null;
    if (!pair) return { ok: false, reason: "no_pair" };
    const rec = currentRoundRecord(state);
    const deal = dealRecord("player", state.round_index, pair, cardById);
    rec.player = deal;
    state.deals.push(deal);
    state.participants.player.points += deal.match_points;
    state.phase = PHASE.ROBOTS_PLAYING;
    return { ok: true, deal };
  }

  // Both robots play one deal each for the current round, AFTER the player.
  // Deterministic (no randomness). `pairs` is the light pair list; `selectFn`
  // defaults to RobotOpponent.selectRobotDeal.
  //
  // V5.10.2.4 same-round company-overlap rule. Two robots in one round must NOT
  // share any company, and neither may use a company still in the player's
  // CURRENT hand. So:
  //   * Robot 1 excludes the player's current-hand companies.
  //   * Robot 2 excludes the player's current-hand companies AND every company
  //     Robot 1 just used (acquirer + target) — the two robots stay company-
  //     disjoint (no shared acquirer, no shared target, no acquirer-vs-target
  //     overlap either).
  // The directed-key exclusion (everything already played this match, incl. the
  // player's just-played deal) still applies on top. Cards the player already
  // played left the hand into the used pile, so they are NOT in the hand set and a
  // robot may re-use them (used-card unlock). If a fully-constrained candidate set
  // is (impossibly) empty, the exclusion relaxes in a fixed order that keeps the
  // player-hand block longest — robot-vs-robot overlap is dropped before it.
  function robotsPlay(state, pairs, getPair, cardById, selectFn) {
    if (!state || state.phase !== PHASE.ROBOTS_PLAYING) return { ok: false, reason: "phase" };
    const select = selectFn || (window.RobotOpponent && window.RobotOpponent.selectRobotDeal);
    if (typeof select !== "function") return { ok: false, reason: "no_robot" };
    const rec = currentRoundRecord(state);

    // Exclude everything already played this match (incl. the player's just-played
    // deal). Directed: A->B excluded does not exclude B->A.
    const baseExclude = playedKeys(state).slice();

    // Per-round company exclusion: the player's current hand is off-limits to both
    // robots; Robot 1's used companies are then added to Robot 2's exclusion.
    const handCompanies = currentHandCompanies(state);
    const robotUsed = new Set();

    // Robot 1 — block the player's current hand; relax to none only if no
    // candidate remains (practically never with 45 cards / 1980 pairs).
    const pick1 = robotPickWithFallback(
      select, state.participants.robot_1.difficulty, pairs, baseExclude, cardById,
      [handCompanies, new Set()],
    );
    if (pick1 && pick1.acquirer_id && pick1.target_id) {
      const p1 = typeof getPair === "function" ? getPair(pick1.acquirer_id, pick1.target_id) : null;
      if (p1) {
        const d1 = dealRecord("robot_1", state.round_index, p1, cardById);
        d1.rationale = Array.isArray(pick1.rationale) ? pick1.rationale : [];
        rec.robot_1 = d1;
        state.deals.push(d1);
        state.participants.robot_1.points += d1.match_points;
        baseExclude.push(dirKey(d1.acquirer_id, d1.target_id));
        robotUsed.add(d1.acquirer_id);
        robotUsed.add(d1.target_id);
      }
    }

    // Robot 2 — block the player's current hand AND every company Robot 1 just
    // used. Relaxation order keeps the player-hand block longest: it drops the
    // robot-vs-robot overlap (level 1) before the player-hand block (level 2).
    const pick2 = robotPickWithFallback(
      select, state.participants.robot_2.difficulty, pairs, baseExclude, cardById,
      [unionCompanies(handCompanies, robotUsed), handCompanies, new Set()],
    );
    if (pick2 && pick2.acquirer_id && pick2.target_id) {
      const p2 = typeof getPair === "function" ? getPair(pick2.acquirer_id, pick2.target_id) : null;
      if (p2) {
        const d2 = dealRecord("robot_2", state.round_index, p2, cardById);
        d2.rationale = Array.isArray(pick2.rationale) ? pick2.rationale : [];
        rec.robot_2 = d2;
        state.deals.push(d2);
        state.participants.robot_2.points += d2.match_points;
      }
    }

    state.phase = PHASE.ROUND_RESULT;
    return { ok: true, round: rec };
  }

  // Round winner = highest match_points that round; deterministic tie-break by
  // participant order (player, robot_1, robot_2). Returns participant id or "draw"
  // when no deal was played.
  function roundWinner(rec) {
    if (!rec) return "draw";
    let best = null;
    let tie = false;
    for (const id of PARTICIPANTS) {
      const deal = rec[id];
      if (!deal) continue;
      const pts = numOr(deal.match_points, 0);
      if (best === null || pts > best.pts) { best = { id, pts }; tie = false; }
      else if (pts === best.pts) { tie = true; }
    }
    if (best === null) return "draw";
    return tie ? "draw" : best.id;
  }

  // Advance to the next round, or complete the match after MAX_ROUNDS.
  function nextRound(state) {
    if (!state) return;
    if (state.round_index >= state.max_rounds) {
      state.phase = PHASE.MATCH_COMPLETE;
      return;
    }
    state.round_index += 1;
    state.phase = PHASE.WAITING_PLAYER;
    // A new round restores the per-round Draw allowance; Reshuffle is match-wide
    // and is NOT restored here.
    state.draw_allowance = DRAW_PER_ROUND;
  }

  // Final standings sorted by total points desc, deterministic tie-break by the
  // fixed participant order. Pure read — does not mutate state.
  function rankings(state) {
    const order = { player: 0, robot_1: 1, robot_2: 2 };
    return PARTICIPANTS.map((id) => ({
      id,
      points: numOr(state.participants[id].points, 0),
      participant: state.participants[id],
    })).sort((a, b) => (b.points - a.points) || (order[a.id] - order[b.id]));
  }

  // Match winner: top of the ranking, or "draw" when the top two tie on points.
  function winner(state) {
    const r = rankings(state);
    if (!r.length) return "draw";
    if (r.length >= 2 && r[0].points === r[1].points) return "draw";
    return r[0].id;
  }

  // Best deal (highest match_points) played by one participant across the match.
  function bestDealFor(state, participantId) {
    let best = null;
    for (const d of state.deals) {
      if (d.participant !== participantId) continue;
      if (best === null || numOr(d.match_points, 0) > numOr(best.match_points, 0)) best = d;
    }
    return best;
  }

  window.MatchEngine = {
    MAX_ROUNDS,
    DRAW_PER_ROUND,
    RESHUFFLE_PER_MATCH,
    PHASE,
    PARTICIPANTS: PARTICIPANTS.slice(),
    createMatch,
    mulberry32,
    seededShuffle,
    buildDrawOrder,
    matchPoints,
    matchPointsBreakdown,
    marketCapOf,
    sizeRatio,
    sizeFeasibilityBand,
    playerPlay,
    robotsPlay,
    roundWinner,
    nextRound,
    rankings,
    winner,
    bestDealFor,
    drawRemaining,
    reshuffleRemaining,
    canDraw,
    canReshuffle,
    useDraw,
    useReshuffle,
    key: dirKey,
    normalizeDifficulty,
  };
})();
