// Shared thesis helpers for Modeling Studio pages.
(function () {
  "use strict";

  const API = "http://127.0.0.1:5000";
  const SCENARIO_STATE_VALUES = ["stronger", "stable", "weaker", "unknown"];
  const SCENARIOS = ["base", "bull", "bear"];

  // v3.4.0: hardcoded negative-polarity drivers.
  // Future: when ontology gains a polarity field, delete this constant
  // and read drivers.json[driverId].polarity instead.
  const NEGATIVE_POLARITY_DRIVERS = ["gross_churn", "regulatory_headwind"];

  function canonicalTicker(t) {
    return (t || "").trim().toUpperCase();
  }

  function getTickerFromURL() {
    const params = new URLSearchParams(window.location.search);
    return canonicalTicker(params.get("symbol"));
  }

  async function fetchOntology() {
    const res = await fetch(`${API}/api/ontology/drivers`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    return await res.json();
  }

  async function fetchThesis(canonical) {
    const res = await fetch(`${API}/api/thesis/${encodeURIComponent(canonical)}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    return await res.json();
  }

  async function saveThesis(canonical, payload) {
    const res = await fetch(`${API}/api/thesis/${encodeURIComponent(canonical)}`, {
      method : "PUT",
      headers: { "Content-Type": "application/json" },
      body   : JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data && data.error ? data.error : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function getDriverInterpretation(driverId, thesis, ontology) {
    const overrides = thesis && thesis.driver_interpretations
      ? thesis.driver_interpretations
      : {};
    const override = overrides[driverId];
    if (typeof override === "string" && override.trim() !== "") {
      return { text: override, isOverride: true };
    }

    const meta = ontology && ontology[driverId] ? ontology[driverId] : {};
    return {
      text: meta.interpretation_zh || "",
      isOverride: false,
    };
  }

  function getDefaultScenarioState(driverId) {
    if (NEGATIVE_POLARITY_DRIVERS.includes(driverId)) {
      return { base: "stable", bull: "weaker", bear: "stronger" };
    }
    return { base: "stable", bull: "stronger", bear: "weaker" };
  }

  function getScenarioState(driverId, scenario, thesis) {
    const overrides = thesis && thesis.scenario_states && thesis.scenario_states[scenario]
      ? thesis.scenario_states[scenario]
      : {};
    const override = overrides[driverId];
    if (SCENARIO_STATE_VALUES.includes(override)) {
      return { state: override, isOverride: true };
    }

    const defaults = getDefaultScenarioState(driverId);
    return { state: defaults[scenario], isOverride: false };
  }

  function getScenarioBadge(currentValue, driverId, scenario) {
    if (currentValue === "unknown") {
      return "unknown";
    }
    const defaultValue = getDefaultScenarioState(driverId)[scenario];
    if (currentValue === defaultValue) {
      return "default";
    }
    return "user_modified";
  }

  function buildScenarioStatesPayload(currentState, driversSelected) {
    const payload = { base: {}, bull: {}, bear: {} };
    const selected = Array.isArray(driversSelected) ? driversSelected : [];
    const state = currentState && typeof currentState === "object" ? currentState : {};

    SCENARIOS.forEach(scenario => {
      selected.forEach(driverId => {
        const scenarioState = state[scenario] || {};
        const currentValue = scenarioState[driverId];
        if (!SCENARIO_STATE_VALUES.includes(currentValue)) return;

        if (currentValue === "unknown") {
          payload[scenario][driverId] = "unknown";
          return;
        }

        const defaultValue = getDefaultScenarioState(driverId)[scenario];
        if (currentValue === defaultValue) return;
        payload[scenario][driverId] = currentValue;
      });
    });

    return payload;
  }

  window.ThesisShared = {
    AFFECTS_LABELS: {
      revenue_growth     : "收入增长",
      margin             : "利润率",
      capex              : "资本支出",
      working_capital    : "营运资本",
      terminal_confidence: "长期确定性",
      risk_discount      : "风险溢价",
    },
    FRAMEWORK_ORDER: [
      "Consumer", "SaaS", "Semis", "Platform",
      "Margin", "Industrial", "Competitive", "External",
    ],
    getTickerFromURL,
    canonicalTicker,
    fetchOntology,
    fetchThesis,
    saveThesis,
    getDriverInterpretation,
    SCENARIO_STATE_VALUES,
    NEGATIVE_POLARITY_DRIVERS,
    getDefaultScenarioState,
    getScenarioState,
    getScenarioBadge,
    buildScenarioStatesPayload,
  };
})();
