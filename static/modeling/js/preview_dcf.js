// v3.4.4: DCF Preview delta mapping (locked by G/Jerry).
// All values are RELATIVE deltas applied to base DCF assumptions.
// "pp" = absolute percentage points (added/subtracted).
// "%" = relative percent (multiplied as 1 + pct).
//
// Direction sign: 上行 = positive delta to corresponding DCF input.
// risk_discount 上行 = wacc 上行 (折现率更高 → 估值下行, 这是数学结果, 不是好坏判断).
// capex 上行 = capex 数值变大 → FCF 变小 → 估值下行. 这是 dcf_calculator 公式语义.
// wc_change 上行 = 营运资本占用上升 → FCF 变小. 同上.
//
// terminal_confidence 的 delta 视 tv_method 而定:
//   - gordon → 只施加 terminal_g delta
//   - exit   → 只施加 exit_multiple delta
//   - average → 两者都施加
const DIMENSION_TIER_DELTA = {
  revenue_growth: {
    // 施加到 fcf_growth, 单位 pp
    target: "fcf_growth",
    unit: "pp",
    values: { 轻微: 0.005, 温和: 0.010, 中等: 0.015, 显著: 0.020 }
  },
  margin: {
    // 施加到 ebit (proxy), 单位 relative %
    target: "ebit",
    unit: "pct",
    values: { 轻微: 0.010, 温和: 0.025, 中等: 0.050, 显著: 0.075 }
  },
  capex: {
    target: "capex",
    unit: "pct",
    values: { 轻微: 0.025, 温和: 0.050, 中等: 0.100, 显著: 0.150 }
  },
  working_capital: {
    target: "wc_change",
    unit: "pct",
    values: { 轻微: 0.025, 温和: 0.050, 中等: 0.100, 显著: 0.150 }
  },
  terminal_confidence: {
    // 双 target 视 tv_method 而定
    target_gordon: "terminal_g",
    target_exit: "exit_multiple",
    unit_gordon: "pp",
    unit_exit: "pct",
    values_gordon: { 轻微: 0.001, 温和: 0.002, 中等: 0.0035, 显著: 0.005 },
    values_exit:   { 轻微: 0.010, 温和: 0.025, 中等: 0.050, 显著: 0.075 }
  },
  risk_discount: {
    target: "wacc",
    unit: "pp",
    values: { 轻微: 0.001, 温和: 0.0025, 中等: 0.005, 显著: 0.0075 }
  }
};

