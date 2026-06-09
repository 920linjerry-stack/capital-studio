// thesis_card.js - compressed thesis card for the DCF page.
(function () {
  "use strict";

  const Shared = window.ThesisShared;

  let _ticker = "";
  let _ontology = null;
  let _thesis = null;

  function $(id) {
    return document.getElementById(id);
  }

  function _normalizeThesis(raw) {
    const thesis = raw && typeof raw === "object" ? raw : {};
    return {
      ticker          : thesis.ticker || _ticker,
      company_name    : typeof thesis.company_name === "string" ? thesis.company_name : _ticker,
      core_thesis     : typeof thesis.core_thesis === "string" ? thesis.core_thesis : "",
      thesis_notes    : typeof thesis.thesis_notes === "string" ? thesis.thesis_notes : "",
      drivers_selected: Array.isArray(thesis.drivers_selected) ? thesis.drivers_selected.slice() : [],
      schema_version  : thesis.schema_version || "v334",
      last_modified   : thesis.last_modified || null,
    };
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
      return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
    } catch (e) {
      return "未保存";
    }
  }

  async function _loadData() {
    try {
      const [ontology, thesis] = await Promise.all([
        Shared.fetchOntology(),
        Shared.fetchThesis(_ticker),
      ]);
      _ontology = ontology;
      _thesis = _normalizeThesis(thesis);
    } catch (err) {
      console.warn("[thesis-card] load failed:", err);
      _ontology = null;
      _thesis = _normalizeThesis(null);
    }
  }

  function _render() {
    const card = $("thesis-card");
    if (!card) return;

    const editBtn = $("thesis-card-edit-btn");
    const titleEl = card.querySelector(".thesis-card-header .card-title");
    if (titleEl) {
      titleEl.innerHTML =
        "估值情景设置 / Valuation Scenarios" +
        '<div style="font-size:11px;font-weight:400;color:var(--text-muted);letter-spacing:0;text-transform:none;margin-top:4px;">用投资逻辑生成乐观 / 悲观 DCF 预览</div>';
    }

    const href = _ticker
      ? `/modeling/case?symbol=${encodeURIComponent(_ticker)}`
      : "/modeling/case";
    if (editBtn) {
      editBtn.href = href;
      editBtn.textContent = "设置情景 / 预览估值影响";
    }

    const tickerEl = $("thesis-card-ticker");
    if (tickerEl) tickerEl.textContent = _ticker || "--";

    const timeEl = $("thesis-card-last-modified");
    if (timeEl) timeEl.textContent = _formatLastModified(_thesis ? _thesis.last_modified : null);

    _renderNotes(href);
    _renderDrivers();
    _renderAffects();
  }

  function _renderNotes(href) {
    const notesEl = $("thesis-card-notes-preview");
    if (!notesEl) return;

    const core = (_thesis && _thesis.core_thesis ? _thesis.core_thesis.trim() : "");
    const fallbackNotes = (_thesis && _thesis.thesis_notes ? _thesis.thesis_notes.trim() : "");
    const notes = core || fallbackNotes;
    if (!notes) {
      notesEl.title = "";
      notesEl.innerHTML =
        `<span class="thesis-card-notes-empty">还没写 thesis</span> ` +
        `<a class="btn btn-primary" href="${_escapeAttr(href)}">开始写</a>`;
      return;
    }

    notesEl.title = notes;
    notesEl.textContent = notes;
  }

  function _renderDrivers() {
    const driversEl = $("thesis-card-drivers");
    if (!driversEl) return;

    const selectedIds = _getSelectedIds();
    if (!_ontology || selectedIds.length === 0) {
      driversEl.innerHTML = "";
      return;
    }

    const names = selectedIds
      .map(id => _getDriverZh(id))
      .filter(Boolean);
    const preview = names.length > 5
      ? `${names.slice(0, 5).join("、")}等 ${names.length} 个`
      : names.join("、");

    driversEl.innerHTML =
      `<span class="thesis-card-drivers-label">已选(${selectedIds.length}):</span>` +
      `<span>${_escapeHtml(preview)}</span>`;
  }

  function _renderAffects() {
    const affectsEl = $("thesis-card-affects");
    if (!affectsEl) return;

    const selectedIds = _getSelectedIds();
    if (!_ontology || selectedIds.length === 0) {
      affectsEl.innerHTML = "";
      return;
    }

    const selectedAffects = new Set();
    selectedIds.forEach(id => {
      const meta = _ontology[id] || {};
      const affects = Array.isArray(meta.affects) ? meta.affects : [];
      affects.forEach(key => selectedAffects.add(key));
    });

    const labels = Object.keys(Shared.AFFECTS_LABELS)
      .filter(key => selectedAffects.has(key))
      .map(key => Shared.AFFECTS_LABELS[key]);

    if (labels.length === 0) {
      affectsEl.innerHTML = "";
      return;
    }

    affectsEl.innerHTML =
      '<span class="thesis-card-affects-label">主要涉及:</span>' +
      `<span>${_escapeHtml(labels.join("、"))}</span>`;
  }

  function _getSelectedIds() {
    return (_thesis && Array.isArray(_thesis.drivers_selected))
      ? _thesis.drivers_selected
      : [];
  }

  function _getDriverZh(id) {
    const meta = _ontology && _ontology[id] ? _ontology[id] : {};
    return meta.display_name_zh || meta.display_name || id;
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

  async function _init() {
    if (!Shared) {
      console.warn("[thesis-card] ThesisShared is missing");
      return;
    }

    _ticker = Shared.getTickerFromURL();
    if (!_ticker) {
      const card = $("thesis-card");
      if (card) card.style.display = "none";
      return;
    }

    await _loadData();
    _render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _init);
  } else {
    _init();
  }
})();
