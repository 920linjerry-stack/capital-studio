const API = "http://127.0.0.1:5000";
let currentResult = null;
let currentDefaultBuilder = null;
let currentDefaultsPanelData = null;
let currentSuitability = null;
let currentScenarios = null;
let currentSensitivity = null;
let defaultsOverridden = false;
let activeCaseId = null;

const SCENARIO_KEYS = ["base", "upside", "downside"];
const SCENARIO_COL_LABELS = { base: "Base Case", upside: "Upside Case", downside: "Downside Case" };
const SAVED_CASES_KEY = "lbo_saved_cases_v1";

const PRESET_TRANCHES = [
  { id: "revolver", name: "Revolver", type: "revolver", opening_balance: 0, commitment: 500, interest_rate: 8.0, mandatory_amortization_pct: 0.0, maturity_year: 5, sweep_priority: 4, draw_allowed: true, optional_repay_allowed: true },
  { id: "tla", name: "Term Loan A", type: "term_loan_a", opening_balance: 1500, commitment: 1500, interest_rate: 8.5, mandatory_amortization_pct: 5.0, maturity_year: 5, sweep_priority: 1, draw_allowed: false, optional_repay_allowed: true },
  { id: "tlb", name: "Term Loan B", type: "term_loan_b", opening_balance: 2500, commitment: 2500, interest_rate: 9.0, mandatory_amortization_pct: 1.0, maturity_year: 7, sweep_priority: 2, draw_allowed: false, optional_repay_allowed: true },
  { id: "senior_notes", name: "Senior Notes", type: "senior_notes", opening_balance: 1000, commitment: 1000, interest_rate: 10.0, mandatory_amortization_pct: 0.0, maturity_year: 8, sweep_priority: 3, draw_allowed: false, optional_repay_allowed: false },
];

const SUPPORTED_CURRENCIES = ["USD", "HKD", "CNY"];

// Map known engine error codes to user-readable, bilingual explanations. The
// engine error code is always preserved; this only adds guidance for the user.
const FRIENDLY_ERRORS = {
  DEBT_EXCEEDS_USES: {
    en: "Debt amount exceeds total uses. The current transaction size from Entry EBITDA × Entry Multiple is not large enough to support the selected debt amount. Reduce Debt Amount, increase Entry EBITDA/Entry Multiple, or reload defaults.",
    cn: "债务金额超过总资金用途。当前 Entry EBITDA × Entry Multiple 形成的交易规模不足以支持这么高的 Debt Amount。请降低 Debt Amount、提高 Entry EBITDA/Entry Multiple，或点击 Load Defaults 重新生成结构。",
  },
};

function normalizeCurrency(value) {
  const code = String(value || "").trim().toUpperCase();
  return SUPPORTED_CURRENCIES.includes(code) ? code : "USD";
}

function currentCurrency() {
  return normalizeCurrency(document.getElementById("currency").value);
}

// Update every currency-dependent unit label in inputs and result cards.
function updateUnitLabels() {
  const ccy = currentCurrency();
  // Keep the select itself on a valid value.
  const sel = document.getElementById("currency");
  if (sel && sel.value !== ccy) sel.value = ccy;
  document.querySelectorAll(".unit-tag").forEach(el => {
    // Preserve any surrounding parentheses present in the original markup.
    el.textContent = el.textContent.includes("(") ? `(${ccy} mm)` : ccy;
  });
  document.querySelectorAll("[data-ccy-note]").forEach(el => {
    el.textContent = `Amounts in ${ccy} mm`;
  });
  const dbtLabel = document.getElementById("debt_amount_label");
  if (dbtLabel) {
    const multi = isMultiMode();
    const auto = debtSizingMode() === "leverage";
    dbtLabel.innerHTML = multi
      ? `Total Opening Debt <span class="unit-tag">(${ccy} mm)</span>`
      : auto
      ? `Debt Amount <span class="unit-tag">(auto, ${ccy} mm)</span>`
      : `Debt Amount <span class="unit-tag">(${ccy} mm)</span>`;
  }
}

function debtSizingMode() {
  const sel = document.getElementById("debt_sizing");
  return sel && sel.value === "manual" ? "manual" : "leverage";
}

function trancheOpeningDebt() {
  if (!isMultiMode()) return 0;
  const host = document.getElementById("tranche-editor");
  if (!host) return 0;
  return PRESET_TRANCHES.reduce((total, preset, i) => {
    const enabled = host.querySelector(`.tranche-enabled[data-idx="${i}"]`);
    if (enabled && !enabled.checked) return total;
    const input = host.querySelector(`input[data-idx="${i}"][data-field="opening_balance"]`);
    return total + Number((input && input.value) || 0);
  }, 0);
}

// Keep Debt Amount / Leverage Multiple / Implied Leverage consistent with the
// selected debt sizing mode. Pure UI sync; the engine still receives a single
// debt input via buildPayload().
function syncDebtSizing() {
  const mode = debtSizingMode();
  const debtInput = document.getElementById("debt_amount");
  const levInput = document.getElementById("leverage_multiple");
  const impliedRow = document.getElementById("implied-leverage-row");
  const impliedOut = document.getElementById("implied-leverage");
  const hint = document.getElementById("debt-sizing-hint");
  const ebitda = num("entry_ebitda");

  if (isMultiMode()) {
    const openingDebt = trancheOpeningDebt();
    const implied = ebitda > 0 ? openingDebt / ebitda : null;
    debtInput.value = openingDebt;
    debtInput.readOnly = true;
    debtInput.classList.add("input-readonly");
    levInput.value = implied === null ? "" : implied.toFixed(1);
    levInput.readOnly = true;
    levInput.classList.add("input-readonly");
    if (impliedRow) impliedRow.style.display = "";
    if (impliedOut) impliedOut.textContent = implied === null ? "n/a" : `${implied.toFixed(1)}x`;
    if (hint) hint.textContent = "Multi-tranche mode: Total Opening Debt is the sum of selected tranche opening balances.";
    const begCashDisplay = document.getElementById("cash_balance_beginning_display");
    if (begCashDisplay) begCashDisplay.textContent = num("cash_to_balance_sheet");
    updateUnitLabels();
    return;
  }

  if (mode === "leverage") {
    // Leverage drives debt. Debt Amount is computed and read-only.
    const lev = num("leverage_multiple");
    debtInput.value = ebitda * lev;
    debtInput.readOnly = true;
    debtInput.classList.add("input-readonly");
    levInput.readOnly = false;
    levInput.classList.remove("input-readonly");
    if (impliedRow) impliedRow.style.display = "none";
    if (hint) hint.textContent = "按倍数模式：Debt = EBITDA × Leverage，随 EBITDA / 杠杆自动更新。";
  } else {
    // Manual debt. Leverage Multiple becomes informational; show implied lev.
    debtInput.readOnly = false;
    debtInput.classList.remove("input-readonly");
    levInput.readOnly = true;
    levInput.classList.add("input-readonly");
    const debt = num("debt_amount");
    if (impliedRow) impliedRow.style.display = "";
    if (impliedOut) impliedOut.textContent = ebitda > 0 ? `${(debt / ebitda).toFixed(1)}x` : "n/a";
    if (hint) hint.textContent = "手动模式：Debt Amount 手动输入，系统显示 implied leverage。";
  }
  // Beginning Cash is a read-only mirror of Cash to Balance Sheet (single cash
  // figure; never editable independently).
  const begCashDisplay = document.getElementById("cash_balance_beginning_display");
  if (begCashDisplay) begCashDisplay.textContent = num("cash_to_balance_sheet");
  updateUnitLabels();
}

function isMultiMode() {
  const sel = document.getElementById("debt_mode");
  return sel && sel.value === "multi";
}

function num(id) {
  return Number(document.getElementById(id).value || 0);
}

function money(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function pct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  return (Number(v) * 100).toFixed(1) + "%";
}

function multiple(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  return Number(v).toFixed(2) + "x";
}

// ── Forecast layer (UI only; engine still receives operating_forecast arrays) ─
// "growth": driver-based 5-year forecast (default). "manual": user year-by-year.
// "Flat Forecast" is intentionally not a user-visible option; the backend keeps
// a flat fallback for legacy payloads only.
const FORECAST_FIELDS = ["revenue", "ebitda", "cash_taxes", "capex", "change_in_nwc"];
let forecastMode = "growth";
let manualForecast = null; // { revenue:[5], ebitda:[5], cash_taxes:[5], capex:[5], change_in_nwc:[5] }

// Build a driver-based 5-year forecast. Does not touch Entry EBITDA.
function generateGrowthForecast() {
  const y1 = num("rev_y1");
  const g = num("rev_growth") / 100;
  const margin = num("ebitda_margin") / 100;
  const taxPct = num("tax_pct_ebitda") / 100;
  const capexPct = num("capex_pct_rev") / 100;
  const nwcPct = num("nwc_pct_rev") / 100;
  const revenue = [], ebitda = [], cash_taxes = [], capex = [], change_in_nwc = [];
  let rev = y1;
  for (let i = 0; i < 5; i++) {
    if (i > 0) rev = rev * (1 + g);
    const e = rev * margin;
    revenue.push(rev);
    ebitda.push(e);
    cash_taxes.push(e * taxPct);
    capex.push(rev * capexPct);
    change_in_nwc.push(rev * nwcPct);
  }
  return { years: [1, 2, 3, 4, 5], revenue, ebitda, cash_taxes, capex, change_in_nwc };
}

// The forecast arrays that currently drive the model.
function activeForecast() {
  if (forecastMode === "manual" && manualForecast) {
    return { years: [1, 2, 3, 4, 5], ...manualForecast };
  }
  return generateGrowthForecast();
}

