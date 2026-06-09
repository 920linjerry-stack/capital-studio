// case.js - Investment Case workspace thesis editor.
(function () {
  "use strict";

  const Shared = window.ThesisShared;
  const API = "http://127.0.0.1:5000";
  const MODEL_LINES = {
    revenue_growth     : ["Revenue Growth", "Volume", "ASP", "FCF Growth"],
    margin             : ["Gross Margin", "EBIT Margin", "FCF Conversion"],
    capex              : ["CapEx Intensity", "Reinvestment Need"],
    working_capital    : ["Working Capital Change", "Cash Conversion"],
    terminal_confidence: ["Terminal Growth", "Exit Multiple Confidence"],
    risk_discount      : ["W\u0041CC", "Risk Premium", "Discount Rate"],
  };

  const DIMENSION_EN_LABELS = {
    revenue_growth     : "Revenue Growth",
    margin             : "Margin",
    capex              : "CapEx",
    working_capital    : "Working Capital",
    terminal_confidence: "Terminal Confidence",
    risk_discount      : "Risk Discount",
  };
  // v3.4.3: magnitude tier reflects source density, NOT financial impact magnitude.
  // Tier count = number of drivers in the single-direction confirmed bucket.
  // stable (持平) drivers do NOT count toward tier.
  // unknown drivers do NOT count toward tier (但 UI 单独提示).
  const MAGNITUDE_TIER_THRESHOLDS = [
    { min: 1, max: 1, label: "轻微" },
    { min: 2, max: 2, label: "温和" },
    { min: 3, max: 3, label: "中等" },
    { min: 4, max: Infinity, label: "显著" }
  ];

  let _ticker = "";
  let _ontology = null;
  let _thesis = null;
  let _saveStatusTimer = null;
  let _overrideState = {};
  let _scenarioState = { base: {}, bull: {}, bear: {} };
  let _isAssumptionBridgeExpanded = false;
  const _openInterpretationEditors = new Set();
  const _expandedFrameworks = new Set();

  function $(id) {
    return document.getElementById(id);
  }

  function _normalizeThesis(raw) {
    const thesis = raw && typeof raw === "object" ? raw : {};
    return {
      ticker          : thesis.ticker || _ticker,
      company_name    : typeof thesis.company_name === "string" ? thesis.company_name : _ticker,
      core_thesis     : typeof thesis.core_thesis === "string" ? thesis.core_thesis : "",
      key_risks       : typeof thesis.key_risks === "string" ? thesis.key_risks : "",
      thesis_notes    : typeof thesis.thesis_notes === "string" ? thesis.thesis_notes : "",
      drivers_selected: Array.isArray(thesis.drivers_selected) ? thesis.drivers_selected.slice() : [],
      driver_interpretations:
        thesis.driver_interpretations && typeof thesis.driver_interpretations === "object" && !Array.isArray(thesis.driver_interpretations)
          ? { ...thesis.driver_interpretations }
          : {},
      scenario_states : _normalizeScenarioStates(thesis.scenario_states),
      schema_version  : thesis.schema_version || "v340",
      last_modified   : thesis.last_modified || null,
    };
  }

  function _normalizeScenarioStates(raw) {
    const normalized = { base: {}, bull: {}, bear: {} };
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return normalized;

    ["base", "bull", "bear"].forEach(scenario => {
      const values = raw[scenario];
      if (values && typeof values === "object" && !Array.isArray(values)) {
        normalized[scenario] = { ...values };
      }
    });
    return normalized;
  }

  function _getSelectedDrivers() {
    return (_thesis && Array.isArray(_thesis.drivers_selected))
      ? _thesis.drivers_selected
      : [];
  }

  function _setSelectedDrivers(ids) {
    if (!_thesis) _thesis = _normalizeThesis(null);
    const seen = new Set();
    _thesis.drivers_selected = ids.filter(id => {
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }

  function _setDriverSelected(driverId, checked) {
    const ids = _getSelectedDrivers().slice();
    const exists = ids.includes(driverId);

    if (checked && !exists) {
      ids.push(driverId);
    } else if (!checked && exists) {
      const idx = ids.indexOf(driverId);
      ids.splice(idx, 1);
    }

    _setSelectedDrivers(ids);
    _renderThesisDynamicBlocks();
    _renderImpactMap();
    _renderAssumptionBridge();
    _updatePreviewBtnState();
  }

  function _setSaveStatus(text, cls) {
    const el = $("thesis-save-status");
    if (!el) return;
    el.textContent = text || "";
    el.className = "thesis-save-status" + (cls ? " " + cls : "");
  }

  function _formatLastModified(iso) {
    if (!iso) return "未保存";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "未保存";
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      const hh = String(d.getHours()).padStart(2, "0");
      const mi = String(d.getMinutes()).padStart(2, "0");
      return `已保存 ${yyyy}-${mm}-${dd} ${hh}:${mi}`;
    } catch (e) {
      return "未保存";
    }
  }

  async function _loadOntology() {
    try {
      _ontology = await Shared.fetchOntology();
      window.ONTOLOGY_DRIVERS = _ontology;
      if (typeof window._v342SanityCheck === "function") {
        window._v342SanityCheck();
      }
    } catch (err) {
      console.warn("[case] ontology load failed:", err);
      _ontology = null;
      const selectedEl = $("thesis-selected-drivers");
      const groupsEl = $("thesis-drivers-groups");
      if (selectedEl) selectedEl.innerHTML = "";
      if (groupsEl) {
        groupsEl.innerHTML =
          '<div style="color:var(--text-muted);font-size:12px;padding:6px 0;">驱动因素加载失败</div>';
      }
    }
  }

  async function _loadThesis() {
    if (!_ticker) {
      _thesis = null;
      return;
    }

    try {
      _thesis = _normalizeThesis(await Shared.fetchThesis(_ticker));
      _syncOverrideStateFromThesis();
      _syncScenarioOverrideStateFromThesis();
    } catch (err) {
      console.warn("[case] thesis load failed:", err);
      _thesis = _normalizeThesis(null);
      _syncOverrideStateFromThesis();
      _syncScenarioOverrideStateFromThesis();
    }
  }

  function _renderHeaderAndNotes() {
    const tEl = $("thesis-ticker");
    if (tEl) tEl.textContent = _ticker || "--";

    const tmEl = $("thesis-last-modified");
    if (tmEl) tmEl.textContent = _formatLastModified(_thesis ? _thesis.last_modified : null);

    const notesEl = $("thesis-notes");
    if (notesEl) notesEl.value = _thesis ? _thesis.thesis_notes : "";

    const coreEl = $("core-thesis");
    if (coreEl) coreEl.value = _thesis ? _thesis.core_thesis : "";

    const risksEl = $("key-risks");
    if (risksEl) risksEl.value = _thesis ? _thesis.key_risks : "";
  }

  function _renderThesisDynamicBlocks() {
    _renderSelectedDrivers();
    _renderDriverGroups();
    _renderFeedback();
    _renderScenarioState();
  }

  function _renderSelectedDrivers() {
    const selectedEl = $("thesis-selected-drivers");
    const countEl = $("thesis-selected-count");
    if (!selectedEl) return;

    const selectedIds = _getSelectedDrivers();
    if (countEl) countEl.textContent = String(selectedIds.length);

    if (!_ontology) {
      selectedEl.innerHTML = "";
      return;
    }

    if (selectedIds.length === 0) {
      selectedEl.innerHTML =
        '<div class="thesis-selected-empty">还没选择 driver,展开下方分类开始选择。</div>';
      return;
    }

    selectedEl.innerHTML = selectedIds
      .map(id => _renderDriverItem(id, _ontology[id], true, true))
      .join("");
  }

  function _renderDriverGroups() {
    const groupsEl = $("thesis-drivers-groups");
    if (!groupsEl || !_ontology) return;

    const selectedSet = new Set(_getSelectedDrivers());
    const byFramework = _groupDriversByFramework();

    groupsEl.innerHTML = _getOrderedFrameworks(byFramework).map(fw => {
      const items = byFramework[fw] || [];
      const selectedCount = items.filter(d => selectedSet.has(d.id)).length;
      const isExpanded = _expandedFrameworks.has(fw);
      const collapsedClass = isExpanded ? "" : " collapsed";
      const toggleText = isExpanded ? "收起" : "展开";
      const itemsHtml = items
        .map(d => _renderDriverItem(d.id, d, selectedSet.has(d.id), false))
        .join("");

      return `
        <div class="thesis-framework-group${collapsedClass}" data-framework="${_escapeAttr(fw)}">
          <div class="thesis-framework-header" data-framework-toggle="${_escapeAttr(fw)}">
            <span>
              <span>${_escapeHtml(fw)}</span>
              <span class="thesis-framework-counts">(${selectedCount}/${items.length})</span>
            </span>
            <span>
              <span class="thesis-framework-toggle">${toggleText}</span>
              <span class="caret">▼</span>
            </span>
          </div>
          <div class="thesis-framework-body">
            ${itemsHtml}
          </div>
        </div>`;
    }).join("");
  }

  function _renderFeedback() {
    const feedbackEl = $("thesis-feedback");
    if (!feedbackEl) return;

    const selectedIds = _getSelectedDrivers();
    if (!_ontology || selectedIds.length === 0) {
      feedbackEl.style.display = "none";
      feedbackEl.innerHTML = "";
      return;
    }

    const itemsHtml = selectedIds.map(id => {
      const meta = _ontology[id] || {};
      const affects = Array.isArray(meta.affects) ? meta.affects : [];
      const affectsText = Array.from(new Set(affects))
        .map(key => Shared.AFFECTS_LABELS[key] || key)
        .filter(Boolean)
        .join("、") || "未标注";

      return `
        <div class="thesis-feedback-item">
          <span class="thesis-feedback-driver">${_escapeHtml(_formatDriverName(meta, id))}</span>
          <span class="thesis-feedback-arrow">→</span>
          <span>可能影响:${_escapeHtml(affectsText)}</span>
        </div>`;
    }).join("");

    feedbackEl.innerHTML = `
      <div class="thesis-feedback-title">结构反馈:你选择的 drivers 可能影响以下 DCF 维度。</div>
      ${itemsHtml}
      <div class="thesis-feedback-title" style="margin-top:4px;">这是结构反馈,不会自动修改 DCF assumptions。</div>`;
    feedbackEl.style.display = "block";
  }

  function _applyMode() {
    const main = $("case-main");
    if (!main) return;

    main.classList.add("is-analysis");

    const map = $("impact-map");
    if (map) map.setAttribute("aria-hidden", "false");

    _renderImpactMap();
  }

  function _renderImpactMap() {
    const concentrationEl = $("impact-concentration");
    const dimensionsEl = $("impact-dimensions");
    if (!concentrationEl || !dimensionsEl) return;

    const dimensionEntries = _getImpactDimensions();
    if (dimensionEntries.length === 0) {
      concentrationEl.innerHTML = "";
      dimensionsEl.innerHTML = "";
      return;
    }

    concentrationEl.innerHTML = `
      <div class="impact-concentration-title">当前 thesis 主要集中在</div>
      ${dimensionEntries.map(entry => `
        <div class="impact-concentration-item">
          <span>${_escapeHtml(Shared.AFFECTS_LABELS[entry.key] || entry.key)}</span>
          <span class="impact-concentration-count">${entry.drivers.length}</span>
        </div>`).join("")}`;

    dimensionsEl.innerHTML = dimensionEntries.map(entry => {
      const zh = Shared.AFFECTS_LABELS[entry.key] || entry.key;
      const en = DIMENSION_EN_LABELS[entry.key] || entry.key;
      const lines = MODEL_LINES[entry.key] || [];

      return `
        <div class="impact-dim-card">
          <div class="impact-dim-name">
            ${_escapeHtml(zh)}
            <span class="impact-dim-name-en">(${_escapeHtml(en)})</span>
          </div>
          <div class="impact-dim-section-label">来源 drivers</div>
          ${entry.drivers.map(driver => `
            <div class="impact-dim-source">
              ${_escapeHtml(driver.zh)}
              <span class="impact-dim-source-en">(${_escapeHtml(driver.en)})</span>
            </div>`).join("")}
          <div class="impact-dim-section-label">可能关联模型行</div>
          ${lines.map(line => `
            <div class="impact-dim-line">${_escapeHtml(line)}</div>`).join("")}
        </div>`;
    }).join("");
  }

  function _renderScenarioState() {
    const bodyEl = $("scenario-state-body");
    if (!bodyEl) return;

    const selectedIds = _getSelectedDrivers();
    if (selectedIds.length === 0) {
      bodyEl.innerHTML =
        '<div class="scenario-state-empty">勾选 drivers 后会自动生成情景判断草稿</div>';
      return;
    }

    const scenarioLabels = { base: "Base", bull: "Bull", bear: "Bear" };
    const rowsHtml = selectedIds.map(driverId => {
      const meta = _ontology && _ontology[driverId] ? _ontology[driverId] : {};
      return `
        <tr>
          <td class="scenario-state-driver">${_escapeHtml(meta.display_name_zh || meta.display_name || driverId)}</td>
          ${["base", "bull", "bear"].map(scenario => _renderScenarioStateCell(driverId, scenario)).join("")}
        </tr>`;
    }).join("");

    bodyEl.innerHTML = `
      <table class="scenario-state-table">
        <colgroup>
          <col style="width:34%;">
          <col style="width:22%;">
          <col style="width:22%;">
          <col style="width:22%;">
        </colgroup>
        <thead>
          <tr>
            <th>Driver</th>
            ${["base", "bull", "bear"].map(scenario => `<th>${_renderScenarioHeading(scenarioLabels[scenario], scenario)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>`;
  }

  function getMagnitudeTier(upCount, downCount) {
    if (upCount > 0 && downCount > 0) {
      return { kind: "conflict" };
    }
    if (upCount === 0 && downCount === 0) {
      return { kind: "none" };
    }
    const direction = upCount > 0 ? "up" : "down";
    const count = upCount > 0 ? upCount : downCount;
    const tier = MAGNITUDE_TIER_THRESHOLDS.find(t => count >= t.min && count <= t.max);
    return { kind: "tier", direction, count, label: tier.label };
  }

  function _renderAssumptionBridge() {
    const container = $("assumption-bridge-content");
    if (!container) return;

    const selected = _getSelectedDrivers();
    if (selected.length === 0) {
      window.__bridgeView = {};
      container.innerHTML = '<p class="assumption-bridge-empty">勾选 drivers 后会生成假设桥接草稿</p>';
      return;
    }

    const effectsMap = window.DRIVER_ASSUMPTION_EFFECTS || {};
    const dimensionMeta = window.DIMENSION_META || {};
    const ontology = window.ONTOLOGY_DRIVERS || _ontology || {};
    const SCENARIOS = ["base", "bull", "bear"];
    const SCENARIO_LABELS = {
      base: "Base / 正常情况",
      bull: "Bull / 乐观情况",
      bear: "Bear / 悲观情况",
    };
    const BUCKETS = ["up", "flat", "down", "unknown"];
    const BUCKET_LABELS = {
      up: "上行来源",
      flat: "持平来源",
      down: "下行来源",
      unknown: "未判断来源",
    };

    const bridgeView = {};

    selected.forEach(driverId => {
      const effects = effectsMap[driverId] || {};
      const driverName = ontology[driverId]?.display_name_zh || driverId;

      Object.keys(effects).forEach(dim => {
        const effectSign = effects[dim] === "positive" ? +1 : -1;

        SCENARIOS.forEach(scenario => {
          const thesisForBridge = {
            ...(_thesis || {}),
            scenario_states: _scenarioState,
          };
          const stateResult = Shared.getScenarioState(driverId, scenario, thesisForBridge);
          const state = stateResult.state;

          let bucket;
          if (state === "unknown") {
            bucket = "unknown";
          } else {
            const stateSign = state === "stronger" ? +1 : state === "weaker" ? -1 : 0;
            // final_direction = effect_sign × state_sign
            const finalDirection = effectSign * stateSign;
            bucket = finalDirection > 0 ? "up" : finalDirection < 0 ? "down" : "flat";
          }

          if (!bridgeView[dim]) bridgeView[dim] = {};
          if (!bridgeView[dim][scenario]) {
            bridgeView[dim][scenario] = { up: [], flat: [], down: [], unknown: [] };
          }
          bridgeView[dim][scenario][bucket].push({ driverId, driverName });
        });
      });
    });
    window.__bridgeView = bridgeView;

    const orderedDims = [];
    const seenDims = new Set();
    selected.forEach(driverId => {
      const affects = ontology[driverId]?.affects || [];
      affects.forEach(dim => {
        if (!seenDims.has(dim) && bridgeView[dim]) {
          seenDims.add(dim);
          orderedDims.push(dim);
        }
      });
    });

    let html = "";
    orderedDims.forEach(dim => {
      const meta = dimensionMeta[dim];
      if (!meta) return;

      html += '<div class="bridge-dimension">';
      html += `<h4>${_escapeHtml(meta.display_name_cn)} <span class="bridge-dimension-en">${_escapeHtml(meta.display_name_en)}</span></h4>`;
      html += `<p class="bridge-dim-desc">${_escapeHtml(meta.neutral_description)}</p>`;

      SCENARIOS.forEach(scenario => {
        const scenarioData = bridgeView[dim][scenario];
        if (!scenarioData) return;
        html += '<div class="bridge-scenario">';
        html += `<div class="bridge-scenario-label">${_escapeHtml(SCENARIO_LABELS[scenario])}</div>`;
        html += _renderBridgeTierLine(scenario, scenarioData);

        const bucketsForScenario = scenario === "base" ? ["flat", "unknown"] : BUCKETS;
        bucketsForScenario.forEach(bucket => {
          const drivers = scenarioData[bucket];
          if (!drivers || drivers.length === 0) return;
          const names = drivers.map(d => d.driverName).join("、");
          html += `<div class="bridge-bucket">${_escapeHtml(BUCKET_LABELS[bucket])}：${_escapeHtml(names)}</div>`;
        });

        html += "</div>";
      });

      html += "</div>";
    });

    container.innerHTML = html;
  }

  function _renderBridgeTierLine(scenario, scenarioData) {
    const upCount = scenarioData.up.length;
    const downCount = scenarioData.down.length;
    const unknownNames = scenarioData.unknown.map(d => d.driverName).join("、");

    if (scenario === "base") {
      return '<div class="bridge-tier bridge-tier-muted">基准维持，未生成幅度等级</div>';
    }

    const tier = getMagnitudeTier(upCount, downCount);
    if (tier.kind === "conflict") {
      return '<div class="bridge-tier">方向分歧，暂不生成幅度等级</div>';
    }
    if (tier.kind === "tier") {
      const directionLabel = tier.direction === "up" ? "上行" : "下行";
      const unknownLine = unknownNames
        ? `<div class="bridge-tier bridge-tier-muted">另有未判断来源：${_escapeHtml(unknownNames)}</div>`
        : "";
      return `
        <div class="bridge-tier">${_escapeHtml(directionLabel)}</div>
        <div class="bridge-tier">幅度等级：${_escapeHtml(tier.label)}（${tier.count} 个来源）</div>
        ${unknownLine}`;
    }
    if (scenarioData.unknown.length > 0 && scenarioData.flat.length === 0) {
      return '<div class="bridge-tier bridge-tier-muted">未判断，暂不生成幅度等级</div>';
    }
    return '<div class="bridge-tier bridge-tier-muted">基准维持，未生成幅度等级</div>';
  }

  function _renderAssumptionBridgeToggle() {
    const toggle = $("assumption-bridge-toggle");
    const panel = $("assumption-bridge-collapsible");
    const status = $("assumption-bridge-toggle-status");
    if (!toggle || !panel) return;

    toggle.setAttribute("aria-expanded", _isAssumptionBridgeExpanded ? "true" : "false");
    panel.hidden = !_isAssumptionBridgeExpanded;
    if (status) status.textContent = _isAssumptionBridgeExpanded ? "收起" : "展开";
  }

  function _updatePreviewBtnState() {
    const btn = $("preview-dcf-btn");
    if (!btn) return;
    btn.disabled = _getSelectedDrivers().length === 0;
  }

  function _renderScenarioStateCell(driverId, scenario) {
    _ensureScenarioValue(driverId, scenario);
    const value = _scenarioState[scenario][driverId];
    const badgeState = Shared.getScenarioBadge(value, driverId, scenario);
    const badge = _renderScenarioBadge(badgeState);

    return `
      <td>
        <span class="scenario-state-cell">
          <select class="scenario-state-select"
                  data-scenario-state-driver="${_escapeAttr(driverId)}"
                  data-scenario-state-scenario="${_escapeAttr(scenario)}">
            ${Shared.SCENARIO_STATE_VALUES.map(value => `
              <option value="${_escapeAttr(value)}"${value === _scenarioState[scenario][driverId] ? " selected" : ""}>${_escapeHtml(_formatScenarioStateLabel(value))}</option>
            `).join("")}
          </select>
          ${badge}
        </span>
      </td>`;
  }

  function _renderScenarioHeading(en, scenario) {
    const zh = {
      base: "正常情况",
      bull: "乐观情况",
      bear: "悲观情况",
    }[scenario] || "";
    return `
      <span class="scenario-state-heading">
        <span>${_escapeHtml(en)}</span>
        <span>/</span>
        <span class="scenario-state-heading-zh">${_escapeHtml(zh)}</span>
      </span>`;
  }

  function _renderScenarioBadge(state) {
    const config = {
      default      : { text: "系统建议", className: "scenario-state-badge-default" },
      user_modified: { text: "你已修改", className: "scenario-state-badge-user-modified" },
      unknown      : { text: "先不判断", className: "scenario-state-badge-unknown" },
    }[state] || { text: "系统建议", className: "scenario-state-badge-default" };

    return `<span class="scenario-state-badge ${config.className}">${_escapeHtml(config.text)}</span>`;
  }

  function _getImpactDimensions() {
    if (!_ontology) return [];

    const dimensions = {};
    Object.keys(Shared.AFFECTS_LABELS).forEach(key => {
      dimensions[key] = [];
    });

    _getSelectedDrivers().forEach(id => {
      const meta = _ontology[id];
      if (!meta) return;

      const driver = {
        id,
        zh: meta.display_name_zh || meta.display_name || id,
        en: meta.display_name || id,
      };

      const affects = Array.isArray(meta.affects) ? Array.from(new Set(meta.affects)) : [];
      affects.forEach(key => {
        if (!dimensions[key]) dimensions[key] = [];
        dimensions[key].push(driver);
      });
    });

    const order = Object.keys(Shared.AFFECTS_LABELS);
    return order
      .map(key => ({ key, drivers: dimensions[key] || [] }))
      .filter(entry => entry.drivers.length > 0)
      .sort((a, b) => {
        const countDiff = b.drivers.length - a.drivers.length;
        if (countDiff !== 0) return countDiff;
        return order.indexOf(a.key) - order.indexOf(b.key);
      });
  }

  function _renderDriverItem(id, meta, checked, includeInterpretation) {
    const item = meta || {};
    const checkedAttr = checked ? "checked" : "";
    const selectedClass = checked ? " is-selected" : "";
    const zh = item.display_name_zh || item.display_name || id;
    const en = item.display_name || id;
    const desc = item.description_zh || item.description || "";

    const interpretationHtml = includeInterpretation
      ? _renderDriverInterpretation(id)
      : "";

    return `
      <label class="thesis-driver-item${selectedClass}">
        <input type="checkbox" data-driver-id="${_escapeAttr(id)}" ${checkedAttr} />
        <span>
          <span class="thesis-driver-name-zh">${_escapeHtml(zh)}</span>
          <span class="thesis-driver-name-en">(${_escapeHtml(en)})</span>
          <span class="thesis-driver-desc-zh">${_escapeHtml(desc)}</span>
        </span>
      </label>
      ${interpretationHtml}`;
  }

  function _renderDriverInterpretation(id) {
    if (!_ontology) return "";

    const thesisForDisplay = {
      ...(_thesis || {}),
      driver_interpretations: _overrideState,
    };
    const result = Shared.getDriverInterpretation(id, thesisForDisplay, _ontology);
    const isOpen = _openInterpretationEditors.has(id);
    const badge = Object.prototype.hasOwnProperty.call(_overrideState, id)
      ? '<span class="interpretation-edited-badge">已编辑</span>'
      : "";

    return `
      <div class="driver-interpretation" data-interpretation-driver-id="${_escapeAttr(id)}">
        <div class="interpretation-top-row">
          <div class="interpretation-text"${isOpen ? " hidden" : ""}>${_escapeHtml(result.text)}</div>
          ${badge}
        </div>
        <button type="button" class="interpretation-edit-btn" data-interpretation-edit="${_escapeAttr(id)}">
          ${isOpen ? "收起" : "编辑"}
        </button>
        <textarea class="interpretation-textarea" data-interpretation-textarea="${_escapeAttr(id)}"${isOpen ? "" : " hidden"}>${_escapeHtml(result.text)}</textarea>
      </div>`;
  }

  function _formatDriverName(meta, id) {
    const item = meta || {};
    const zh = item.display_name_zh || item.display_name || id;
    const en = item.display_name || id;
    return `${zh}(${en})`;
  }

  function _groupDriversByFramework() {
    const byFramework = {};
    Object.entries(_ontology || {}).forEach(([id, meta]) => {
      const fw = meta.framework || "Other";
      if (!byFramework[fw]) byFramework[fw] = [];
      byFramework[fw].push({ id, ...meta });
    });
    return byFramework;
  }

  function _getOrderedFrameworks(byFramework) {
    const ordered = Shared.FRAMEWORK_ORDER.filter(fw => byFramework[fw]);
    Object.keys(byFramework).forEach(fw => {
      if (!ordered.includes(fw)) ordered.push(fw);
    });
    return ordered;
  }

  function _bindEvents() {
    const selectedEl = $("thesis-selected-drivers");
    const groupsEl = $("thesis-drivers-groups");
    const scenarioEl = $("scenario-state-body");
    const bridgeToggle = $("assumption-bridge-toggle");
    const previewBtn = $("preview-dcf-btn");
    const previewOverlay = $("preview-overlay");
    const previewMask = previewOverlay ? previewOverlay.querySelector(".preview-mask") : null;
    const previewClose = previewOverlay ? previewOverlay.querySelector(".preview-close") : null;

    if (selectedEl) {
      selectedEl.addEventListener("change", _onDriverCheckboxChange);
      selectedEl.addEventListener("click", _onSelectedDriversClick);
      selectedEl.addEventListener("input", _onInterpretationInput);
    }
    if (groupsEl) {
      groupsEl.addEventListener("change", _onDriverCheckboxChange);
      groupsEl.addEventListener("click", _onFrameworkClick);
    }
    if (scenarioEl) {
      scenarioEl.addEventListener("change", _onScenarioStateChange);
    }
    if (bridgeToggle) {
      bridgeToggle.addEventListener("click", _onAssumptionBridgeToggle);
    }
    if (previewBtn) {
      previewBtn.addEventListener("click", _onPreviewClick);
    }
    if (previewMask) {
      previewMask.addEventListener("click", _closePreviewOverlay);
    }
    if (previewClose) {
      previewClose.addEventListener("click", _closePreviewOverlay);
    }
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") _closePreviewOverlay();
    });
  }

  function _onDriverCheckboxChange(event) {
    const box = event.target;
    if (!box || !box.matches("input[type='checkbox'][data-driver-id]")) return;
    _setDriverSelected(box.getAttribute("data-driver-id"), box.checked);
  }

  function _onFrameworkClick(event) {
    const header = event.target.closest("[data-framework-toggle]");
    if (!header) return;

    const fw = header.getAttribute("data-framework-toggle");
    if (_expandedFrameworks.has(fw)) {
      _expandedFrameworks.delete(fw);
    } else {
      _expandedFrameworks.add(fw);
    }
    _renderDriverGroups();
  }

  function _onSelectedDriversClick(event) {
    const button = event.target.closest("[data-interpretation-edit]");
    if (!button) return;

    const driverId = button.getAttribute("data-interpretation-edit");
    if (_openInterpretationEditors.has(driverId)) {
      _openInterpretationEditors.delete(driverId);
    } else {
      _openInterpretationEditors.add(driverId);
    }
    _renderSelectedDrivers();
  }

  function _onInterpretationInput(event) {
    const textarea = event.target;
    if (!textarea || !textarea.matches("[data-interpretation-textarea]")) return;

    const driverId = textarea.getAttribute("data-interpretation-textarea");
    const value = textarea.value;
    if (value.trim() === "") {
      delete _overrideState[driverId];
    } else {
      _overrideState[driverId] = value;
    }
  }

  function _onScenarioStateChange(event) {
    const select = event.target;
    if (!select || !select.matches("[data-scenario-state-driver][data-scenario-state-scenario]")) return;

    const driverId = select.getAttribute("data-scenario-state-driver");
    const scenario = select.getAttribute("data-scenario-state-scenario");
    const value = select.value;
    if (!driverId || !scenario || !Shared.SCENARIO_STATE_VALUES.includes(value)) return;

    if (!_scenarioState[scenario]) _scenarioState[scenario] = {};
    _scenarioState[scenario][driverId] = value;
    _renderScenarioState();
    _renderAssumptionBridge();
  }

  function _onAssumptionBridgeToggle() {
    _isAssumptionBridgeExpanded = !_isAssumptionBridgeExpanded;
    _renderAssumptionBridgeToggle();
  }

  async function _onPreviewClick() {
    const overlay = $("preview-overlay");
    const content = $("preview-content");
    const btn = $("preview-dcf-btn");
    if (!overlay || !content || !window.fetchPreview || !_ticker) return;

    overlay.style.display = "block";
    content.innerHTML = '<p class="preview-loading">正在计算 Preview...</p>';
    if (btn) btn.disabled = true;

    try {
      const data = await window.fetchPreview(_ticker);
      _renderPreviewContent(data);
    } catch (err) {
      content.innerHTML = `<p class="preview-error">Preview 计算失败：${_escapeHtml(err.message)}</p>`;
    } finally {
      _updatePreviewBtnState();
    }
  }

  function _renderPreviewContent(data) {
    const content = $("preview-content");
    if (!content) return;

    const base = data.base;
    const bull = data.bull;
    const bear = data.bear;
    const ccy = base.params.currency || "USD";
    const baseFV = Number(base.result.intrinsic_per_share || 0);
    const bullFV = Number(bull.result.intrinsic_per_share || 0);
    const bearFV = Number(bear.result.intrinsic_per_share || 0);
    const bullPct = baseFV ? ((bullFV - baseFV) / baseFV * 100) : 0;
    const bearPct = baseFV ? ((bearFV - baseFV) / baseFV * 100) : 0;

    content.innerHTML = `
      <h2 class="preview-title">预览估值影响 / Preview DCF Impact</h2>
      <p class="preview-note">这是临时预览，不会覆盖当前 DCF。</p>
      <div class="preview-scenarios">
        ${_renderPreviewScenario("当前 DCF Base", baseFV, ccy, null)}
        ${_renderPreviewScenario("Bull 情景预览", bullFV, ccy, bullPct, "bull")}
        ${_renderPreviewScenario("Bear 情景预览", bearFV, ccy, bearPct, "bear")}
      </div>
      <details class="preview-details">
        <summary>展开看应用了哪些 dimension delta</summary>
        ${_renderPreviewAppliedList("Bull 应用的 delta", bull.applied || [])}
        ${_renderPreviewAppliedList("Bear 应用的 delta", bear.applied || [])}
      </details>`;

    content.querySelectorAll("[data-save-type]").forEach(btn => {
      btn.addEventListener("click", () => {
        const scenarioType = btn.getAttribute("data-save-type");
        const scenarioData = scenarioType === "bull" ? bull : bear;
        _onSaveScenario(scenarioType, scenarioData);
      });
    });
  }

  function _renderPreviewScenario(label, value, ccy, pct, saveType) {
    const pctHtml = pct == null
      ? ""
      : `<div class="preview-vs-base ${pct >= 0 ? "up" : "down"}">(${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% vs Base)</div>`;
    const saveHtml = saveType
      ? `<button class="btn btn-primary" data-save-type="${_escapeAttr(saveType)}">保存为 ${saveType === "bull" ? "Bull" : "Bear"} 情景</button>
         <span class="save-status" data-status-type="${_escapeAttr(saveType)}"></span>`
      : "";
    return `
      <div class="preview-scenario-card">
        <div class="preview-scenario-label">${_escapeHtml(label)}</div>
        <div class="preview-fair-value">${_escapeHtml(ccy)} ${_formatNumber(value, 2)}</div>
        ${pctHtml}
        ${saveHtml}
      </div>`;
  }

  async function _onSaveScenario(scenarioType, scenarioData) {
    if (!scenarioData || !scenarioData.params || !scenarioData.result) return;

    const symbol = scenarioData.params.symbol;
    const statusEl = document.querySelector(`[data-status-type="${scenarioType}"]`);
    const btnEl = document.querySelector(`[data-save-type="${scenarioType}"]`);
    if (!symbol || !statusEl || !btnEl) return;

    btnEl.disabled = true;
    statusEl.textContent = "保存中...";

    const selectedDrivers = (_thesis && Array.isArray(_thesis.drivers_selected))
      ? _thesis.drivers_selected.slice()
      : _getSelectedDrivers().slice();
    const origin = {
      source: "preview_overlay",
      drivers_count: selectedDrivers.length,
      selected_driver_ids: selectedDrivers,
      thesis_last_modified: (_thesis && _thesis.last_modified) || null,
    };

    try {
      const res = await fetch(`${API}/api/modeling/dcf/scenario/${encodeURIComponent(symbol)}/${scenarioType}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          params: scenarioData.params,
          valuation: {
            intrinsic_per_share: scenarioData.result.intrinsic_per_share,
            currency: scenarioData.result.currency,
            ev: scenarioData.result.ev,
            equity_value: scenarioData.result.equity_value,
            tv_pct: scenarioData.result.tv_pct,
          },
          origin,
        }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);

      btnEl.textContent = "已保存（覆盖）";
      statusEl.textContent = "";
    } catch (err) {
      btnEl.disabled = false;
      statusEl.textContent = "保存失败：" + err.message;
    }
  }

  function _renderPreviewAppliedList(title, items) {
    if (!items.length) {
      return `
        <div class="preview-delta-title">${_escapeHtml(title)}</div>
        <div class="preview-delta-line">未应用 delta</div>`;
    }
    return `
      <div class="preview-delta-title">${_escapeHtml(title)}</div>
      ${items.map(item => `
        <div class="preview-delta-line">
          ${_escapeHtml(item.dimensionLabel || item.dimension)}
          ${_escapeHtml(item.tier)}
          ${_escapeHtml(item.directionLabel || item.direction)}
          → ${_escapeHtml(item.targetLabel || item.target)}
          ${_escapeHtml(item.delta)}
        </div>`).join("")}`;
  }

  function _closePreviewOverlay() {
    const overlay = $("preview-overlay");
    if (!overlay || overlay.style.display === "none") return;
    overlay.style.display = "none";
  }

  async function _saveThesis() {
    if (!_ticker) {
      _setSaveStatus("无法保存:缺少 ticker", "error");
      return;
    }

    const coreEl = $("core-thesis");
    const risksEl = $("key-risks");
    const notesEl = $("thesis-notes");
    const companyName =
      (_thesis && typeof _thesis.company_name === "string")
        ? _thesis.company_name
        : _ticker;

    _syncOpenOverrideTextareas();

    const payload = {
      ticker          : _ticker,
      company_name    : companyName,
      core_thesis     : coreEl ? coreEl.value : "",
      key_risks       : risksEl ? risksEl.value : "",
      thesis_notes    : notesEl ? notesEl.value : "",
      drivers_selected: _getSelectedDrivers().slice(),
      driver_interpretations: _getSelectedDriverInterpretationsPayload(),
      scenario_states : Shared.buildScenarioStatesPayload(_scenarioState, _getSelectedDrivers()),
      ["industry_" + "warning"]: null,
      schema_version  : "v340",
      last_modified   : null,
    };

    _setSaveStatus("保存中...", "");

    try {
      const data = await Shared.saveThesis(_ticker, payload);
      _thesis = _normalizeThesis(data);
      _syncOverrideStateFromThesis();
      _syncScenarioOverrideStateFromThesis();
      _openInterpretationEditors.clear();
      if (coreEl) _thesis.core_thesis = coreEl.value;
      if (risksEl) _thesis.key_risks = risksEl.value;
      if (notesEl) _thesis.thesis_notes = notesEl.value;

      const tmEl = $("thesis-last-modified");
      if (tmEl) tmEl.textContent = _formatLastModified(_thesis.last_modified);

      _renderThesisDynamicBlocks();
      _applyMode();
      _setSaveStatus("已保存", "saved");

      if (_saveStatusTimer) clearTimeout(_saveStatusTimer);
      _saveStatusTimer = setTimeout(() => _setSaveStatus("", ""), 1500);
    } catch (err) {
      console.warn("[case] PUT failed:", err);
      _setSaveStatus("网络错误:" + err.message, "error");
    }
  }

  function _escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function _escapeAttr(s) {
    return _escapeHtml(s);
  }

  function _formatNumber(value, decimals) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "--";
    return num.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function _syncOverrideStateFromThesis() {
    _overrideState = _thesis && _thesis.driver_interpretations
      ? { ..._thesis.driver_interpretations }
      : {};
  }

  function _syncScenarioOverrideStateFromThesis() {
    _scenarioState = _normalizeScenarioStates(_thesis ? _thesis.scenario_states : null);
    _getSelectedDrivers().forEach(driverId => {
      ["base", "bull", "bear"].forEach(scenario => _ensureScenarioValue(driverId, scenario));
    });
  }

  function _syncOpenOverrideTextareas() {
    document.querySelectorAll("[data-interpretation-textarea]").forEach(textarea => {
      const driverId = textarea.getAttribute("data-interpretation-textarea");
      if (!driverId || !_openInterpretationEditors.has(driverId)) return;
      if (!Object.prototype.hasOwnProperty.call(_overrideState, driverId)) return;

      const value = textarea.value || "";
      if (value.trim() === "") {
        delete _overrideState[driverId];
      } else {
        _overrideState[driverId] = value;
      }
    });
  }

  function _getSelectedDriverInterpretationsPayload() {
    const selectedSet = new Set(_getSelectedDrivers());
    const payload = {};
    Object.entries(_overrideState).forEach(([driverId, value]) => {
      if (!selectedSet.has(driverId)) return;
      if (typeof value === "string" && value.trim() !== "") {
        payload[driverId] = value;
      }
    });
    return payload;
  }

  function _formatScenarioStateLabel(value) {
    const labels = {
      stronger: "变好 · 增强",
      stable  : "差不多 · 稳定",
      weaker  : "变差 · 减弱",
      unknown : "先不判断",
    };
    return labels[value] || value;
  }

  function _ensureScenarioValue(driverId, scenario) {
    if (!_scenarioState[scenario]) _scenarioState[scenario] = {};
    if (Shared.SCENARIO_STATE_VALUES.includes(_scenarioState[scenario][driverId])) return;
    _scenarioState[scenario][driverId] = Shared.getDefaultScenarioState(driverId)[scenario];
  }

  function _setBackLink() {
    const link = $("back-to-dcf");
    if (!link) return;
    link.href = _ticker
      ? `/modeling/dcf?symbol=${encodeURIComponent(_ticker)}`
      : "/modeling/dcf";
  }

  async function _init() {
    if (!Shared) {
      console.warn("[case] ThesisShared is missing");
      return;
    }

    _ticker = Shared.getTickerFromURL();
    _setBackLink();

    if (!_ticker) {
      const panel = $("case-panel");
      if (panel) panel.style.display = "none";
      return;
    }

    _bindEvents();
    await Promise.all([_loadOntology(), _loadThesis()]);
    _renderHeaderAndNotes();
    _renderThesisDynamicBlocks();
    _applyMode();
    _renderAssumptionBridge();
    _renderAssumptionBridgeToggle();
    _updatePreviewBtnState();
  }

  window.saveThesis = _saveThesis;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _init);
  } else {
    _init();
  }
})();
