"""V6 -- data/advice boundary tests.

Guards the hard product boundary: generated conclusions/explanations must not
contain buy/sell or other trading-instruction wording, and the API payload must
flag mock data and the not-investment-advice notice. Also guards that the
package imports no LLM/model client.
"""

import os

from modeling.v6.api import build_intelligence_response, BOUNDARIES
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.exposure import build_portfolio
from modeling.v6.impact_engine import analyze_portfolio
from modeling.v6.templates import contains_banned_phrase


def _all_generated_strings(res):
    """Collect every GENERATED advice/explanation string (not echoed titles)."""
    out = [res["conclusion"]]
    for h in res["holdings"]:
        out.append(h["conclusion"])
        for r in h["contributions"]:
            out.append(r["explanation"])
    return out


def test_no_buy_sell_wording_in_generated_conclusions():
    res = analyze_portfolio(build_portfolio(None), load_fixture_events())
    for s in _all_generated_strings(res):
        hit = contains_banned_phrase(s, ignore_quoted=True)
        assert hit is None, f"banned phrase {hit!r} in generated text: {s!r}"


def test_holding_conclusions_never_say_buy_or_sell_instruction():
    res = analyze_portfolio(build_portfolio(None), load_fixture_events())
    for h in res["holdings"]:
        low = h["conclusion"].lower()
        # the conclusion sentence echoes no source title, so scan it raw too
        for word in ("you should buy", "you should sell", "stop loss",
                     "increase position", "reduce position", "trade signal"):
            assert word not in low


def test_api_payload_flags_sample_data_and_boundaries():
    payload = build_intelligence_response(None, event_source="sample")
    assert payload["data_mode"] == "sample"
    assert payload["boundaries"]["no_buy_sell_signal"] is True
    assert payload["boundaries"]["not_investment_advice"] is True
    assert "not provide buy/sell" in payload["boundaries"]["notice"].lower()


def test_application_holdings_with_sample_events_are_labeled():
    holdings = [
        {"symbol": "AAPL", "cost_price": 100.0, "quantity": 2.0},
        {"symbol": "MSFT", "cost_price": 200.0, "quantity": 1.0},
    ]
    payload = build_intelligence_response(holdings, event_source="sample")
    assert payload["data_mode"] == "sample-events"
    assert payload["portfolio"]["is_sample_portfolio"] is False



def test_boundaries_constant_is_non_advice():
    assert BOUNDARIES["engine"].startswith("deterministic")
    assert BOUNDARIES["no_target_price"] is True
    assert BOUNDARIES["no_stop_loss"] is True


def test_v6_package_imports_no_llm_client():
    """Static guard: no v6 source file references an LLM/model SDK."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    v6_dir = os.path.join(root, "modeling", "v6")
    banned = ("openai", "anthropic", "google.generativeai", "genai",
              "cohere", "mistralai", "ollama", "llama_cpp", "transformers")
    for fname in os.listdir(v6_dir):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(v6_dir, fname), encoding="utf-8") as f:
            src = f.read().lower()
        for token in banned:
            assert token not in src, f"{fname} references LLM token {token!r}"