function updateForecastModeIndicator() {
  const label = forecastMode === "manual" ? "Manual Forecast" : "Growth Forecast";
  const ind = document.getElementById("forecast-mode-indicator");
  if (ind) ind.textContent = label;
  const note = document.getElementById("forecast-active-note");
  if (note) note.textContent = forecastMode === "manual"
    ? "Manual forecast active / 已使用手动逐年预测"
    : "Growth forecast active";
  const resetBtn = document.getElementById("reset-growth-btn");
  if (resetBtn) resetBtn.style.display = forecastMode === "manual" ? "" : "none";
}

function showForecastToast() {
  const toast = document.getElementById("forecast-toast");
  if (!toast) return;
  toast.textContent = "预测已保存。 / Forecast saved.";
  toast.style.display = "block";
  clearTimeout(showForecastToast._t);
  showForecastToast._t = setTimeout(() => { toast.style.display = "none"; }, 2600);
}

function showCaseToast(message) {
  const toast = document.getElementById("case-toast") || document.getElementById("forecast-toast");
  if (!toast) return;
  toast.textContent = message;
  toast.style.display = "block";
  clearTimeout(showCaseToast._t);
  showCaseToast._t = setTimeout(() => { toast.style.display = "none"; }, 2800);
}

function readSavedCasesStore() {
  try {
    const raw = window.localStorage.getItem(SAVED_CASES_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && Array.isArray(parsed.cases) ? parsed : { cases: [] };
  } catch (e) {
    return { cases: [] };
  }
}

function writeSavedCasesStore(store) {
  window.localStorage.setItem(SAVED_CASES_KEY, JSON.stringify({ cases: store.cases || [] }));
}

function currentGrowthDrivers() {
  return {
    rev_y1: num("rev_y1"),
    rev_growth: num("rev_growth"),
    ebitda_margin: num("ebitda_margin"),
    tax_pct_ebitda: num("tax_pct_ebitda"),
    capex_pct_rev: num("capex_pct_rev"),
    nwc_pct_rev: num("nwc_pct_rev"),
  };
}

function buildCaseUiState() {
  return {
    forecast_mode: forecastMode === "manual" ? "manual" : "growth",
    debt_sizing_mode: debtSizingMode(),
    capital_structure_mode: isMultiMode() ? "multi_tranche" : "single",
    growth_drivers: currentGrowthDrivers(),
    manual_forecast: manualForecast ? JSON.parse(JSON.stringify(manualForecast)) : null,
  };
}

function buildCaseRecord(name, existing) {
  const now = new Date().toISOString();
  const payload = buildPayload();
  delete payload.scenarios;
  delete payload.default_builder;
  delete payload.suitability;
  return {
    id: existing ? existing.id : `case_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    name,
    created_at: existing ? existing.created_at : now,
    updated_at: now,
    payload,
    ui_state: buildCaseUiState(),
  };
}

function openSaveCaseModal() {
  const overlay = document.getElementById("case-save-overlay");
  const input = document.getElementById("case-name-input");
  if (!overlay || !input) return;
  const store = readSavedCasesStore();
  const existing = activeCaseId ? store.cases.find(c => c.id === activeCaseId) : null;
  input.value = existing ? existing.name : "";
  overlay.style.display = "flex";
  setTimeout(() => input.focus(), 0);
}

function closeSaveCaseModal() {
  const overlay = document.getElementById("case-save-overlay");
  if (overlay) overlay.style.display = "none";
}

function saveCurrentCase() {
  const input = document.getElementById("case-name-input");
  const rawName = input ? input.value.trim() : "";
  const name = rawName || `${(document.getElementById("symbol").value || "SYNTH").toUpperCase()} LBO Case`;
  const store = readSavedCasesStore();
  const sameName = store.cases.find(c => c.name.toLowerCase() === name.toLowerCase());
  if (sameName && sameName.id !== activeCaseId) {
    const ok = window.confirm("A case with this name exists. Overwrite?");
    if (!ok) return;
    activeCaseId = sameName.id;
  }
  const existing = activeCaseId ? store.cases.find(c => c.id === activeCaseId) : sameName;
  const record = buildCaseRecord(name, existing || null);
  const next = store.cases.filter(c => c.id !== record.id);
  next.unshift(record);
  writeSavedCasesStore({ cases: next });
  activeCaseId = record.id;
  closeSaveCaseModal();
  refreshVisibleCaseChoosers();
  showCaseToast("Case saved.");
}

function clearResultOutputsForLoadedCase() {
  currentResult = null;
  clearError();
  ["headline-grid", "transaction-table", "forecast-table", "debt-table", "exit-bridge-table", "returns-table", "audit-list"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = "";
  });
  ["attribution-card", "capstructure-card", "covenant-card", "maturity-card"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  });
  renderReturnContext(null);
  renderDebtStressHint(null);
  updateExportState();
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatCaseDate(value) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function renderCaseListPanel() {
  const panel = document.getElementById("case-list-panel");
  if (!panel) return false;
  const cases = readSavedCasesStore().cases;
  if (!cases.length) {
    panel.style.display = "none";
    panel.innerHTML = "";
    return false;
  }
  const rows = cases.map(c => {
    const payload = c.payload || {};
    const ui = c.ui_state || {};
    const symbol = payload.symbol || "SYNTH";
    const currency = payload.currency || "USD";
    const forecast = ui.forecast_mode || payload.forecast_mode || "growth";
    const cap = ui.capital_structure_mode || (payload.capital_structure ? "multi_tranche" : "single");
    return `
      <div class="case-list-row" data-case-id="${escapeHtml(c.id)}">
        <div>
          <div class="case-list-name">${escapeHtml(c.name)}</div>
          <div class="case-list-meta">${escapeHtml(symbol)} · ${escapeHtml(currency)} · Updated ${escapeHtml(formatCaseDate(c.updated_at))} · ${escapeHtml(forecast)} · ${escapeHtml(cap)}</div>
        </div>
        <div class="case-list-actions">
          <button class="btn btn-secondary btn-sm case-open-btn" type="button" data-case-id="${escapeHtml(c.id)}">Open</button>
          <button class="btn btn-secondary btn-sm case-delete-btn" type="button" data-case-id="${escapeHtml(c.id)}">Delete</button>
        </div>
      </div>`;
  }).join("");
  panel.innerHTML = `
    <div class="case-list-head">
      <div>
        <div class="case-list-title">选择 LBO Case / Select LBO Case</div>
        <div class="defaults-subtitle">Open a saved case or start from a blank case.</div>
      </div>
      <button class="btn btn-secondary btn-sm" id="blank-case-btn" type="button">Blank Case / 空白搭建</button>
    </div>
    ${rows}
  `;
  panel.style.display = "block";
  panel.querySelectorAll(".case-open-btn").forEach(btn => {
    btn.addEventListener("click", () => openSavedCase(btn.dataset.caseId));
  });
  panel.querySelectorAll(".case-delete-btn").forEach(btn => {
    btn.addEventListener("click", () => deleteSavedCase(btn.dataset.caseId));
  });
  const blank = document.getElementById("blank-case-btn");
  if (blank) blank.addEventListener("click", startBlankCase);
  return true;
}

function openSavedCase(id) {
  const record = readSavedCasesStore().cases.find(c => c.id === id);
  if (!record) return;
  applyCaseRecord(record);
  const panel = document.getElementById("case-list-panel");
  if (panel) panel.style.display = "none";
}

function deleteSavedCase(id) {
  const store = readSavedCasesStore();
  const next = store.cases.filter(c => c.id !== id);
  writeSavedCasesStore({ cases: next });
  if (activeCaseId === id) activeCaseId = null;
  renderCaseListPanel();
  showCaseToast("Case deleted.");
}

function startBlankCase() {
  activeCaseId = null;
  const panel = document.getElementById("case-list-panel");
  if (panel) panel.style.display = "none";
  runLbo();
}

function renderCaseRowsV474(cases, target) {
  const rows = cases.map(c => {
    const payload = c.payload || {};
    const ui = c.ui_state || {};
    const symbol = payload.symbol || "SYNTH";
    const currency = payload.currency || "USD";
    const forecast = ui.forecast_mode || payload.forecast_mode || "growth";
    const cap = ui.capital_structure_mode || (payload.capital_structure ? "multi_tranche" : "single");
    return `
      <div class="case-list-row" data-case-id="${escapeHtml(c.id)}" data-case-name="${escapeHtml(c.name)}">
        <div>
          <div class="case-list-name">${escapeHtml(c.name)}</div>
          <div class="case-list-meta">${escapeHtml(symbol)} · ${escapeHtml(currency)} · Updated ${escapeHtml(formatCaseDate(c.updated_at))} · ${escapeHtml(forecast)} · ${escapeHtml(cap)}</div>
        </div>
        <div class="case-list-actions">
          <button class="btn btn-secondary btn-sm case-open-btn" type="button" data-case-target="${target}" data-case-id="${escapeHtml(c.id)}">Open</button>
          <button class="btn btn-secondary btn-sm case-delete-btn" type="button" data-case-target="${target}" data-case-id="${escapeHtml(c.id)}">Delete</button>
        </div>
      </div>`;
  }).join("");
  return rows || `<div class="case-list-row"><div><div class="case-list-meta">No saved cases yet.</div></div></div>`;
}

function caseChooserHtml(cases, target) {
  const blankId = target === "switcher" ? "switch-blank-case-btn" : "blank-case-btn";
  const cardClass = target === "switcher" ? "case-switcher-card-inner" : "case-launcher-card";
  return `
    <div class="${cardClass}">
      <div class="case-list-head">
        <div>
          <div class="case-list-title">选择 LBO Case / Select LBO Case</div>
          <div class="case-list-subtitle">Open a saved case or start from a blank case.</div>
          <div class="case-list-subtitle">打开已保存的 case，或从空白模型开始搭建。</div>
        </div>
        <button class="btn btn-secondary btn-sm blank-case-btn" id="${blankId}" data-case-target="${target}" type="button">Blank Case / 空白搭建</button>
      </div>
      ${renderCaseRowsV474(cases, target)}
    </div>
  `;
}

function bindCaseChooser(container) {
  if (!container) return;
  container.querySelectorAll(".case-open-btn").forEach(btn => {
    btn.addEventListener("click", () => openSavedCase(btn.dataset.caseId, btn.dataset.caseTarget || "launcher"));
  });
  container.querySelectorAll(".case-delete-btn").forEach(btn => {
    btn.addEventListener("click", () => deleteSavedCase(btn.dataset.caseId, btn.dataset.caseTarget || "launcher"));
  });
  container.querySelectorAll(".blank-case-btn").forEach(btn => {
    btn.addEventListener("click", () => startBlankCase(btn.dataset.caseTarget || "launcher"));
  });
}

function renderCaseListPanel(forceShow = false) {
  const panel = document.getElementById("case-list-panel");
  if (!panel) return false;
  const cases = readSavedCasesStore().cases;
  if (!cases.length && !forceShow) {
    panel.style.display = "none";
    panel.innerHTML = "";
    return false;
  }
  panel.innerHTML = caseChooserHtml(cases, "launcher");
  panel.style.display = "flex";
  bindCaseChooser(panel);
  return true;
}

function hideCaseLauncher() {
  const panel = document.getElementById("case-list-panel");
  if (panel) panel.style.display = "none";
}

function openCaseSwitcher() {
  const overlay = document.getElementById("case-switcher-overlay");
  const body = document.getElementById("case-switcher-body");
  if (!overlay || !body) return;
  body.innerHTML = caseChooserHtml(readSavedCasesStore().cases, "switcher");
  bindCaseChooser(body);
  overlay.style.display = "flex";
}

function closeCaseSwitcher() {
  const overlay = document.getElementById("case-switcher-overlay");
  if (overlay) overlay.style.display = "none";
}

function refreshVisibleCaseChoosers() {
  const launcher = document.getElementById("case-list-panel");
  if (launcher && launcher.style.display !== "none" && launcher.innerHTML) {
    renderCaseListPanel(true);
  }
  const switcher = document.getElementById("case-switcher-overlay");
  if (switcher && switcher.style.display !== "none") {
    openCaseSwitcher();
  }
}

function closeCaseChoosers() {
  hideCaseLauncher();
  closeCaseSwitcher();
}

async function openSavedCase(id, target = "launcher") {
  const record = readSavedCasesStore().cases.find(c => c.id === id);
  if (!record) return;
  applyCaseRecord(record);
  closeCaseChoosers();
  const result = await runLbo();
  if (result && result.status === "ok") showCaseToast("Case loaded and refreshed.");
}

function deleteSavedCase(id, target = "launcher") {
  const store = readSavedCasesStore();
  const next = store.cases.filter(c => c.id !== id);
  writeSavedCasesStore({ cases: next });
  if (activeCaseId === id) activeCaseId = null;
  if (target === "switcher") {
    openCaseSwitcher();
  } else {
    renderCaseListPanel(true);
  }
  showCaseToast("Case deleted.");
}

function resetBlankCaseInputs() {
  setValue("symbol", "SYNTH");
  setValue("currency", "USD");
  setValue("entry_ebitda", 1000);
  setValue("entry_multiple", 10.0);
  setValue("exit_multiple", 10.0);
  setValue("exit_year", 5);
  setValue("fees_pct", 2.0);
  setValue("debt_sizing", "leverage");
  setValue("leverage_multiple", 5.0);
  setValue("debt_amount", 5000);
  setValue("interest_rate", 9.0);
  setValue("mandatory_amortization_pct", 1.0);
  setValue("cash_sweep_pct", 100.0);
  setValue("cash_to_balance_sheet", 0);
  setValue("debt_mode", "single");
  setValue("minimum_cash_balance", 0);
  setValue("max_net_debt_ebitda", 6.0);
  setValue("min_interest_coverage", 2.0);
  setValue("rev_y1", 5000);
  setValue("rev_growth", 5.0);
  setValue("ebitda_margin", 20.0);
  setValue("tax_pct_ebitda", 10.0);
  setValue("tax_rate", 25.0);
  setValue("tax_shield_enabled", "enabled");
  setValue("capex_pct_rev", 3.0);
  setValue("nwc_pct_rev", 0.4);
  forecastMode = "growth";
  manualForecast = null;
  currentDefaultBuilder = null;
  currentDefaultsPanelData = null;
  currentSuitability = null;
  currentSensitivity = null;
  defaultsOverridden = false;
  const multiInputs = document.getElementById("multi-tranche-inputs");
  if (multiInputs) multiInputs.style.display = "none";
  const defaultsPanel = document.getElementById("defaults-panel");
  if (defaultsPanel) {
    defaultsPanel.style.display = "none";
    defaultsPanel.innerHTML = "";
  }
  renderSuitabilityPanel(null);
  renderTrancheEditor();
  updateForecastModeIndicator();
  updateUnitLabels();
  syncDebtSizing();
}

function startBlankCase(target = "launcher") {
  activeCaseId = null;
  resetBlankCaseInputs();
  invalidateScenarios();
  clearResultOutputsForLoadedCase();
  closeCaseChoosers();
}

function buildPayload() {
  const years = [1, 2, 3, 4, 5];
  const debt = {
    interest_rate: num("interest_rate") / 100,
    mandatory_amortization_pct: num("mandatory_amortization_pct") / 100,
    cash_sweep_pct: num("cash_sweep_pct") / 100,
    cash_to_balance_sheet: num("cash_to_balance_sheet"),
  };
  // Multi-tranche mode uses tranche opening balances as the debt source of
  // truth. Single-tranche mode keeps the existing debt sizing controls.
  if (isMultiMode()) {
    const openingDebt = trancheOpeningDebt();
    debt.debt_amount = openingDebt;
    if (num("entry_ebitda") > 0) debt.leverage_multiple = openingDebt / num("entry_ebitda");
  } else if (debtSizingMode() === "manual") {
    debt.debt_amount = num("debt_amount");
  } else {
    debt.leverage_multiple = num("leverage_multiple");
  }
  const payload = {
    symbol: document.getElementById("symbol").value.trim().toUpperCase() || "SYNTH",
    currency: currentCurrency(),
    transaction: {
      entry_ebitda: num("entry_ebitda"),
      entry_multiple: num("entry_multiple"),
      exit_multiple: num("exit_multiple"),
      exit_year: Number(document.getElementById("exit_year").value || years.length),
      transaction_fees_pct_ev: num("fees_pct") / 100,
    },
    operating_forecast: activeForecast(),
    tax_rate: num("tax_rate") / 100,
    tax_shield_enabled: (document.getElementById("tax_shield_enabled").value || "enabled") === "enabled",
    forecast_mode: forecastMode === "manual" ? "manual" : "growth",
    debt,
  };
  if (isMultiMode()) {
    const cs = buildCapitalStructure();
    if (cs) payload.capital_structure = cs;
  }
  if (currentDefaultBuilder) payload.default_builder = currentDefaultBuilder;
  if (currentSuitability) payload.suitability = currentSuitability;
  return payload;
}

const MANUAL_ROW_LABELS = {
  revenue: "Revenue",
  ebitda: "EBITDA",
  cash_taxes: "Cash Taxes",
  capex: "CapEx",
  change_in_nwc: "Change in NWC",
};

function renderManualTable(forecast) {
  const table = document.getElementById("manual-forecast-table");
  if (!table) return;
  const head = `<thead><tr><th></th>${[1, 2, 3, 4, 5].map(y => `<th>Y${y}</th>`).join("")}</tr></thead>`;
  const body = FORECAST_FIELDS.map(field => {
    const vals = (forecast[field] || []);
    const cells = [0, 1, 2, 3, 4].map(i =>
      `<td><input type="number" step="0.1" id="manual_${field}_${i}" value="${Number(vals[i] || 0).toFixed(1)}" /></td>`
    ).join("");
    return `<tr><td style="text-align:left;">${MANUAL_ROW_LABELS[field]} <span class="unit-tag">(USD mm)</span></td>${cells}</tr>`;
  }).join("");
  table.innerHTML = head + `<tbody>${body}</tbody>`;
}

function openManualForecast() {
  // Seed the overlay from the currently active forecast so manual editing
  // starts from what the user already sees.
  renderManualTable(activeForecast());
  document.getElementById("manual-forecast-overlay").style.display = "flex";
  updateUnitLabels();
}

function closeManualForecast() {
  document.getElementById("manual-forecast-overlay").style.display = "none";
}

function saveManualForecast() {
  const out = {};
  FORECAST_FIELDS.forEach(field => {
    out[field] = [0, 1, 2, 3, 4].map(i => Number(document.getElementById(`manual_${field}_${i}`).value || 0));
  });
  manualForecast = out;
  forecastMode = "manual";
  closeManualForecast();
  updateForecastModeIndicator();
  showForecastToast();
  invalidateScenarios();
  runLbo();
}

function resetToGrowth() {
  forecastMode = "growth";
  updateForecastModeIndicator();
  invalidateScenarios();
  runLbo();
}

function renderTrancheEditor() {
  const host = document.getElementById("tranche-editor");
  if (!host) return;
  host.innerHTML = PRESET_TRANCHES.map((t, i) => `
    <div class="tranche-block" data-idx="${i}">
      <div class="tranche-block-head">
        <input type="checkbox" class="tranche-enabled" data-idx="${i}" checked />
        <span>${t.name}</span>
      </div>
      <div class="field-row"><span class="field-label">Opening</span><input class="tranche-mini" data-idx="${i}" data-field="opening_balance" type="number" value="${t.opening_balance}" /></div>
      <div class="field-row"><span class="field-label">Commitment</span><input class="tranche-mini" data-idx="${i}" data-field="commitment" type="number" value="${t.commitment}" /></div>
      <div class="field-row"><span class="field-label">Rate %</span><input class="tranche-mini" data-idx="${i}" data-field="interest_rate" type="number" step="0.1" value="${t.interest_rate}" /></div>
      <div class="field-row"><span class="field-label">Amort %</span><input class="tranche-mini" data-idx="${i}" data-field="mandatory_amortization_pct" type="number" step="0.1" value="${t.mandatory_amortization_pct}" /></div>
      <div class="field-row"><span class="field-label">Maturity Yr</span><input class="tranche-mini" data-idx="${i}" data-field="maturity_year" type="number" value="${t.maturity_year}" /></div>
      <div class="field-row"><span class="field-label">Optional Repay</span><input type="checkbox" class="tranche-optional" data-idx="${i}" ${t.optional_repay_allowed ? "checked" : ""} /></div>
    </div>`).join("");
  host.querySelectorAll("input").forEach(el => {
    el.addEventListener("input", () => { markDefaultsOverridden(); syncDebtSizing(); invalidateScenarios(); invalidateSensitivity(); });
    el.addEventListener("change", () => { markDefaultsOverridden(); syncDebtSizing(); runLbo(); });
  });
}

function buildCapitalStructure() {
  const host = document.getElementById("tranche-editor");
  if (!host) return null;
  const tranches = [];
  PRESET_TRANCHES.forEach((preset, i) => {
    const enabled = host.querySelector(`.tranche-enabled[data-idx="${i}"]`);
    if (enabled && !enabled.checked) return;
    const get = (field) => Number(host.querySelector(`input[data-idx="${i}"][data-field="${field}"]`).value || 0);
    const optional = host.querySelector(`.tranche-optional[data-idx="${i}"]`);
    tranches.push({
      id: preset.id,
      name: preset.name,
      type: preset.type,
      opening_balance: get("opening_balance"),
      commitment: get("commitment"),
      interest_rate: get("interest_rate") / 100,
      mandatory_amortization_pct: get("mandatory_amortization_pct") / 100,
      maturity_year: get("maturity_year"),
      sweep_priority: preset.sweep_priority,
      draw_allowed: preset.draw_allowed,
      optional_repay_allowed: optional ? optional.checked : preset.optional_repay_allowed,
      cash_pay: true,
      pik_enabled: false,
    });
  });
  if (!tranches.length) return null;
  return {
    mode: "multi_tranche",
    cash_balance_beginning: num("cash_to_balance_sheet"),
    minimum_cash_balance: num("minimum_cash_balance"),
    cash_sweep_enabled: true,
    tranches,
    covenants: {
      max_net_debt_ebitda: num("max_net_debt_ebitda"),
      min_interest_coverage: num("min_interest_coverage"),
    },
  };
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el && value !== undefined && value !== null) el.value = value;
}

function applyGrowthDrivers(drivers) {
  if (!drivers) return;
  setValue("rev_y1", drivers.rev_y1);
  setValue("rev_growth", drivers.rev_growth);
  setValue("ebitda_margin", drivers.ebitda_margin);
  setValue("tax_pct_ebitda", drivers.tax_pct_ebitda);
  setValue("capex_pct_rev", drivers.capex_pct_rev);
  setValue("nwc_pct_rev", drivers.nwc_pct_rev);
}

function applyCapitalStructure(cs) {
  const debtMode = document.getElementById("debt_mode");
  const multiInputs = document.getElementById("multi-tranche-inputs");
  if (debtMode) debtMode.value = cs ? "multi" : "single";
  if (multiInputs) multiInputs.style.display = cs ? "block" : "none";
  if (!cs) return;
  setValue("minimum_cash_balance", cs.minimum_cash_balance);
  setValue("max_net_debt_ebitda", cs.covenants && cs.covenants.max_net_debt_ebitda);
  setValue("min_interest_coverage", cs.covenants && cs.covenants.min_interest_coverage);
  const byId = {};
  (cs.tranches || []).forEach(t => { byId[t.id] = t; });
  PRESET_TRANCHES.forEach((preset, i) => {
    const tranche = byId[preset.id];
    const enabled = document.querySelector(`.tranche-enabled[data-idx="${i}"]`);
    if (enabled) enabled.checked = !!tranche;
    if (!tranche) return;
    setValueForSelector(`input[data-idx="${i}"][data-field="opening_balance"]`, tranche.opening_balance);
    setValueForSelector(`input[data-idx="${i}"][data-field="commitment"]`, tranche.commitment);
    setValueForSelector(`input[data-idx="${i}"][data-field="interest_rate"]`, Number(tranche.interest_rate || 0) * 100);
    setValueForSelector(`input[data-idx="${i}"][data-field="mandatory_amortization_pct"]`, Number(tranche.mandatory_amortization_pct || 0) * 100);
    setValueForSelector(`input[data-idx="${i}"][data-field="maturity_year"]`, tranche.maturity_year);
    const optional = document.querySelector(`.tranche-optional[data-idx="${i}"]`);
    if (optional) optional.checked = !!tranche.optional_repay_allowed;
  });
}

function setValueForSelector(selector, value) {
  const el = document.querySelector(selector);
  if (el && value !== undefined && value !== null) el.value = value;
}

function applyCaseRecord(record) {
  if (!record || !record.payload) return;
  const payload = record.payload;
  const ui = record.ui_state || {};
  activeCaseId = record.id;
  setValue("symbol", payload.symbol || "SYNTH");
  setValue("currency", normalizeCurrency(payload.currency));
  const t = payload.transaction || {};
  setValue("entry_ebitda", t.entry_ebitda);
  setValue("entry_multiple", t.entry_multiple);
  setValue("exit_multiple", t.exit_multiple);
  setValue("exit_year", t.exit_year);
  setValue("fees_pct", Number(t.transaction_fees_pct_ev || 0) * 100);
  const d = payload.debt || {};
  const sizing = ui.debt_sizing_mode || (d.debt_amount !== undefined ? "manual" : "leverage");
  setValue("debt_sizing", sizing);
  setValue("debt_amount", d.debt_amount);
  setValue("leverage_multiple", d.leverage_multiple);
  setValue("interest_rate", Number(d.interest_rate || 0) * 100);
  setValue("mandatory_amortization_pct", Number(d.mandatory_amortization_pct || 0) * 100);
  setValue("cash_sweep_pct", Number(d.cash_sweep_pct || 0) * 100);
  setValue("cash_to_balance_sheet", d.cash_to_balance_sheet);
  setValue("tax_rate", payload.tax_rate === undefined ? 25.0 : Number(payload.tax_rate || 0) * 100);
  setValue("tax_shield_enabled", payload.tax_shield_enabled === false ? "disabled" : "enabled");
  applyGrowthDrivers(ui.growth_drivers);
  forecastMode = ui.forecast_mode || payload.forecast_mode || "growth";
  manualForecast = ui.manual_forecast || (forecastMode === "manual" ? extractManualForecast(payload.operating_forecast) : null);
  applyCapitalStructure(payload.capital_structure || null);
  currentDefaultBuilder = payload.default_builder || null;
  currentSuitability = payload.suitability || null;
  renderSuitabilityPanel(currentSuitability);
  updateForecastModeIndicator();
  updateUnitLabels();
  syncDebtSizing();
  invalidateScenarios();
  clearResultOutputsForLoadedCase();
}

function extractManualForecast(forecast) {
  if (!forecast) return null;
  const out = {};
  FORECAST_FIELDS.forEach(field => { out[field] = (forecast[field] || []).slice(0, 5); });
  return out;
}

function showError(result) {
  const panel = document.getElementById("error-panel");
  const flags = (result && result.flags) || [];
  const blocks = flags.map(f => {
    const friendly = FRIENDLY_ERRORS[f.code];
    let html = `<div><code>${f.code}</code>: ${f.message}</div>`;
    if (friendly) {
      html += `<div style="margin-top:4px;color:var(--text-muted);">${friendly.en}</div>`;
      html += `<div style="margin-top:2px;color:var(--text-muted);">${friendly.cn}</div>`;
      if (f.code === "DEBT_EXCEEDS_USES" && debtSizingMode() === "manual") {
        html += `<div style="margin-top:4px;color:var(--text-muted);">You are using Manual Debt Amount. Switch to By Leverage Multiple to size debt automatically from EBITDA. / 当前使用手动 Debt Amount，可切换到 By Leverage Multiple 让债务按 EBITDA 自动计算。</div>`;
      }
    }
    return html;
  });
  panel.innerHTML = `<strong>LBO calculation blocked</strong><div style="margin-top:6px;">${blocks.join("<br>")}</div>`;
  panel.style.display = "block";
  document.getElementById("headline-grid").innerHTML = "";
}

function clearError() {
  const panel = document.getElementById("error-panel");
  panel.style.display = "none";
  panel.textContent = "";
}

function renderPairs(tableId, rows) {
  const table = document.getElementById(tableId);
  table.innerHTML = rows.map(([label, value]) => `<tr><td>${label}</td><td>${value}</td></tr>`).join("");
}

function renderForecast(result) {
  const f = result.operating_forecast;
  const rowDefs = [
    ["revenue", "revenue"],
    ["ebitda", "ebitda"],
    ["gross_cash_taxes", "gross_cash_taxes"],
    ["tax_shield", "tax_shield"],
    ["levered_cash_taxes", "levered_cash_taxes"],
    ["capex", "capex"],
    ["change_in_nwc", "change_in_nwc"],
  ];
  const rows = rowDefs.map(([key, label]) => {
    const values = f[key] || (key === "gross_cash_taxes" ? f.cash_taxes : []);
    return `<tr><td>${label}</td>${values.map(money).map(v => `<td>${v}</td>`).join("")}</tr>`;
  }).join("");
  document.getElementById("forecast-table").innerHTML = `<thead><tr><th>Metric</th>${f.years.map(y => `<th>Y${y}</th>`).join("")}</tr></thead><tbody>${rows}</tbody>`;
}

function renderMultiDebt(result) {
  const headers = [
    ["year", "Year"], ["cash_flow_before_debt_service", "Cash Before DS"], ["total_cash_interest", "Interest"],
    ["gross_cash_taxes", "Gross Taxes"], ["tax_shield", "Tax Shield"], ["levered_cash_taxes", "Levered Taxes"],
    ["total_mandatory_amortization", "Mandatory"], ["cash_after_interest_and_mandatory_amortization", "Cash After Mandatory"],
    ["revolver_draw", "Revolver Draw"], ["total_optional_repayment", "Optional"],
    ["ending_cash_balance", "Ending Cash"], ["total_beginning_debt", "Beg. Debt"],
    ["total_ending_debt", "End Debt"], ["debt_service_failure", "DS Fail"],
  ];
  const body = result.debt_schedule.map(row => `<tr>${headers.map(([k]) =>
    `<td>${k === "debt_service_failure" ? row[k] : money(row[k])}</td>`).join("")}</tr>`).join("");
  document.getElementById("debt-table").innerHTML =
    `<thead><tr>${headers.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
}

function renderCapStructure(result) {
  const card = document.getElementById("capstructure-card");
  const cs = result.capital_structure_summary;
  if (!card) return;
  if (!cs) { card.style.display = "none"; return; }
  const trancheRows = (cs.tranches || []).map(t =>
    `<tr><td>${t.name}</td><td>${money(t.opening_balance)}</td><td>${money(t.ending_balance)}</td><td>${pct(t.interest_rate)}</td><td>Y${t.maturity_year}</td></tr>`).join("");
  document.getElementById("capstructure-table").innerHTML = `
    <tbody>
      <tr><td>Total Opening Debt</td><td colspan="4">${money(cs.total_opening_debt)}</td></tr>
      <tr><td>Total Ending Debt</td><td colspan="4">${money(cs.total_ending_debt)}</td></tr>
      <tr><td>Ending Cash Balance</td><td colspan="4">${money(cs.ending_cash_balance)}</td></tr>
      <tr><td>Net Debt At Exit</td><td colspan="4">${money(cs.net_debt_at_exit)}</td></tr>
      <tr><td>Wtd Avg Interest (Y1)</td><td colspan="4">${pct(cs.weighted_avg_cash_interest_rate_year_1)}</td></tr>
    </tbody>
    <thead><tr><th>Tranche</th><th>Opening</th><th>Ending</th><th>Rate</th><th>Maturity</th></tr></thead>
    <tbody>${trancheRows}</tbody>`;
  card.style.display = "block";
  const note = document.createElement("div");
  note.className = "defaults-flags";
  note.style.marginTop = "8px";
  note.textContent = cs.single_vs_multi_cash_bridge_note_cn || cs.single_vs_multi_cash_bridge_note || "";
  const existing = card.querySelector(".cs-bridge-note");
  if (existing) existing.remove();
  note.classList.add("cs-bridge-note");
  card.appendChild(note);
}

function covLeverage(chk) {
  if (chk.is_net_cash) return `<span class="badge-netcash">Net cash</span>`;
  if (chk.net_debt_ebitda === null || chk.net_debt_ebitda === undefined) return "--";
  return multiple(chk.net_debt_ebitda);
}

function covHeadroom(chk) {
  if (chk.is_net_cash) return "n/a (net cash)";
  if (chk.leverage_headroom === null || chk.leverage_headroom === undefined) return "--";
  return multiple(chk.leverage_headroom);
}

function renderCovenants(result) {
  const card = document.getElementById("covenant-card");
  const cov = result.covenant_summary;
  if (!card) return;
  if (!cov) { card.style.display = "none"; return; }
  const statusMap = {
    pass: ["badge-pass", "Pass"],
    breach: ["badge-breach", "Breach detected / 契约触发"],
    unavailable: ["badge-unavail", "Unavailable / 不可用"],
  };
  const [cls, label] = statusMap[cov.status] || statusMap.unavailable;
  const breachYears = (cov.breach_years || []).length ? `（breach years: ${cov.breach_years.join(", ")}）` : "";
  document.getElementById("covenant-status").innerHTML =
    `<span class="${cls}">${label}</span> ${breachYears}`;
  const body = (cov.checks || []).map(chk => `<tr>
    <td>Y${chk.year}</td>
    <td>${money(chk.net_debt)}</td>
    <td>${money(chk.ebitda)}</td>
    <td>${covLeverage(chk)}</td>
    <td>${covHeadroom(chk)}</td>
    <td>${chk.leverage_breach ? '<span class="badge-breach">是</span>' : "否"}</td>
    <td>${chk.interest_coverage === null || chk.interest_coverage === undefined ? "n/a" : multiple(chk.interest_coverage)}</td>
    <td>${chk.interest_coverage_breach ? '<span class="badge-breach">是</span>' : "否"}</td>
  </tr>`).join("");
  document.getElementById("covenant-table").innerHTML = `
    <thead><tr><th>Year</th><th>Net Debt</th><th>Forecast EBITDA</th><th>Net Debt / Forecast EBITDA</th><th>Headroom</th><th>Lev. Breach</th><th>Int. Cov.</th><th>Cov. Breach</th></tr></thead>
    <tbody>${body}</tbody>`;
  card.style.display = "block";
}

function renderMaturity(result) {
  const card = document.getElementById("maturity-card");
  const wall = result.maturity_wall;
  if (!card) return;
  if (!wall) { card.style.display = "none"; return; }
  const body = wall.map(b =>
    `<tr><td>Y${b.year}</td><td>${money(b.maturing_debt)}</td><td>${(b.tranches || []).join(", ")}</td></tr>`).join("");
  document.getElementById("maturity-table").innerHTML =
    `<thead><tr><th>Maturity Year</th><th>Outstanding at Exit</th><th>Tranches</th></tr></thead><tbody>${body}</tbody>`;
  card.style.display = "block";
}

function hideMultiCards() {
  ["capstructure-card", "covenant-card", "maturity-card"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  });
}

function renderDebt(result) {
  if (result.capital_structure_summary) {
    document.getElementById("debt-card-title").textContent = "Multi-Tranche Debt Schedule";
    renderMultiDebt(result);
    return;
  }
  document.getElementById("debt-card-title").textContent = "Debt Schedule";
  const headers = ["year", "beginning_debt", "cash_flow_before_debt_service", "cash_interest", "gross_cash_taxes", "tax_shield", "levered_cash_taxes", "mandatory_amortization", "cash_after_interest_and_mandatory_amortization", "optional_repayment", "ending_debt", "debt_service_failure"];
  const labels = {
    year: "Year",
    beginning_debt: "Beg. Debt",
    cash_flow_before_debt_service: "Cash Before DS",
    cash_interest: "Interest",
    gross_cash_taxes: "Gross Taxes",
    tax_shield: "Tax Shield",
    levered_cash_taxes: "Levered Taxes",
    mandatory_amortization: "Mandatory Amort.",
    cash_after_interest_and_mandatory_amortization: "Cash After Mandatory",
    optional_repayment: "Optional Repay.",
    ending_debt: "Ending Debt",
    debt_service_failure: "Debt Service Fail",
  };
  const body = result.debt_schedule.map(row => `<tr>${headers.map(h => `<td>${h === "debt_service_failure" ? row[h] : money(row[h])}</td>`).join("")}</tr>`).join("");
  document.getElementById("debt-table").innerHTML = `<thead><tr>${headers.map(h => `<th>${labels[h]}</th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
}

function renderExitBridge(result) {
  const ex = result && result.exit;
  if (!ex) return;
  renderPairs("exit-bridge-table", [
    ["Exit EBITDA", money(ex.exit_ebitda)],
    ["Exit Multiple", multiple(ex.exit_multiple)],
    ["Exit Enterprise Value", money(ex.exit_ev)],
    ["Less: Remaining Debt", money(ex.remaining_debt)],
    ["Plus: Ending Cash", money(ex.ending_cash_balance || 0)],
    ["Exit Equity Value", money(ex.exit_equity_value)],
  ]);
}

function dirBadge(direction) {
  const map = {
    positive: { color: "#7fd58a", text: "正向" },
    negative: { color: "#ff6b6b", text: "拖累" },
    neutral: { color: "#8a93a0", text: "中性" },
  };
  const d = map[direction] || map.neutral;
  return `<span style="color:${d.color};font-weight:700;">${d.text}</span>`;
}

function signed(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  const n = Number(v);
  return (n >= 0 ? "+" : "") + n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function signedMultiple(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  const n = Number(v);
  return (n >= 0 ? "+" : "") + n.toFixed(4) + "x";
}

function renderAttribution(attribution) {
  const card = document.getElementById("attribution-card");
  const body = document.getElementById("attribution-body");
  if (!card || !body) return;
  if (!attribution || attribution.status !== "ok") {
    if (attribution && attribution.status === "unavailable") {
      const flags = (attribution.flags || []).map(f => f.message).join("；");
      body.innerHTML = `<div style="color:var(--text-muted);font-size:12px;">回报归因暂不可用：${flags || "LBO 未产生有效回报。"}</div>`;
      card.style.display = "block";
    } else {
      card.style.display = "none";
    }
    return;
  }
  const tie = attribution.tie_out || {};
  const rows = (attribution.components || []).map(c => `
    <tr>
      <td style="text-align:left;">${c.label_en || c.label_cn}</td>
      <td>${signed(c.value)}</td>
      <td>${signedMultiple(c.moic_contribution)}</td>
      <td>${dirBadge(c.direction)}</td>
      <td style="text-align:left;color:var(--text-muted);">${c.rationale_en || c.rationale_cn}</td>
    </tr>`).join("");
  let tieMsg;
  if (tie.directional_bridge_pass === false) {
    tieMsg = "该桥接存在较大 residual，请将其作为方向性拆解。";
  } else if (Math.abs(Number(tie.residual || 0)) <= Number(tie.tolerance_abs || 0)) {
    tieMsg = "Residual 接近 0，说明桥接与模型输出基本一致。";
  } else {
    tieMsg = "Residual 在可接受范围内，归因桥可作为方向性拆解。";
  }
  const extraFlags = (attribution.flags || [])
    .filter(f => f.code !== "ATTRIBUTION_RESIDUAL_LARGE")
    .map(f => f.message);
  const footnotes = [
    tieMsg,
    "Component MOIC contribution sums to MOIC - 1.0, not headline MOIC.",
    ...extraFlags,
  ];
  body.innerHTML = `
    <div class="lbo-table-scroll">
      <table class="data-table">
        <thead><tr>
          <th>贡献项</th><th>金额</th><th>MOIC 贡献</th><th>方向</th><th>说明</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="attribution-footnotes">${footnotes.map(t => `<div>${t}</div>`).join("")}</div>
  `;
  card.style.display = "block";
}

function fmtScenarioCell(value, format) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (value === null || value === undefined) return "—";
  if (typeof value !== "number") return String(value);
  if (format === "percent") return pct(value);
  if (format === "multiple") return multiple(value);
  if (format === "amount") return money(value);
  return String(value);
}

function updateScenarioActiveState() {
  const btn = document.getElementById("scenarios-btn");
  const hint = document.getElementById("scenario-export-hint");
  const active = !!currentScenarios;
  if (btn) {
    btn.textContent = active ? "Scenarios Active" : "Generate Scenarios";
    btn.classList.toggle("scenario-active-btn", active);
    btn.classList.toggle("btn-secondary", !active);
  }
  if (hint) hint.classList.toggle("is-active", active);
}

function renderScenarios(data) {
  const card = document.getElementById("scenario-card");
  const body = document.getElementById("scenario-body");
  if (!card || !body) return;
  if (!data || data.status === "error" || !data.comparison) {
    const msg = ((data && data.flags) || []).map(f => f.message).join("；") || "情景暂不可用。";
    body.innerHTML = `<div class="defaults-warning">Scenario generation unavailable / 情景生成不可用：${msg}</div>`;
    card.style.display = "block";
    return;
  }
  const rows = data.comparison.rows || [];
  const statuses = data.comparison.scenario_statuses || {};
  const headCells = SCENARIO_KEYS.map(k => {
    const unavailable = (statuses[k] || {}).status !== "ok";
    const badge = unavailable ? ' <span class="badge-unavail">Unavailable</span>' : "";
    return `<th class="${unavailable ? "scn-unavail" : ""}">${SCENARIO_COL_LABELS[k]}${badge}</th>`;
  }).join("");
  const bodyRows = rows.map(r => {
    const cells = SCENARIO_KEYS.map(k => {
      const unavailable = (statuses[k] || {}).status !== "ok";
      const display = unavailable ? "Unavailable" : fmtScenarioCell(r[k], r.format);
      return `<td class="${unavailable ? "scn-unavail" : ""}">${display}</td>`;
    }).join("");
    return `<tr><td style="text-align:left;">${r.metric}</td>${cells}</tr>`;
  }).join("");
  const reasons = SCENARIO_KEYS
    .filter(k => (statuses[k] || {}).status !== "ok")
    .map(k => `<div class="defaults-warning">${SCENARIO_COL_LABELS[k]} unavailable：${(statuses[k] || {}).reason || ""}</div>`)
    .join("");
  const disclosures = (data.disclosures_cn || data.disclosures || []).map(d => `<li>${d}</li>`).join("");
  const notes = data.notes || {};
  const sameTxn = notes.same_transaction_note_cn || "情景对比为同一交易敏感性：入口估值、初始债务和 Sponsor Equity 保持不变。";
  body.innerHTML = `
    <div class="scenario-sensitivity-note">${sameTxn}</div>
    <div class="lbo-table-scroll">
      <table class="data-table lbo-table">
        <thead><tr><th style="text-align:left;">Metric</th>${headCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
    ${reasons}
    <div class="defaults-subtitle" style="margin-top:8px;">Base / Upside / Downside 为确定性建模情景，同时调整经营表现、退出倍数和利率假设；不是预测、概率或交易建议。</div>
    <ul class="audit-list">${disclosures}</ul>
  `;
  card.style.display = "block";
}

async function generateScenarios() {
  const btn = document.getElementById("scenarios-btn");
  if (currentScenarios) {
    invalidateScenarios();
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const payload = { inputs: buildPayload() };
    if (currentSuitability) payload.base_suitability = currentSuitability;
    const res = await fetch(`${API}/api/modeling/lbo/scenarios`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    currentScenarios = (data && (data.status === "ok" || data.status === "warning")) ? data : null;
    renderScenarios(data);
    updateScenarioActiveState();
  } finally {
    if (btn) btn.disabled = false;
  }
}

function closeSensitivity() {
  const overlay = document.getElementById("sensitivity-overlay");
  if (overlay) overlay.style.display = "none";
  const body = document.getElementById("sensitivity-body");
  if (body && !currentSensitivity) body.innerHTML = "";
}

function renderSensitivityGrid(grid) {
  if (!grid) return "";
  const cols = grid.cols || [];
  const head = `<thead><tr><th>${grid.row_label || ""} \\ ${grid.col_label || ""}</th>${cols.map(c => `<th>${Number(c).toFixed(1)}x</th>`).join("")}</tr></thead>`;
  const body = (grid.rows || []).map((r, i) => {
    const cells = ((grid.cells || [])[i] || []).map(cell => {
      const unavailable = !cell || cell.status !== "ok";
      const value = unavailable ? "n/a" : pct(cell.irr);
      const cls = cell && cell.is_base ? "sensitivity-base" : (unavailable ? "scn-unavail" : "");
      const title = unavailable ? ` title="${escapeHtml(cell && cell.error_code || "unavailable")}"` : ` title="MOIC ${multiple(cell.moic)}"`;
      return `<td class="${cls}"${title}>${value}</td>`;
    }).join("");
    return `<tr><td>${Number(r).toFixed(1)}x</td>${cells}</tr>`;
  }).join("");
  return `<div class="sensitivity-grid-title">${grid.row_label || ""} x ${grid.col_label || ""}</div>
    <div class="lbo-table-scroll"><table class="data-table lbo-table">${head}<tbody>${body}</tbody></table></div>`;
}

function renderSensitivity(data) {
  const overlay = document.getElementById("sensitivity-overlay");
  const body = document.getElementById("sensitivity-body");
  if (!overlay || !body) return;
  if (!data || data.status !== "ok" || !data.grids) {
    const msg = ((data && data.flags) || []).map(f => f.message).join("; ") || "Sensitivity unavailable.";
    body.innerHTML = `<div class="defaults-warning">${escapeHtml(msg)}</div>`;
    overlay.style.display = "flex";
    return;
  }
  body.innerHTML = `
    ${renderSensitivityGrid(data.grids.entry_exit)}
    ${renderSensitivityGrid(data.grids.leverage_exit)}
    <div class="defaults-subtitle" style="margin-top:8px;">Tax shield uses cash interest x tax rate; no full tax schedule modeled.</div>
  `;
  overlay.style.display = "flex";
}

async function openSensitivity() {
  if (!currentResult || currentResult.status !== "ok") return;
  const btn = document.getElementById("sensitivity-btn");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/modeling/lbo/sensitivity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs: buildPayload() }),
    });
    const data = await res.json();
    currentSensitivity = data && data.status === "ok" ? data : null;
    renderSensitivity(data);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function updateExportState() {
  const card = document.getElementById("export-card");
  if (!card) return;
  const ready = currentResult && currentResult.status === "ok";
  card.classList.toggle("export-disabled", !ready);
  const btn = document.getElementById("excel-btn");
  if (btn) btn.disabled = !ready;
  const sensBtn = document.getElementById("sensitivity-btn");
  if (sensBtn) sensBtn.disabled = !ready;
}