(function () {
  "use strict";

  const API = "http://127.0.0.1:5000";
  const DIMENSION_LABELS = {
    revenue_growth: "收入增长",
    margin: "利润率",
    capex: "资本支出",
    working_capital: "营运资本",
    terminal_confidence: "长期确定性",
    risk_discount: "风险溢价",
  };
  const TARGET_LABELS = {
    ebit: "EBIT proxy",
  };
  const TIER_THRESHOLDS = [
    { min: 1, max: 1, label: "轻微" },
    { min: 2, max: 2, label: "温和" },
    { min: 3, max: 3, label: "中等" },
    { min: 4, max: Infinity, label: "显著" },
  ];

  function getMagnitudeTier(upCount, downCount) {
    if (upCount > 0 && downCount > 0) {
      return { kind: "conflict" };
    }
    if (upCount === 0 && downCount === 0) {
      return { kind: "none" };
    }
    const direction = upCount > 0 ? "up" : "down";
    const count = upCount > 0 ? upCount : downCount;
    const tier = TIER_THRESHOLDS.find(t => count >= t.min && count <= t.max);
    return { kind: "tier", direction, count, label: tier.label };
  }

  function applyDelta(overrides, target, unit, deltaValue, baseParams) {
    if (unit === "pp") {
      overrides[target] = (overrides[target] ?? baseParams[target]) + deltaValue;
    } else if (unit === "pct") {
      const baseVal = baseParams[target];
      overrides[target] = (overrides[target] ?? baseVal) * (1 + deltaValue);
    }
    if (typeof overrides[target] === "number" && overrides[target] < 0) {
      throw new Error(`Preview override for ${target} became negative`);
    }
  }

  function buildScenarioOverrides(baseParams, scenario) {
    const bridgeView = window.__bridgeView || {};
    const overrides = {};
    const appliedList = [];

    Object.keys(bridgeView).forEach(dim => {
      const scenarioData = bridgeView[dim] && bridgeView[dim][scenario];
      const cfg = DIMENSION_TIER_DELTA[dim];
      if (!scenarioData || !cfg) return;

      const tier = getMagnitudeTier(
        (scenarioData.up || []).length,
        (scenarioData.down || []).length
      );
      if (tier.kind !== "tier") return;

      const sign = tier.direction === "up" ? 1 : -1;
      if (dim === "terminal_confidence") {
        applyTerminalConfidenceDelta(overrides, baseParams, tier, sign, appliedList);
        return;
      }

      const deltaValue = sign * cfg.values[tier.label];
      applyDelta(overrides, cfg.target, cfg.unit, deltaValue, baseParams);
      appliedList.push(_formatAppliedItem(dim, tier.direction, tier.label, cfg.target, cfg.unit, deltaValue));
    });

    return { overrides, appliedList };
  }

  function applyTerminalConfidenceDelta(overrides, baseParams, tier, sign, appliedList) {
    const cfg = DIMENSION_TIER_DELTA.terminal_confidence;
    const tvMethod = baseParams.tv_method;

    if (tvMethod === "gordon" || tvMethod === "average") {
      const deltaValue = sign * cfg.values_gordon[tier.label];
      applyDelta(overrides, cfg.target_gordon, cfg.unit_gordon, deltaValue, baseParams);
      appliedList.push(_formatAppliedItem("terminal_confidence", tier.direction, tier.label, cfg.target_gordon, cfg.unit_gordon, deltaValue));
    }
    if (tvMethod === "exit" || tvMethod === "average") {
      const deltaValue = sign * cfg.values_exit[tier.label];
      applyDelta(overrides, cfg.target_exit, cfg.unit_exit, deltaValue, baseParams);
      appliedList.push(_formatAppliedItem("terminal_confidence", tier.direction, tier.label, cfg.target_exit, cfg.unit_exit, deltaValue));
    }
  }

  function _formatAppliedItem(dimension, direction, tier, target, unit, deltaValue) {
    return {
      dimension,
      dimensionLabel: DIMENSION_LABELS[dimension] || dimension,
      direction,
      directionLabel: direction === "up" ? "上行" : "下行",
      tier,
      target,
      targetLabel: TARGET_LABELS[target] || target,
      unit,
      deltaValue,
      delta: _formatDelta(deltaValue, unit),
    };
  }

  function _formatDelta(value, unit) {
    const sign = value >= 0 ? "+" : "";
    if (unit === "pp") {
      return `${sign}${(value * 100).toFixed(1)}pp`;
    }
    return `${sign}${(value * 100).toFixed(1)}%`;
  }

  async function fetchPreview(symbol) {
    const defaultsRes = await fetch(`${API}/api/modeling/dcf?symbol=${encodeURIComponent(symbol)}`);
    const defaultsData = await defaultsRes.json();
    if (!defaultsRes.ok || defaultsData.error) throw new Error(defaultsData.error || `HTTP ${defaultsRes.status}`);
    const baseParams = defaultsData.defaults;

    const baseResult = await _postDCF(API, baseParams);
    const bullBuild = buildScenarioOverrides(baseParams, "bull");
    const bearBuild = buildScenarioOverrides(baseParams, "bear");

    const bullParams = { ...baseParams, ...bullBuild.overrides };
    const bearParams = { ...baseParams, ...bearBuild.overrides };

    const [bullResult, bearResult] = await Promise.all([
      _postDCF(API, bullParams),
      _postDCF(API, bearParams),
    ]);

    return {
      base: { params: baseParams, result: baseResult },
      bull: { params: bullParams, result: bullResult, applied: bullBuild.appliedList },
      bear: { params: bearParams, result: bearResult, applied: bearBuild.appliedList },
    };
  }

  async function _postDCF(API, params) {
    const res = await fetch(`${API}/api/modeling/dcf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  window.DIMENSION_TIER_DELTA = DIMENSION_TIER_DELTA;
  window.buildScenarioOverrides = buildScenarioOverrides;
  window.fetchPreview = fetchPreview;
})();
