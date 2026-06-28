"""PEAD readiness scaffold -- medium-horizon drift, no imputation, no trade signal."""

from modeling.v6 import pead


def test_dataset_has_labels_and_matured_flags():
    ds = pead.build_pead_dataset()
    assert ds["windows"] == pead.ALL_WINDOWS
    if not ds["rows"]:
        return
    r = ds["rows"][0]
    assert set(r["labels_residual"]) == set(pead.ALL_WINDOWS)
    assert set(r["matured"]) == set(pead.ALL_WINDOWS)
    # matured flag must agree with label presence (never imputed)
    for w in pead.ALL_WINDOWS:
        assert r["matured"][w] == (r["labels_residual"][w] is not None)


def test_dataset_is_time_sorted():
    rows = pead.build_pead_dataset()["rows"]
    assert [x["event_time"] for x in rows] == sorted(x["event_time"] for x in rows)


def test_scorecard_windows_valid_or_insufficient():
    card = pead.pead_scorecard()
    for w in ("5", "20", "40", "60"):
        c = card["windows"][w]
        if c["status"] == "ok":
            assert 0.0 <= c["drift_direction_hit_rate"] <= 1.0
            assert 0.0 <= c["coverage"] <= 1.0
            assert c["horizon_class"] in ("short_reaction", "pead")
        else:
            assert c["status"] == "insufficient_matured_windows"


def test_horizon_class_separation():
    card = pead.pead_scorecard()
    for w in ("20", "40", "60"):
        c = card["windows"][w]
        if c["status"] == "ok":
            assert c["horizon_class"] == "pead"


def test_empty_returns_yields_insufficient(monkeypatch):
    monkeypatch.setattr(pead, "load_pead_returns", lambda: {})
    card = pead.pead_scorecard()
    for w in ("20", "40", "60"):
        assert card["windows"][w]["status"] == "insufficient_matured_windows"


def test_feature_note_marks_t1_postprint_and_labels_not_features():
    ds = pead.build_pead_dataset()
    note = ds["feature_note"]
    assert "post-print only" in note and "pre-print" in note
    roles = ds["feature_roles"]
    assert "post-print only" in roles["t1_reaction"]
    assert "label/target" in roles["labels_residual[5/20/40/60]"]
    assert "never a feature" in roles["labels_residual[5/20/40/60]"]


def test_spearman_ic_handles_small_samples():
    assert pead._spearman_ic([1.0, 2.0], [1.0, 2.0]) is None  # too few
    ic = pead._spearman_ic([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert ic is not None and ic > 0.9