function renderReturnContext(context) {
  const badge = document.getElementById("return-context-badge");
  if (!badge) return;
  // Up to 2 lightweight context badges (falls back to the single primary badge).
  const list = (context && context.badges && context.badges.length)
    ? context.badges
    : (context && context.status === "ok" && context.badge_cn
        ? [{ badge_cn: context.badge_cn, badge_en: context.badge_en }]
        : []);
  if (!context || context.status !== "ok" || !list.length) {
    badge.style.display = "none";
    badge.innerHTML = "";
    return;
  }
  badge.innerHTML = list.map(b =>
    `<div class="return-context-line">${b.badge_cn}<br><span style="opacity:0.75;">${b.badge_en}</span></div>`
  ).join("");
  badge.style.display = "block";
}

// Lightweight debt-service stress hint: shown when any forecast year cannot
// cover interest + mandatory amortization. Context only -- no fail / bad-deal /
// recommendation wording.
function renderDebtStressHint(result) {
  const hint = document.getElementById("debt-stress-hint");
  if (!hint) return;
  const schedule = (result && result.debt_schedule) || [];
  const stressed = schedule.some(row => row && row.debt_service_failure);
  if (!stressed) {
    hint.style.display = "none";
    hint.innerHTML = "";
    return;
  }
  hint.innerHTML = "债务服务压力：经营现金流不足以覆盖利息和强制摊还。<br>"
    + "<span style=\"opacity:0.75;\">Debt service stress: cash before debt service is below interest plus mandatory amortization.</span>";
  hint.style.display = "block";
}

