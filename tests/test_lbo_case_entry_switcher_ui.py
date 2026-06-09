"""V4.7.4 LBO case launcher / switcher UX tests.

Static UI/JS contract coverage only. This hotfix does not change LBO engine,
scenario math, Excel workbook architecture, or API contracts.
"""

from pathlib import Path


STATIC = Path(__file__).resolve().parent.parent / "static" / "modeling"
HTML = (STATIC / "lbo.html").read_text(encoding="utf-8")
JS = (STATIC / "js" / "lbo.js").read_text(encoding="utf-8")


def test_case_launcher_ui_exists_for_saved_cases():
    assert 'id="case-list-panel"' in HTML
    assert "function renderCaseListPanel" in JS
    assert "case-launcher-card" in HTML
    assert "选择 LBO Case / Select LBO Case" in JS
    assert "Open a saved case or start from a blank case." in JS
    assert "打开已保存的 case，或从空白模型开始搭建。" in JS


def test_launcher_includes_blank_case_option():
    assert 'id="${blankId}"' in JS
    assert "Blank Case / 空白搭建" in JS
    assert 'const blankId = target === "switcher" ? "switch-blank-case-btn" : "blank-case-btn"' in JS


def test_launcher_saved_case_row_includes_metadata():
    assert "case-list-name" in JS
    assert "case-list-meta" in JS
    assert 'const symbol = payload.symbol || "SYNTH"' in JS
    assert 'const currency = payload.currency || "USD"' in JS
    assert "formatCaseDate(c.updated_at)" in JS
    assert "forecast" in JS
    assert "capital_structure_mode" in JS


def test_open_saved_case_auto_runs_existing_run_lbo_path():
    block = JS.split("async function openSavedCase", 1)[1].split("function deleteSavedCase", 1)[0]
    assert "applyCaseRecord(record);" in block
    assert "const result = await runLbo();" in block
    assert "Case loaded and refreshed." in block
    assert "fetch(`${API}/api/modeling/lbo`" not in block


def test_open_saved_case_clears_scenarios_inactive():
    apply_block = JS.split("function applyCaseRecord", 1)[1].split("function extractManualForecast", 1)[0]
    assert "invalidateScenarios();" in apply_block
    run_block = JS.split("async function runLbo", 1)[1].split("function renderSuitabilityPanel", 1)[0]
    assert "invalidateScenarios();" in run_block


def test_open_saved_case_enables_export_after_successful_run():
    assert "function updateExportState" in JS
    assert "renderResult(data);" in JS
    assert "return data;" in JS
    assert "updateExportState();" in JS


def test_no_saved_cases_launcher_does_not_block_default_page():
    block = JS.rsplit("function renderCaseListPanel", 1)[1].split("function hideCaseLauncher", 1)[0]
    assert "if (!cases.length && !forceShow)" in block
    assert "return false;" in block
    dom_block = JS.split("document.addEventListener(\"DOMContentLoaded\"", 1)[1]
    assert "const hasSavedCases = renderCaseListPanel();" in dom_block
    assert "if (!hasSavedCases) runLbo();" in dom_block


def test_switch_case_button_exists_in_workspace():
    assert 'id="switch-case-btn"' in HTML
    assert "Switch Case" in HTML
    assert 'switchCaseBtn.addEventListener("click", openCaseSwitcher)' in JS


def test_switch_case_opens_overlay():
    assert 'id="case-switcher-overlay"' in HTML
    assert 'id="case-switcher-body"' in HTML
    assert "function openCaseSwitcher" in JS
    block = JS.split("function openCaseSwitcher", 1)[1].split("function closeCaseSwitcher", 1)[0]
    assert 'caseChooserHtml(readSavedCasesStore().cases, "switcher")' in block
    assert 'overlay.style.display = "flex"' in block


def test_switcher_can_open_another_case_and_auto_run():
    assert 'data-case-target="${target}"' in JS
    assert 'openSavedCase(btn.dataset.caseId, btn.dataset.caseTarget || "launcher")' in JS
    block = JS.split("async function openSavedCase", 1)[1].split("function deleteSavedCase", 1)[0]
    assert "closeCaseChoosers();" in block
    assert "await runLbo();" in block


def test_switcher_blank_case_resets_and_clears_results_scenarios():
    assert "function resetBlankCaseInputs" in JS
    block = JS.rsplit("function startBlankCase", 1)[1].split("function buildPayload", 1)[0]
    assert "resetBlankCaseInputs();" in block
    assert "invalidateScenarios();" in block
    assert "clearResultOutputsForLoadedCase();" in block
    assert "runLbo()" not in block


def test_switcher_close_without_changing_current_case():
    assert 'id="case-switcher-close"' in HTML
    close_block = JS.split("function closeCaseSwitcher", 1)[1].split("function refreshVisibleCaseChoosers", 1)[0]
    assert 'overlay.style.display = "none"' in close_block
    assert "activeCaseId" not in close_block
    assert "applyCaseRecord" not in close_block


def test_delete_saved_case_removes_from_localstorage():
    block = JS.rsplit("function deleteSavedCase", 1)[1].split("function resetBlankCaseInputs", 1)[0]
    assert "store.cases.filter" in block
    assert "writeSavedCasesStore({ cases: next })" in block
    assert "if (activeCaseId === id) activeCaseId = null;" in block


def test_save_case_still_does_not_persist_transient_outputs():
    record_block = JS.split("function buildCaseRecord", 1)[1].split("function openSaveCaseModal", 1)[0]
    assert "delete payload.scenarios;" in record_block
    assert "delete payload.default_builder;" in record_block
    assert "delete payload.suitability;" in record_block
    assert "currentResult" not in record_block
    assert "workbook" not in record_block.lower()


def test_no_engine_math_api_changes_in_ui_hotfix_contract():
    assert "run_lbo(" not in HTML
    assert "run_lbo(" not in JS
    assert "/api/modeling/lbo/scenarios" in JS
    assert "/api/modeling/lbo/excel" in JS
    assert "/api/modeling/lbo`" in JS
