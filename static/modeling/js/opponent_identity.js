// V5.10.2 Opponent Identity & Presence — presentation layer only.
//
// Assigns stable fictional banker display names, abstract monogram sigils, and
// finite scripted dialogue to robot_1 / robot_2 seats. Selection is fully
// deterministic from (match_seed, seat, difficulty, round, outcome). Internal
// participant ids stay robot_1 / robot_2; nothing here enters engine/API/state.

(function () {
  "use strict";

  const RANK = {
    intern: { cn: "实习生", en: "Intern" },
    analyst: { cn: "分析师", en: "Analyst" },
    associate: { cn: "高级分析师", en: "Associate" },
    vp: { cn: "副总裁", en: "VP" },
    md: { cn: "董事总经理", en: "MD" },
  };

  // V5.10.2.1 banker rank colors — presentation only; NOT card tier / viability.
  const RANK_COLOR = {
    intern: { color: "#c7d0da", glow: "rgba(199,208,218,0.22)", pillText: "#0d1117" },
    analyst: { color: "#45c99a", glow: "rgba(69,201,154,0.24)", pillText: "#0d1117" },
    associate: { color: "#58a6ff", glow: "rgba(88,166,255,0.24)", pillText: "#0d1117" },
    vp: { color: "#e45b78", glow: "rgba(228,91,120,0.26)", pillText: "#fff" },
    md: { color: "#e6bd5a", glow: "rgba(230,189,90,0.30)", pillText: "#1b1404" },
  };

  const NAME_POOL = {
    intern: [
      { first: "Theo", last: "Vance" },
      { first: "Priya", last: "Anand" },
      { first: "Sam", last: "Okoro" },
      { first: "Mia", last: "Chen" },
    ],
    analyst: [
      { first: "Marcus", last: "Lehn" },
      { first: "Sofia", last: "Reyes" },
      { first: "Jun", last: "Park" },
      { first: "Nora", last: "Ellis" },
    ],
    associate: [
      { first: "Dana", last: "Osei" },
      { first: "Ken", last: "Murata" },
      { first: "Elena", last: "Faro" },
      { first: "Iris", last: "Novak" },
    ],
    vp: [
      { first: "Adrian", last: "Cole" },
      { first: "Lena", last: "Volkov" },
      { first: "Raymond", last: "Suh" },
      { first: "Clara", last: "Wynn" },
    ],
    md: [
      { first: "Jerry", last: "Lin" },
      { first: "Vivienne", last: "Roark" },
      { first: "Sterling", last: "Voss" },
      { first: "Margaret", last: "Ainsley" },
      { first: "Arthur", last: "Vale" },
    ],
  };

  // Finite scripted pools — no runtime LLM, no fetch.
  const DIALOGUE = {
    intern: {
      showdown: [
        "这笔 EPS 看起来很能打。",
        "我先冲一笔高增厚。",
        "增厚数字不错，我先押上。",
      ],
      round_win: [
        "居然赢了？也许模型没看错。",
        "这轮增厚站住了。",
        "好吧，先拿下一分。",
      ],
      round_loss: [
        "好吧，风险我可能看轻了。",
        "下轮我再把结构看清楚。",
      ],
      // V5.10.3 Match Ceremony — final winner verdict line (finite, deterministic).
      final_winner: [
        "我……我真的赢了这张桌子？",
        "EPS 还是有用的，对吧？",
      ],
    },
    analyst: {
      showdown: [
        "模型跑完，这笔能过第一轮。",
        "数字站得住，我押这笔。",
        "增厚和可行性都在容忍区间。",
      ],
      round_win: [
        "数字站得住，结果不意外。",
        "模型给出的最优解，这轮是我的。",
        "增厚领先，合理结果。",
      ],
      round_loss: [
        "你的结构更干净，这轮算你的。",
        "你的数字更稳，我认了。",
      ],
      final_winner: [
        "模型站住了，结果自然会跟上。",
        "这场是数字纪律的胜利。",
      ],
    },
    associate: {
      showdown: [
        "EPS、可行性、行业逻辑都对得上。",
        "故事和风险平衡得不错。",
        "这笔交易各轴都过得去。",
      ],
      round_win: [
        "平衡得不错，这轮我来。",
        "结构和叙事都更完整。",
        "各轴对齐，拿下这轮。",
      ],
      round_loss: [
        "你的交易结构更稳。",
        "你的平衡更好，这轮归你。",
      ],
      final_winner: [
        "平衡比激进更耐打。",
        "这五轮，结构赢了噪音。",
      ],
    },
    vp: {
      showdown: [
        "这笔交易有故事，委员会会听。",
        "叙事成立，风险也没有挡死。",
        "委员会听得懂这笔逻辑。",
      ],
      round_win: [
        "叙事赢了，委员会会买账。",
        "故事和风险都站住了。",
        "这轮话语权在我这边。",
      ],
      round_loss: [
        "漂亮的一手，你拿走这轮。",
        "你的说服角度更好，认了。",
      ],
      final_winner: [
        "能被委员会买账的故事，才是好交易。",
        "这场我赢在叙事，也赢在执行路径。",
      ],
    },
    md: {
      showdown: [
        "风险调整后，这是桌上最稳的一笔。",
        "资本会流向更克制的判断。",
        "纪律优先，这笔经得起推敲。",
      ],
      round_win: [
        "意料之中，风险调整后的最优解。",
        "克制的一手，结果合理。",
        "短期分数不重要，纪律才重要。",
      ],
      round_loss: [
        "短期分数不重要，纪律才重要。",
        "你这笔更经得起委员会追问。",
      ],
      final_winner: [
        "资本会留在最克制的人手里。",
        "纪律，比兴奋更贵。",
      ],
    },
  };

  // V5.10.3 Match Ceremony — room verdict lines for a PLAYER win or a DRAW.
  // These are not tied to a banker rank; they close the committee session.
  // Finite, deterministic, no runtime LLM, no fetch, no RNG.
  const ROOM_VERDICT = {
    player: [
      "这张桌子今晚是你的。",
      "委员会听见了你的交易逻辑。",
    ],
    draw: [
      "委员会未能形成多数意见 · 平局收场。",
      "这一场，没有人完全说服整张桌子。",
    ],
  };

  const HUE_BAND = {
    intern: [32, 48],
    analyst: [198, 218],
    associate: [158, 178],
    vp: [252, 272],
    md: [36, 52],
  };

  function normalizeDifficulty(diff) {
    if (window.MatchEngine && window.MatchEngine.normalizeDifficulty) {
      return window.MatchEngine.normalizeDifficulty(diff);
    }
    const d = String(diff || "analyst").toLowerCase();
    return RANK[d] ? d : "analyst";
  }

  function rankClass(difficulty) {
    const norm = normalizeDifficulty(difficulty);
    return `rank-${norm}`;
  }

  function rankColor(difficulty) {
    const norm = normalizeDifficulty(difficulty);
    return RANK_COLOR[norm] || RANK_COLOR.analyst;
  }

  function hashMix(seed, ...parts) {
    let h = (Number(seed) >>> 0) || 1;
    for (const part of parts) {
      const s = String(part);
      for (let i = 0; i < s.length; i++) {
        h = Math.imul(31, h) + s.charCodeAt(i) | 0;
      }
      h = Math.imul(h ^ (h >>> 16), 2246822507) ^ Math.imul(h ^ (h >>> 13), 3266489909);
      h >>>= 0;
    }
    return h >>> 0;
  }

  function initials(first, last) {
    const a = (first && first[0]) ? first[0].toUpperCase() : "?";
    const b = (last && last[0]) ? last[0].toUpperCase() : "?";
    return a + b;
  }

  function hueFor(seed, seat, difficulty) {
    const band = HUE_BAND[difficulty] || HUE_BAND.analyst;
    const span = band[1] - band[0] + 1;
    const offset = hashMix(seed, seat, difficulty, "hue") % span;
    return band[0] + offset;
  }

  function shapeFor(seed, seat, difficulty) {
    return hashMix(seed, seat, difficulty, "shape") % 3;
  }

  function pickFromPool(pool, seed, ...keys) {
    if (!pool || !pool.length) return "";
    const idx = hashMix(seed, ...keys) % pool.length;
    return pool[idx];
  }

  function buildOneIdentity(seed, seat, difficulty, usedNames) {
    const norm = normalizeDifficulty(difficulty);
    const pool = NAME_POOL[norm] || NAME_POOL.analyst;
    const rank = RANK[norm] || RANK.analyst;
    let idx = hashMix(seed, seat, norm, "name") % pool.length;
    let guard = 0;
    while (guard < pool.length) {
      const entry = pool[idx];
      const displayName = `${entry.first} ${entry.last}`;
      if (!usedNames.has(displayName)) {
        usedNames.add(displayName);
        return {
          seat,
          difficulty: norm,
          first: entry.first,
          last: entry.last,
          displayName,
          initials: initials(entry.first, entry.last),
          rankCn: rank.cn,
          rankEn: rank.en,
          hue: hueFor(seed, seat, norm),
          shape: shapeFor(seed, seat, norm),
        };
      }
      idx = (idx + 1) % pool.length;
      guard++;
    }
    const fallback = pool[0];
    const displayName = `${fallback.first} ${fallback.last}`;
    return {
      seat,
      difficulty: norm,
      first: fallback.first,
      last: fallback.last,
      displayName,
      initials: initials(fallback.first, fallback.last),
      rankCn: rank.cn,
      rankEn: rank.en,
      hue: hueFor(seed, seat, norm),
      shape: shapeFor(seed, seat, norm),
    };
  }

  function buildForMatch(match) {
    const seed = (match && match.match_seed != null) ? match.match_seed : 1;
    const used = new Set();
    const out = {};
    for (const seat of [1, 2]) {
      const id = `robot_${seat}`;
      const p = match && match.participants && match.participants[id];
      const diff = p ? p.difficulty : "analyst";
      out[id] = buildOneIdentity(seed, seat, diff, used);
    }
    return out;
  }

  function dialoguePool(difficulty, kind) {
    const norm = normalizeDifficulty(difficulty);
    const tier = DIALOGUE[norm] || DIALOGUE.analyst;
    return (tier && tier[kind]) ? tier[kind] : [];
  }

  function pickShowdownLine(identity, seed, round) {
    if (!identity) return "";
    const pool = dialoguePool(identity.difficulty, "showdown");
    return pickFromPool(pool, seed, round, identity.seat, "showdown");
  }

  function pickRoundResultLine(identity, seed, round, outcome) {
    if (!identity) return "";
    const kind = outcome === "win" ? "round_win" : (outcome === "loss" ? "round_loss" : "");
    if (!kind) return "";
    const pool = dialoguePool(identity.difficulty, kind);
    return pickFromPool(pool, seed, round, identity.seat, kind);
  }

  // V5.10.3 final committee verdict line. `outcome` is "player" / "draw" / "banker".
  // Deterministic from (match_seed, outcome, winner identity). For a banker win the
  // winning banker's identity selects from its finite final_winner pool; a player
  // win / draw uses the room-verdict pool. No RNG, no fetch, no LLM.
  function pickFinalLine(outcome, identity, seed) {
    if (outcome === "player") {
      return pickFromPool(ROOM_VERDICT.player, seed, "final", "player");
    }
    if (outcome === "draw") {
      return pickFromPool(ROOM_VERDICT.draw, seed, "final", "draw");
    }
    if (!identity) return "";
    const pool = dialoguePool(identity.difficulty, "final_winner");
    return pickFromPool(pool, seed, "final", identity.seat, identity.difficulty);
  }

  // Inline SVG monogram sigil — geometric only, no external assets.
  function makeSigilNode(identity, size) {
    const wrap = document.createElement("span");
    wrap.className = "oi-sigil";
    if (!identity) return wrap;
    const hue = identity.hue || 210;
    const sz = size || 34;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", String(sz));
    svg.setAttribute("height", String(sz));
    svg.setAttribute("viewBox", "0 0 48 48");
    svg.setAttribute("aria-hidden", "true");
    const defs = document.createElementNS(ns, "defs");
    const grad = document.createElementNS(ns, "radialGradient");
    const gid = `oi-g-${hue}-${identity.initials}-${identity.shape}-${sz}`;
    grad.setAttribute("id", gid);
    grad.setAttribute("cx", "38%");
    grad.setAttribute("cy", "30%");
    const s1 = document.createElementNS(ns, "stop");
    s1.setAttribute("offset", "0%");
    s1.setAttribute("stop-color", `hsl(${hue},55%,42%)`);
    const s2 = document.createElementNS(ns, "stop");
    s2.setAttribute("offset", "100%");
    s2.setAttribute("stop-color", `hsl(${hue},45%,18%)`);
    grad.appendChild(s1);
    grad.appendChild(s2);
    defs.appendChild(grad);
    svg.appendChild(defs);

    const rc = rankColor(identity.difficulty);
    const stroke = rc.color;
    const fill = `url(#${gid})`;
    const shape = identity.shape || 0;
    if (shape === 1) {
      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", "4");
      rect.setAttribute("y", "4");
      rect.setAttribute("width", "40");
      rect.setAttribute("height", "40");
      rect.setAttribute("rx", "10");
      rect.setAttribute("fill", fill);
      rect.setAttribute("stroke", stroke);
      rect.setAttribute("stroke-width", "1.5");
      svg.appendChild(rect);
    } else if (shape === 2) {
      const poly = document.createElementNS(ns, "polygon");
      poly.setAttribute("points", "24,3 44,14 44,34 24,45 4,34 4,14");
      poly.setAttribute("fill", fill);
      poly.setAttribute("stroke", stroke);
      poly.setAttribute("stroke-width", "1.5");
      svg.appendChild(poly);
    } else {
      const circle = document.createElementNS(ns, "circle");
      circle.setAttribute("cx", "24");
      circle.setAttribute("cy", "24");
      circle.setAttribute("r", "22");
      circle.setAttribute("fill", fill);
      circle.setAttribute("stroke", stroke);
      circle.setAttribute("stroke-width", "1.5");
      svg.appendChild(circle);
    }

    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", "24");
    text.setAttribute("y", "31");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("font-size", "16");
    text.setAttribute("font-weight", "800");
    text.setAttribute("fill", `hsla(${hue},70%,88%,0.95)`);
    text.setAttribute("font-family", "sans-serif");
    text.textContent = identity.initials || "??";
    svg.appendChild(text);
    wrap.appendChild(svg);
    return wrap;
  }

  window.OpponentIdentity = {
    RANK,
    RANK_COLOR,
    NAME_POOL,
    DIALOGUE,
    ROOM_VERDICT,
    normalizeDifficulty,
    rankClass,
    rankColor,
    hashMix,
    initials,
    buildForMatch,
    pickShowdownLine,
    pickRoundResultLine,
    pickFinalLine,
    makeSigilNode,
  };
})();