function renderResult(result) {
  currentResult = result;
  if (!result || result.status !== "ok") {
    showError(result);
    renderAttribution(result && result.attribution);
    renderReturnContext(result && result.return_context);
    renderDebtStressHint(null);
    updateExportState();
    return;
  }
  clearError();
  renderAttribution(result.attribution);
  renderReturnContext(result.return_context);
  renderDebtStressHint(result);
  const r = result.returns;
  const headlines = [
    ["IRR", pct(r.irr)],
    ["MOIC", multiple(r.moic)],
    ["Sponsor Equity", money(r.sponsor_equity)],
    ["Entry EV", money(r.entry_ev)],
    ["Exit Equity Value", money(r.exit_equity_value)],
    ["Debt Paydown", money(r.debt_paydown)],
    ["Remaining Debt", money(r.remaining_debt)],
  ];
  document.getElementById("headline-grid").innerHTML = headlines.map(([label, value]) => `<div class="headline"><div class="headline-label">${label}</div><div class="headline-value">${value}</div></div>`).join("");
  const t = result.transaction_summary;
  const debtLabel = result.capital_structure_summary ? "Total Opening Debt" : "Debt Amount";
  renderPairs("transaction-table", [
    ["Entry EBITDA", money(t.entry_ebitda)],
    ["Entry Multiple", multiple(t.entry_multiple)],
    ["Entry EV", money(t.entry_ev)],
    ["Transaction Fees", money(t.transaction_fees)],
    ["Total Uses", money(t.total_uses)],
    [debtLabel, money(t.debt_amount)],
    ["Implied Leverage", t.implied_leverage === null || t.implied_leverage === undefined ? "n/a" : multiple(t.implied_leverage)],
    ["Sponsor Equity", money(t.sponsor_equity)],
    ["Exit Multiple", multiple(t.exit_multiple)],
    ["Exit Year", t.exit_year],
  ]);
  renderForecast(result);
  renderCapStructure(result);
  renderDebt(result);
  renderExitBridge(result);
  renderCovenants(result);
  renderMaturity(result);
  if (!result.capital_structure_summary) hideMultiCards();
  renderPairs("returns-table", [
    ["IRR", pct(r.irr)],
    ["MOIC", multiple(r.moic)],
    ["Sponsor Equity", money(r.sponsor_equity)],
    ["Exit Equity Value", money(r.exit_equity_value)],
    ["Debt Paydown", money(r.debt_paydown)],
    ["Remaining Debt", money(r.remaining_debt)],
  ]);
  document.getElementById("audit-list").innerHTML = ((result.audit && result.audit.disclosures) || []).map(x => `<li>${x}</li>`).join("");
  updateExportState();
}

