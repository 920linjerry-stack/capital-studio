"""V4.7.2 LBO case persistence / scenario active-state UX tests.

These are static UI/JS contract checks for the hotfix layer only. They do not
exercise or change run_lbo, waterfall, covenant, attribution, scenario math, or
Excel workbook architecture.
"""

from pathlib import Path


STATIC = Path(__file__).resolve().parent.parent / "static" / "modeling"
HTML = (STATIC / "lbo.html").read_text(encoding="utf-8")
JS = (STATIC / "js" / "lbo.js").read_text(encoding="utf-8")


def test_generate_scenarios_default_button_is_inactive():
    assert '<button class="btn btn-secondary" id="scenarios-btn">Generate Scenarios</button>' in HTML
    assert "scenario-export-active-hint" in HTML
    assert 'id="scenario-export-hint"' in HTML
    assert 'classList.toggle("scenario-active-btn", active)' in JS


def test_successful_scenario_generation_sets_active_state():
    assert "function updateScenarioActiveState" in JS
    assert 'btn.textContent = active ? "Scenarios Active" : "Generate Scenarios"' in JS
    assert "scenario-active-btn" in HTML
    assert "currentScenarios = (data && (data.status === \"ok\" || data.status === \"warning\")) ? data : null" in JS
    assert "updateScenarioActiveState();" in JS


def test_active_scenario_export_hint_exists():
    assert "Scenario Summary will be included in Excel export." in HTML
    assert 'id="scenario-export-hint"' in HTML
    assert 'hint.classList.toggle("is-active", active)' in JS


def test_clicking_active_scenario_button_clears_without_rerun():
    block = JS.split("async function generateScenarios()", 1)[1].split("if (btn) btn.disabled = true", 1)[0]
    assert "if (currentScenarios)" in block
    assert "invalidateScenarios();" in block
    assert "return;" in block
    assert "runLbo()" not in block


def test_cleared_scenarios_are_not_sent_to_excel_payload():
    assert "function invalidateScenarios" in JS
    assert "currentScenarios = null;" in JS
    assert "if (currentScenarios) payload.scenarios = currentScenarios;" in JS


def test_editing_inputs_invalidates_active_scenarios():
    assert 'el.addEventListener("input", () => {' in JS
    assert "invalidateScenarios();" in JS
    assert 'currencySel.addEventListener("change", invalidateScenarios)' in JS
    assert 'debtSizingSel.addEventListener("change", () => {' in JS


def test_save_case_card_exists_above_export_card():
    assert 'id="save-case-card"' in HTML
    assert "保存当前 Case / Save Case" in HTML
    assert "Save Current Case" in HTML
    assert HTML.index('id="save-case-card"') < HTML.index('id="export-card"')


def test_save_modal_has_case_name_input():
    assert 'id="case-save-overlay"' in HTML
    assert "Case Name" in HTML
    assert 'id="case-name-input"' in HTML
    assert 'id="case-save-confirm"' in HTML


def test_saving_stores_payload_in_localstorage_key():
    assert 'const SAVED_CASES_KEY = "lbo_saved_cases_v1"' in JS
    assert "window.localStorage.setItem(SAVED_CASES_KEY" in JS
    assert "const payload = buildPayload();" in JS


def test_saved_case_includes_payload_and_ui_state():
    assert "function buildCaseRecord" in JS
    assert "payload," in JS
    assert "ui_state: buildCaseUiState()" in JS
    assert "function buildCaseUiState" in JS
    assert "forecast_mode" in JS
    assert "debt_sizing_mode" in JS
    assert "capital_structure_mode" in JS
    assert "growth_drivers" in JS
    assert "manual_forecast" in JS


def test_saved_case_does_not_include_generated_scenario_output():
    assert "delete payload.scenarios;" in JS
    assert "delete payload.default_builder;" in JS
    assert "delete payload.suitability;" in JS


def test_loading_case_restores_inputs_and_ui_state():
    assert "function applyCaseRecord" in JS
    for field in [
        'setValue("symbol"',
        'setValue("currency"',
        'setValue("entry_ebitda"',
        'setValue("debt_sizing"',
        'applyGrowthDrivers(ui.growth_drivers)',
        "applyCapitalStructure(payload.capital_structure || null)",
    ]:
        assert field in JS


def test_loading_case_makes_scenarios_inactive():
    block = JS.split("function applyCaseRecord", 1)[1].split("function extractManualForecast", 1)[0]
    assert "invalidateScenarios();" in block
    assert "clearResultOutputsForLoadedCase();" in block


def test_loading_case_shows_refresh_hint():
    assert "Case loaded and refreshed." in JS


def test_case_list_appears_when_saved_cases_exist():
    assert 'id="case-list-panel"' in HTML
    assert "function renderCaseListPanel" in JS
    assert "panel.style.display = \"flex\"" in JS
    assert "Select LBO Case" in JS


def test_blank_case_option_exists():
    assert "Blank Case / 空白搭建" in JS
    assert "function startBlankCase" in JS


def test_delete_saved_case_removes_from_localstorage():
    assert "function deleteSavedCase" in JS
    block = JS.split("function deleteSavedCase", 1)[1].split("function startBlankCase", 1)[0]
    assert "store.cases.filter" in block
    assert "writeSavedCasesStore({ cases: next })" in block


def test_duplicate_names_trigger_overwrite_confirmation():
    assert "A case with this name exists. Overwrite?" in JS
    assert "window.confirm" in JS


def test_load_case_auto_run_is_handled_by_open_saved_case_not_apply_case_record():
    block = JS.split("function applyCaseRecord", 1)[1].split("function extractManualForecast", 1)[0]
    assert "runLbo()" not in block
    open_block = JS.split("async function openSavedCase", 1)[1].split("function deleteSavedCase", 1)[0]
    assert "applyCaseRecord(record);" in open_block
    assert "await runLbo();" in open_block


def test_no_engine_api_math_files_are_touched_by_this_test_contract():
    assert "run_lbo(" not in HTML
    assert "run_lbo(" not in JS
    assert "/api/modeling/lbo/scenarios" in JS
    assert "/api/modeling/lbo/excel" in JS
