// V5.9.0 Robot Opponent — deterministic strategy over precomputed pairs.
// V5.9.5 Robot Retune under Hand Lifecycle — rebalanced difficulty ladder.
//
// The robot is NOT an LLM and never goes to the network. It selects one deal
// from the SAME frozen 45-company deck and 1980 precomputed directed pairs the
// page already loaded from /api/modeling/ma/arena/pairs. It generates NO new
// financial judgement: it only reads existing LIGHT compact-pair fields (EPS
// accretion/dilution, economic/synergy status, default synergy tier, viability
// level + risk-flag count, deck tier, strategic tags, pair direction) and ranks
// them with a fixed, explainable weight table per difficulty.
//
// V5.9.5 retune (player now has a hand lifecycle; robots stay hand-agnostic, so
// an over-strong global picker felt unfair to beginners). Two deterministic
// levers were added on top of the existing weight ladder — NO randomness, NO
// new model truth, NO Match Points / engine / board change:
//   * `outlierDistrust` — above EPS_TRUST_CAP the higher rungs DISCOUNT
//     implausibly large accretion (a small-EPS-base artifact, not real synergy).
//     This stops Analyst/Associate from grabbing the single global EPS outlier.
//   * `rankSkip` — a rung deliberately settles for the Nth-best deal of its OWN
//     deterministic ranking instead of the argmax. The Intern (rankSkip 40) is
//     still wowed by big EPS but lands a "good but not top" deal — typically a
//     high-EPS, weaker-viability combo it does not scrutinise — never the
//     global optimum. MD/VP keep rankSkip 0 (they pick their true best).
//
// Hard boundaries: no LLM, no runtime market reaction, no runtime synergy /
// regulatory generation, no source-metadata / audit trail, no random number
// generator, no dynamic code execution, no network call. The internal
// `strategy_rank` is for ROBOT selection ONLY — it is never surfaced as a
// product-wide total score and never enters the Economic or Viability boards.
// Rationale chips come from fixed rule templates, never generated text.
(function () {
  "use strict";

  // The five difficulty rungs of the ladder (ordered weakest -> strongest).
  const DIFFICULTIES = ["intern", "analyst", "associate", "vp", "md"];
  const DEFAULT_DIFFICULTY = "analyst";

  const DIFFICULTY_META = {
    intern:    { label: "Intern Bot · 实习生",     short: "实习生",     badge: "INTERN" },
    analyst:   { label: "Analyst Bot · 分析师",     short: "分析师",     badge: "ANALYST" },
    associate: { label: "Associate Bot · 高级分析师", short: "高级分析师", badge: "ASSOCIATE" },
    vp:        { label: "VP Bot · 副总裁",          short: "副总裁",     badge: "VP" },
    md:        { label: "MD Bot · 董事总经理",       short: "董事总经理", badge: "MD" },
  };

  // Internal strategy weights — robot selection ONLY (never a product score).
  // The ladder progresses from "naive EPS chaser" (Intern) to "risk-adjusted,
  // story-aware" (MD). `redVeto:"hard"` removes red-viability deals from the
  // candidate set entirely; `softRedPenalty` only discounts them.
  //
  // V5.9.5 added two per-rung deterministic knobs (see header):
  //   * `outlierDistrust` — discount on EPS above EPS_TRUST_CAP (artifact wariness).
  //   * `rankSkip` — pick the (rankSkip)-th best of this rung's own ranking, not
  //     the argmax. Intern's 40 is what keeps it off the global-optimum deals;
  //     the elite rungs stay at 0 and pick their true best.
  const EPS_TRUST_CAP = 0.6; // +60% accretion: above this, big EPS is "too good to be true".
  const STRATEGY = {
    intern:    { eps: 1.00, viaPenalty: 0.00, flagPenalty: 0.00, tier: 0.00, related: 0.00, synergy: 0.00, redVeto: "none", softRedPenalty: 0.20, outlierDistrust: 0.00, rankSkip: 40 },
    analyst:   { eps: 0.90, viaPenalty: 0.14, flagPenalty: 0.05, tier: 0.05, related: 0.06, synergy: 0.10, redVeto: "none", softRedPenalty: 0.35, outlierDistrust: 0.34, rankSkip: 2 },
    associate: { eps: 0.78, viaPenalty: 0.30, flagPenalty: 0.12, tier: 0.16, related: 0.20, synergy: 0.22, redVeto: "none", softRedPenalty: 0.45, outlierDistrust: 0.30, rankSkip: 0 },
    vp:        { eps: 0.55, viaPenalty: 0.55, flagPenalty: 0.22, tier: 0.28, related: 0.42, synergy: 0.34, redVeto: "hard", softRedPenalty: 0.00, outlierDistrust: 0.55, rankSkip: 0 },
    md:        { eps: 0.46, viaPenalty: 0.78, flagPenalty: 0.30, tier: 0.42, related: 0.58, synergy: 0.46, redVeto: "hard", softRedPenalty: 0.00, outlierDistrust: 0.72, rankSkip: 0 },
  };

  const VIA_LEVEL_NUM = { green: 0, yellow: 1, red: 2 };
  const SYNERGY_TIER_STRENGTH = { high: 1.0, medium: 0.6, low: 0.3, none: 0.0 };
  const TIER_RANK = { gold: 5, red: 4, blue: 3, green: 2, white: 1 };

  function normalizeDifficulty(d) {
    return DIFFICULTIES.indexOf(d) >= 0 ? d : DEFAULT_DIFFICULTY;
  }

  function dirKey(acquirerId, targetId) {
    return `${acquirerId}->${targetId}`;
  }

  function numOr(v, fallback) {
    return typeof v === "number" && isFinite(v) ? v : fallback;
  }

  function tierRank(card) {
    return card ? (TIER_RANK[card.arena_tier] || 1) : 1;
  }

  // "Story" relatedness from static deck tags only (no new judgement): same
  // sector / industry and overlapping strategic tags read as a more narratable
  // combination. Capped to [0,1].
  function relatedness(acqCard, tgtCard) {
    if (!acqCard || !tgtCard) return 0;
    let score = 0;
    if (acqCard.sector && acqCard.sector === tgtCard.sector) score += 0.5;
    if (acqCard.industry && acqCard.industry === tgtCard.industry) score += 0.2;
    const a = (acqCard.tags && acqCard.tags.strategic_tags) || [];
    const t = new Set((tgtCard.tags && tgtCard.tags.strategic_tags) || []);
    let overlap = 0;
    for (const tag of a) if (t.has(tag)) overlap++;
    score += Math.min(0.3, overlap * 0.15);
    return Math.min(1, score);
  }

  // Map raw EPS accretion/dilution into a bounded signal via a monotonic
  // saturating transform, then (V5.9.5) optionally discount implausibly large
  // accretion above EPS_TRUST_CAP by `distrust`. The base transform keeps "more
  // accretive is preferred" so a naive Intern (distrust 0) is still wowed by raw
  // EPS; the distrust term lets the sophisticated rungs treat a +400%-on-a-tiny-
  // base number as the small-base artifact it usually is, so they diverge from
  // the raw EPS leaderboard instead of all grabbing the single global outlier.
  function epsSignal(eps, distrust) {
    const base = eps / (1 + Math.abs(eps));
    if (eps > EPS_TRUST_CAP) return base - (numOr(distrust, 0)) * (eps - EPS_TRUST_CAP);
    return base;
  }

  // Deterministic strategy score for one compact pair under one weight set.
  // Returns null when the pair is unusable (no finite EPS) or vetoed (hard red).
  function scorePair(pair, weights, ctx) {
    const eps = numOr(pair.accretion_dilution_pct, null);
    if (eps === null) return null; // data-insufficient pairs are never selected
    const level = pair.viability_level;
    if (weights.redVeto === "hard" && level === "red") return null;

    const viaNum = VIA_LEVEL_NUM[level] !== undefined ? VIA_LEVEL_NUM[level] : 1;
    const flags = numOr(pair.viability_flags_count, 0);
    const synergy = SYNERGY_TIER_STRENGTH[pair.default_synergy_tier] || 0;
    const softRed = weights.redVeto !== "hard" && level === "red" ? 1 : 0;

    let tierStrength = 0;
    let related = 0;
    if (ctx && typeof ctx.cardById === "function") {
      const acqCard = ctx.cardById(pair.acquirer_id);
      const tgtCard = ctx.cardById(pair.target_id);
      tierStrength = (tierRank(acqCard) + tierRank(tgtCard)) / 10;
      related = relatedness(acqCard, tgtCard);
    }

    return (
      weights.eps * epsSignal(eps, weights.outlierDistrust) -
      weights.viaPenalty * viaNum -
      weights.flagPenalty * flags -
      weights.softRedPenalty * softRed +
      weights.tier * tierStrength +
      weights.related * related +
      weights.synergy * synergy
    );
  }

  // Fixed rule-template rationale chips (NO generated text). The first chip is
  // the difficulty's strategy flavour; the rest are derived from the pair's own
  // light fields so the user can see WHY the robot picked it.
  const STRATEGY_FLAVOUR = {
    intern: "策略：被高 EPS 吸引，较少权衡风险",
    analyst: "策略：偏 EPS，避开最明显红灯",
    associate: "策略：平衡 EPS / 可行性 / 行业故事",
    vp: "策略：重交易叙事，避开监管死局",
    md: "策略：风险调整后最稳的交易",
  };

  function rationaleFor(difficulty, pair, ctx) {
    const chips = [];
    chips.push({ kind: "flavour", text: STRATEGY_FLAVOUR[difficulty] || STRATEGY_FLAVOUR.analyst });
    chips.push({
      kind: pair.is_accretive ? "econ-pos" : "econ-neg",
      text: pair.is_accretive ? "经济性：增厚" : "经济性：摊薄",
    });
    const viaShort = (pair.viability_label || "").replace("现实可行性：", "可行性 ") || "可行性 —";
    chips.push({ kind: "via-" + (pair.viability_level || "green"), text: viaShort });
    if (pair.synergy_status_label) chips.push({ kind: "synergy", text: pair.synergy_status_label });
    if (ctx && typeof ctx.cardById === "function") {
      const acqCard = ctx.cardById(pair.acquirer_id);
      const tgtCard = ctx.cardById(pair.target_id);
      if (acqCard && tgtCard && acqCard.sector && acqCard.sector === tgtCard.sector) {
        chips.push({ kind: "story", text: "同业故事 · " + acqCard.sector });
      }
    }
    return chips;
  }

  // Build the exclude set from a queue/recent state. Accepts an array of items
  // ({acquirer_id,target_id}) or directed key strings. Directed: A->B excluded
  // does NOT exclude B->A.
  function toExcludeSet(state) {
    const set = new Set();
    if (!Array.isArray(state)) return set;
    for (const it of state) {
      if (!it) continue;
      if (typeof it === "string") { set.add(it); continue; }
      if (it.acquirer_id && it.target_id) set.add(dirKey(it.acquirer_id, it.target_id));
    }
    return set;
  }

  // V5.10.2.4 — a COMPANY-level exclusion set. Unlike `toExcludeSet` (which bans
  // specific directed pairs), this bans whole companies: a banned id may appear as
  // NEITHER acquirer NOR target in this selection. Accepts an array of ids or a
  // Set; anything else yields an empty (no-op) set. Used by the Match round
  // orchestration to keep two robots in one round company-disjoint and to keep a
  // robot off the player's current-hand companies. Empty/undefined => no effect,
  // so every existing caller (Play Table sandbox, tests) is unchanged.
  function toCompanySet(ids) {
    if (ids instanceof Set) return ids;
    const set = new Set();
    if (Array.isArray(ids)) for (const id of ids) if (id) set.add(id);
    return set;
  }

  // The core deterministic selection. Same (difficulty, pairs, excludeState)
  // ALWAYS yields the same pair. Candidates are ranked by score desc with a
  // directed-key-string tie-break (stable regardless of input ordering), then the
  // rung's `rankSkip` picks the Nth-best instead of the argmax. With rankSkip 0
  // this is the plain best deal; the Intern's rankSkip walks it down to a "good
  // but not top" deal so it never lands the global optimum. No randomness.
  function selectRobotDeal(difficulty, pairs, excludeState, options) {
    const diff = normalizeDifficulty(difficulty);
    const weights = STRATEGY[diff];
    const ctx = options || {};
    const exclude = toExcludeSet(excludeState);
    // V5.10.2.4 company-level ban (acquirer OR target). Same deterministic ranking
    // — this only narrows the candidate set, it never reweights a score.
    const excludeCompanies = toCompanySet(ctx.excludedCompanies);
    const list = Array.isArray(pairs) ? pairs : [];

    const scored = [];
    for (const pair of list) {
      if (!pair || !pair.acquirer_id || !pair.target_id) continue;
      if (pair.acquirer_id === pair.target_id) continue; // never a self-deal
      const key = dirKey(pair.acquirer_id, pair.target_id);
      if (exclude.has(key)) continue;
      if (excludeCompanies.has(pair.acquirer_id) || excludeCompanies.has(pair.target_id)) continue;
      const score = scorePair(pair, weights, ctx);
      if (score === null) continue; // data-insufficient / hard-vetoed
      scored.push({ score, key, pair });
    }
    if (!scored.length) return null;

    // Deterministic ranking: higher score first, equal score broken by the
    // directed key string. Identical inputs always sort identically.
    scored.sort(function (a, b) {
      if (a.score > b.score + 1e-9) return -1;
      if (b.score > a.score + 1e-9) return 1;
      return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
    });

    // Rank window: settle for the rankSkip-th best (clamped into range), so a
    // weaker rung deterministically avoids the top deals it lacks the skill to
    // earn. Always the top of what remains -> the pick is stable and, with an
    // exclude set growing each round, walks down the ranking for variety.
    const skip = Math.max(0, numOr(weights.rankSkip, 0));
    const chosen = scored[Math.min(skip, scored.length - 1)];

    return {
      acquirer_id: chosen.pair.acquirer_id,
      target_id: chosen.pair.target_id,
      difficulty: diff,
      rationale: rationaleFor(diff, chosen.pair, ctx),
      // Internal strategy rank ONLY — never rendered as a product-wide total score.
      strategy_rank: chosen.score,
    };
  }

  window.RobotOpponent = {
    DIFFICULTIES: DIFFICULTIES.slice(),
    DEFAULT_DIFFICULTY,
    meta: function (d) { return DIFFICULTY_META[normalizeDifficulty(d)]; },
    normalizeDifficulty,
    selectRobotDeal,
    scorePair, // exposed for testing/inspection only
    key: dirKey,
  };
})();