function renderDefaultsPanel(data, overridden = false) {
  const panel = document.getElementById("defaults-panel");
  if (!panel) return;
  const provenance = data.provenance || {};
  const serviceability = data.serviceability || {};
  const flags = data.flags || [];
  const p = (key) => provenance[key] && provenance[key].rationale_cn;
  const rationale = [
    ["买入倍数", p("entry_multiple") || "来自当前 EV/EBITDA 或占位默认值。"],
    ["退出倍数", p("exit_multiple") || "默认等于买入倍数，避免依赖倍数扩张。"],
    ["杠杆倍数", p("leverage_multiple") || "根据 DSCR 偿债覆盖校验后确定。"],
    ["利率", p("interest_rate") || "V4.1 暂用可修改的市场惯例占位值。"],
    ["现金扫款", p("cash_sweep_pct") || "100% sweep，V4.1 不做现金余额桥。"],
  ];
  let notice = "";
  if (serviceability.haircut_applied && serviceability.debt_service_pass) {
    notice = `<div class="defaults-warning">候选杠杆已从 ${multiple(serviceability.initial_candidate_leverage)} 下调至 ${multiple(serviceability.final_leverage)}，因为更高杠杆未通过 DSCR 偿债覆盖校验。</div>`;
  } else if (serviceability.debt_service_pass === false) {
    notice = `<div class="defaults-warning">即使降至 1.0x 默认杠杆，该标的仍未通过 V4.1 简化偿债能力校验。完整 LBO suitability 判断将在后续版本处理。</div>`;
  }
  const flagHtml = flags.length ? `<div class="defaults-flags">${flags.map(f => `${f.code}: ${f.message}`).join("<br>")}</div>` : "";
  const overrideNote = overridden
    ? `<div class="defaults-warning">你已修改部分假设；下方来源说明对应系统默认结构，不代表所有手动修改后的输入。</div>`
    : "";
  panel.innerHTML = `
    <div class="defaults-title">默认结构来源说明 / Default Structure Provenance</div>
    <div class="defaults-subtitle">这是一套可修改的建模起点，不代表交易建议。</div>
    <ul>${rationale.map(([label, text]) => `<li><strong>${label}：</strong>${text}</li>`).join("")}</ul>
    ${overrideNote}
    ${notice}
    ${flagHtml}
  `;
  panel.style.display = "block";
}

function markDefaultsOverridden() {
  if (!currentDefaultBuilder || defaultsOverridden || !currentDefaultsPanelData) return;
  defaultsOverridden = true;
  renderDefaultsPanel(currentDefaultsPanelData, true);
}

function invalidateScenarios() {
  currentScenarios = null;
  const card = document.getElementById("scenario-card");
  if (card) card.style.display = "none";
  const body = document.getElementById("scenario-body");
  if (body) body.innerHTML = "";
  updateScenarioActiveState();
}

function invalidateSensitivity() {
  currentSensitivity = null;
  closeSensitivity();
}

async function runLbo() {
  invalidateScenarios();
  invalidateSensitivity();
  const res = await fetch(`${API}/api/modeling/lbo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildPayload()),
  });
  const data = await res.json();
  renderResult(data);
  return data;
}

function renderSuitabilityPanel(suitability) {
  const panel = document.getElementById("suitability-panel");
  if (!panel) return;
  if (!suitability || !suitability.suitability) {
    panel.style.display = "none";
    return;
  }
  const palette = {
    suitable: { color: "#7fd58a", header: "LBO 框架适配度：较适合" },
    borderline: { color: "#ffcc66", header: "LBO 框架适配度：边缘 / 需复核" },
    unsuitable: { color: "#ff6b6b", header: "LBO 框架适配度：不适合 / 仅作机械建模参考" },
  };
  const tone = palette[suitability.suitability] || palette.unsuitable;
  const veto = (suitability.veto_reasons || []).map(r => `<li><strong>${r.code}</strong> — ${r.message_cn}</li>`).join("");
  const penalty = (suitability.penalty_reasons || []).map(r => `<li><strong>${r.code}</strong> — ${r.message_cn}</li>`).join("");
  const positive = (suitability.positive_factors || []).map(r => `<li><strong>${r.code}</strong> — ${r.message_cn}</li>`).join("");
  const vetoBlock = suitability.veto_triggered
    ? `<div class="defaults-warning">该标的触发 LBO 框架适配否决项；当前模型仍可运行，但输出只能作为机械建模结果，不代表真实交易可行性。</div>`
    : "";
  const next = suitability.recommended_next_view
    ? `<div class="defaults-subtitle">Next modeling view: ${suitability.recommended_next_view}</div>`
    : "";
  const score = (suitability.score === null || suitability.score === undefined)
    ? "" : ` · Score ${suitability.score}`;
  panel.innerHTML = `
    <div class="defaults-title" style="color:${tone.color};">${tone.header}${score}</div>
    <div class="defaults-subtitle">${suitability.summary_cn || ""}</div>
    ${vetoBlock}
    ${veto ? `<div class="defaults-title" style="margin-top:8px;">否决项</div><ul>${veto}</ul>` : ""}
    ${penalty ? `<div class="defaults-title" style="margin-top:8px;">扣分项</div><ul>${penalty}</ul>` : ""}
    ${positive ? `<div class="defaults-title" style="margin-top:8px;">正向因素</div><ul>${positive}</ul>` : ""}
    ${next}
    <div class="defaults-subtitle" style="margin-top:8px;">${suitability.modeling_guidance_cn || ""}</div>
    <div class="defaults-flags">${suitability.disclosure_cn || ""}</div>
  `;
  panel.style.display = "block";
}

async function loadDefaults() {
  const symbol = document.getElementById("symbol").value || "SYNTH";
  const res = await fetch(`${API}/api/modeling/lbo/defaults?symbol=${encodeURIComponent(symbol)}`);
  const data = await res.json();
  if (data.status === "error") return showError(data);
  const d = data.defaults;
  currentSuitability = data.suitability || (d && d.suitability) || null;
  renderSuitabilityPanel(currentSuitability);
  currentDefaultBuilder = d.default_builder || {
    status: data.status,
    provenance: data.provenance,
    serviceability: data.serviceability,
    flags: data.flags || [],
  };
  currentDefaultsPanelData = data;
  defaultsOverridden = false;
  document.getElementById("symbol").value = d.symbol || symbol;
  document.getElementById("currency").value = normalizeCurrency(d.currency);
  document.getElementById("entry_ebitda").value = d.transaction.entry_ebitda;
  document.getElementById("entry_multiple").value = d.transaction.entry_multiple;
  document.getElementById("exit_multiple").value = d.transaction.exit_multiple;
  document.getElementById("exit_year").value = d.transaction.exit_year;
  document.getElementById("fees_pct").value = d.transaction.transaction_fees_pct_ev * 100;
  // Defaults size debt from leverage; use By Leverage Multiple so Debt Amount
  // tracks Entry EBITDA automatically.
  document.getElementById("debt_sizing").value = "leverage";
  document.getElementById("leverage_multiple").value = d.debt.leverage_multiple || 5.0;
  document.getElementById("interest_rate").value = d.debt.interest_rate * 100;
  document.getElementById("mandatory_amortization_pct").value = d.debt.mandatory_amortization_pct * 100;
  document.getElementById("cash_sweep_pct").value = d.debt.cash_sweep_pct * 100;
  document.getElementById("cash_to_balance_sheet").value = d.debt.cash_to_balance_sheet;
  document.getElementById("tax_rate").value = d.tax_rate === undefined ? 25.0 : Number(d.tax_rate || 0) * 100;
  document.getElementById("tax_shield_enabled").value = d.tax_shield_enabled === false ? "disabled" : "enabled";
  // Derive Growth Forecast drivers from the default Y1 levels. Defaults arrive
  // flat, so growth defaults to a non-zero modeling start (not a forecast).
  const of = d.operating_forecast;
  const rev1 = Number(of.revenue[0]) || 0;
  const ebitda1 = Number(of.ebitda[0]) || 0;
  document.getElementById("rev_y1").value = rev1;
  document.getElementById("rev_growth").value = 5.0;
  document.getElementById("ebitda_margin").value = rev1 > 0 ? +(ebitda1 / rev1 * 100).toFixed(2) : 20.0;
  document.getElementById("tax_pct_ebitda").value = ebitda1 > 0 ? +(Number(of.cash_taxes[0]) / ebitda1 * 100).toFixed(2) : 10.0;
  document.getElementById("capex_pct_rev").value = rev1 > 0 ? +(Number(of.capex[0]) / rev1 * 100).toFixed(2) : 3.0;
  document.getElementById("nwc_pct_rev").value = rev1 > 0 ? +(Number(of.change_in_nwc[0]) / rev1 * 100).toFixed(2) : 0.4;
  // Loading defaults returns to the Growth path.
  forecastMode = "growth";
  updateForecastModeIndicator();
  renderDefaultsPanel(data, false);
  updateUnitLabels();
  syncDebtSizing();
  await runLbo();
}

// Parse the server-provided download name from a Content-Disposition header so
// the saved file matches what the API names it (V4.1.0 formula-native workbook
// uses LBO_{sym}_{mode}_formula_{date}.xlsx). Returns null if unparseable.
function filenameFromContentDisposition(res) {
  const cd = res.headers.get("Content-Disposition") || "";
  // Prefer RFC 5987 filename*=UTF-8''... then plain filename="...".
  let m = cd.match(/filename\*=(?:UTF-8'')?["']?([^;"']+)["']?/i);
  if (m && m[1]) {
    try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
  }
  m = cd.match(/filename=["']?([^;"']+)["']?/i);
  if (m && m[1]) return m[1];
  return null;
}

async function exportExcel() {
  if (!currentResult || currentResult.status !== "ok") return;
  const payload = buildPayload();
  if (currentScenarios) payload.scenarios = currentScenarios;
  if (currentSensitivity) payload.sensitivity = currentSensitivity;
  const res = await fetch(`${API}/api/modeling/lbo/excel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const type = res.headers.get("Content-Type") || "";
  if (type.includes("application/json")) {
    renderResult(await res.json());
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const mode = (currentResult.capital_structure_summary || {}).mode === "multi_tranche" ? "multi" : "single";
  const today = new Date().toISOString().slice(0, 10);
  const sym = (payload.symbol || "SYNTH").replace(/\./g, "_");
  // Prefer the server filename (carries the `formula` marker); fall back to a
  // locally built name that also includes `formula`.
  a.download = filenameFromContentDisposition(res) || `LBO_${sym}_${mode}_formula_${today}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const symbol = params.get("symbol");
  if (symbol) document.getElementById("symbol").value = symbol.toUpperCase();
  document.getElementById("run-btn").addEventListener("click", runLbo);
  document.getElementById("defaults-btn").addEventListener("click", loadDefaults);
  document.getElementById("excel-btn").addEventListener("click", exportExcel);
  const scnBtn = document.getElementById("scenarios-btn");
  if (scnBtn) scnBtn.addEventListener("click", generateScenarios);
  const sensitivityBtn = document.getElementById("sensitivity-btn");
  if (sensitivityBtn) sensitivityBtn.addEventListener("click", openSensitivity);
  const sensitivityClose = document.getElementById("sensitivity-close");
  if (sensitivityClose) sensitivityClose.addEventListener("click", closeSensitivity);
  const sensitivityOverlay = document.getElementById("sensitivity-overlay");
  if (sensitivityOverlay) sensitivityOverlay.addEventListener("click", (e) => { if (e.target === sensitivityOverlay) closeSensitivity(); });
  const saveCaseBtn = document.getElementById("save-case-btn");
  if (saveCaseBtn) saveCaseBtn.addEventListener("click", openSaveCaseModal);
  const saveClose = document.getElementById("case-save-close");
  if (saveClose) saveClose.addEventListener("click", closeSaveCaseModal);
  const saveCancel = document.getElementById("case-save-cancel");
  if (saveCancel) saveCancel.addEventListener("click", closeSaveCaseModal);
  const saveConfirm = document.getElementById("case-save-confirm");
  if (saveConfirm) saveConfirm.addEventListener("click", saveCurrentCase);
  const saveOverlay = document.getElementById("case-save-overlay");
  if (saveOverlay) saveOverlay.addEventListener("click", (e) => { if (e.target === saveOverlay) closeSaveCaseModal(); });
  const switchCaseBtn = document.getElementById("switch-case-btn");
  if (switchCaseBtn) switchCaseBtn.addEventListener("click", openCaseSwitcher);
  const switchClose = document.getElementById("case-switcher-close");
  if (switchClose) switchClose.addEventListener("click", closeCaseSwitcher);
  const switchOverlay = document.getElementById("case-switcher-overlay");
  if (switchOverlay) switchOverlay.addEventListener("click", (e) => { if (e.target === switchOverlay) closeCaseSwitcher(); });
  updateExportState();
  renderTrancheEditor();
  const debtMode = document.getElementById("debt_mode");
  if (debtMode) {
    debtMode.addEventListener("change", () => {
      document.getElementById("multi-tranche-inputs").style.display = isMultiMode() ? "block" : "none";
      syncDebtSizing();
      invalidateSensitivity();
      runLbo();
    });
  }
  const currencySel = document.getElementById("currency");
  if (currencySel) {
    currencySel.addEventListener("change", updateUnitLabels);
    currencySel.addEventListener("change", invalidateScenarios);
    currencySel.addEventListener("change", invalidateSensitivity);
  }
  // Manual forecast overlay wiring.
  const mfBtn = document.getElementById("manual-forecast-btn");
  if (mfBtn) mfBtn.addEventListener("click", openManualForecast);
  const mfClose = document.getElementById("manual-forecast-close");
  if (mfClose) mfClose.addEventListener("click", closeManualForecast);
  const mfCancel = document.getElementById("manual-forecast-cancel");
  if (mfCancel) mfCancel.addEventListener("click", closeManualForecast);
  const mfSave = document.getElementById("manual-forecast-save");
  if (mfSave) mfSave.addEventListener("click", saveManualForecast);
  const resetBtn = document.getElementById("reset-growth-btn");
  if (resetBtn) resetBtn.addEventListener("click", resetToGrowth);
  const overlay = document.getElementById("manual-forecast-overlay");
  if (overlay) overlay.addEventListener("click", (e) => { if (e.target === overlay) closeManualForecast(); });
  const debtSizingSel = document.getElementById("debt_sizing");
  if (debtSizingSel) {
    debtSizingSel.addEventListener("change", () => {
      syncDebtSizing();
      markDefaultsOverridden();
      invalidateScenarios();
      invalidateSensitivity();
      runLbo();
    });
  }
  document.querySelectorAll(".lbo-input").forEach(el => {
    el.addEventListener("input", () => {
      markDefaultsOverridden();
      invalidateScenarios();
      invalidateSensitivity();
      syncDebtSizing();
    });
    el.addEventListener("change", () => {
      markDefaultsOverridden();
      runLbo();
    });
  });
  updateUnitLabels();
  syncDebtSizing();
  updateForecastModeIndicator();
  updateScenarioActiveState();
  const hasSavedCases = renderCaseListPanel();
  if (!hasSavedCases) runLbo();
});
