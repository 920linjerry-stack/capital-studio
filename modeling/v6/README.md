# V6 — Market Intelligence / Portfolio-Aware Event Engine

V6 is a **deterministic, non-LLM, portfolio-aware market intelligence engine**.
It represents macro / sentiment / institutional / official / company events as
structured records, maps them onto the holdings already tracked by the Portfolio
Tracker, and explains the likely impact through three transmission channels:

1. **Direct impact** — company-specific news, or the holding's own factor
   reaction to a macro move (signed sensitivity) and thematic factor overlap.
2. **Second-order transmission** — the event reaches the holding through a
   supplier / customer / sector-beta chain rather than direct company news.
3. **Reflexivity / sentiment** — positioning and risk-on/risk-off feedback
   loops, scaled by each holding's reflexivity exposure.

It classifies effects as **bullish / bearish / neutral / mixed / uncertain**. It
**does not** give buy/sell instructions, target prices, stop-losses, or
automated trading recommendations.

---

## Product goal

Let a user enter from the Portfolio Tracker, see their holdings in an intuitive,
impact-ranked list, expand any holding, and understand *why* today's events
matter for it — direction, channel, and a plain-language explanation — without
ever being told what to trade.

---

## Non-LLM design

Everything is rule-based and deterministic. Equal inputs always produce equal
outputs.

- **Classifier**: ordered keyword/phrase rules with word-boundary matching.
- **Matching**: set intersections over tickers, aliases, sectors, and exposure
  tags.
- **Scoring**: one transparent arithmetic formula (below).
- **Explanations**: fixed string templates filled from structured fields.

There is **no** OpenAI / Anthropic / Gemini / local-model dependency anywhere in
`modeling/v6/`. A test (`tests/test_v6_boundaries.py::test_v6_package_imports_no_llm_client`)
statically asserts no LLM SDK token appears in the package source.

---

## Architecture

Pure calculation logic is separated from the UI, mirroring the existing
`modeling/ma/` package.

```
modeling/v6/
  schemas.py        # MarketEvent (+future fields), HoldingExposure dataclasses
  exposure.py       # curated exposure registry + portfolio adapter + demo sets
  fixtures.py       # curated sample events (recent + scheduled future catalysts)
  classifier.py     # deterministic keyword/rule event classifier
  timing.py         # future-event phase / countdown / anticipation / decay
  dedupe.py         # deterministic multi-feed event de-duplication
  impact_engine.py  # matching, scoring, temporal-weighted aggregation (the core)
  templates.py      # Chinese template explanations + banned-phrase guard
  api.py            # thin, pure UI-facing payload builder
  sources/          # public, keyless source adapters (see below)
    base.py         #   HTTP + RSS/Atom parser + RawItem/FetchResult + raw_to_event
    adapters.py     #   Yahoo / Google News / SEC EDGAR / FRED / analyst adapters
    registry.py     #   orchestration, failure isolation, TTL cache, status rollup
  README.md         # this document
static/modeling/v6.html        # Chinese cockpit page (dashboard dark theme)
static/modeling/js/v6.js       # read-only rendering of the payload
tests/test_v6_*.py             # classifier/engine/boundary/timing/dedupe/sources/cn
```

Flask wiring (in `app.py`):

- `GET /modeling/v6` — serves the page.
- `GET /api/modeling/v6/intelligence` — returns the intelligence payload.
  Reuses application-provided holdings with cost-basis weighting (no live
  quote fetch, so it runs fully offline by default). Query params:
  - `?demo=<id>` — use a named demo portfolio (`sample`, `us_megacap_tech`,
    `leveraged_growth`, `balanced`, `ai_semis`); `?demo=1` ≙ `sample`.
  - `?sources=1` — merge the public-source feed in **fixture** mode (badges).
  - `?live=1` — best-effort **live** fetch from the keyless public sources.
- A V6 entry banner is added to the Portfolio Tracker page (`static/index.html`).

---

## Schemas

### `MarketEvent`

| field | meaning |
|---|---|
| `event_id` | stable id |
| `title` | headline |
| `source` / `source_type` | provenance; `source_type` ∈ macro/sentiment/institutional/official/company |
| `timestamp` | ISO-8601 string |
| `event_type` | one of the classifier types (e.g. `rate_cut`, `earnings_beat`) |
| `direction` | broad direction: `+1` bullish, `-1` bearish, `0` neutral |
| `magnitude` | event strength `1..5` |
| `confidence` | reliability `0..1` |
| `affected_tags` | exposure tags the event hits (e.g. `rates`, `ai_capex`) |
| `related_tickers` | direct tickers |
| `decay_hours` | half-life for time-decay (`0` = none, used by fixtures) |
| `summary` | short note / body |

### `HoldingExposure`

The reusable, **non-private** fingerprint of a holding (no cost/quantity/P&L).

| field | meaning |
|---|---|
| `ticker` / `name` / `aliases` | identity + match terms |
| `sector` / `asset_type` | classification |
| `factor_tags` | thematic exposure (e.g. `growth`, `semiconductors`) |
| `macro_sensitivity` | tag → deterministic signed factor exposure (see below) |
| `second_order_exposure` | transmission tags (supplier/customer/sector beta) |
| `reflexivity_exposure` | `0..1` sentiment-feedback sensitivity |

**Sign convention for `macro_sensitivity` (important):** legacy broad tags such
as `rates` and `yields` remain betas against the event's broad direction. A
second vocabulary of explicit factor states (`oil_up`, `commodity_inflation`,
`inflation_fear`, `risk_off`, `real_yields_up`, `dollar_up`, `credit_stress`,
and `yield_curve_steepening`) uses the sensitivity sign directly as the
holding-specific reaction. This lets one macro event be positive for an oil
beneficiary, negative for high-duration growth, or mixed for gold without
changing the event's broad market direction. Conflicting factor states remain
separate contributions rather than being averaged away.

---

## Rule engine

`impact_engine.match_event_to_holding` attributes an event to a holding through
the channels above. Each matched tag is counted in **exactly one** channel
(direct > second-order) so impact is never double-counted; the reserved tag
`risk_sentiment` always routes to the reflexivity channel.

Scoring (`score_contribution`), applied per channel contribution:

```
impact = position_weight
       × effective_direction      # +1 / -1 / 0
       × magnitude                # raw 1..5
       × relevance                # 0..1 (channel- and beta-dependent)
       × confidence               # 0..1
       × decay_factor             # 1.0 for fixtures; half-life hook otherwise
```

Aggregation (`analyze_holding`, `analyze_portfolio`):

- Sum positive and negative impacts; `net = pos − |neg|`, `gross = pos + |neg|`.
- **Status**: if both sides are material (each ≥ 30% of gross) → `mixed`;
  else `bullish` / `bearish` by net sign, or `neutral`. A non-mixed read whose
  contributing events average `confidence < 0.4` is reported as `uncertain`.
- Portfolio status uses the same logic over all contributions; weighting
  metadata (`cost-basis` / `equal-weight` fallback / `is_sample`) is surfaced.

If a holding has no curated profile it gets a neutral generic fingerprint
(flagged `matched_profile: false`) so it is never silently dropped.

---

## Data boundary

- **No** LLM API, **no** brokerage API, **no** live/paid data sources, **no**
  real secrets, **no** committed private portfolio data.
- Events are currently the bundled **sample fixtures** (`fixtures.py`). The API
  marks this with `data_mode` (`sample` / `sample-events` / `live`) and the UI
  renders an explicit "sample data" notice.
- Every payload carries a `boundaries` block and the UI shows a persistent
  "not investment advice / no buy-sell signal" notice.
- Generated explanations/conclusions are scanned against
  `templates.BANNED_PHRASES`; echoed source headlines (in quotes) are excluded
  from the no-instruction guarantee because they are reported data, not advice.

---

## Mock fixtures vs. future real-source adapters

The bundled fixtures demonstrate every channel: a bullish and a bearish direct
company event, a macro event hitting growth/tech, a second-order transmission
event, a reflexivity/sentiment event, and conflicting events that aggregate to
`mixed`.

The seam for real data is intentionally clean:

- `classifier.recognize_text` first collects every structured state in a
  headline; `assign_direction` then sets a broad sign only when evidence is
  one-sided. `classify_text` / `classify_event` expose the compatible combined
  path. States, conflict flags, and classification confidence remain attached
  to each `MarketEvent` for deterministic audit.
- `api.build_intelligence_response(holdings, events, event_source=...)` accepts a
  caller-supplied event list and an `event_source` label; wiring a real public
  feed means building that list and passing `event_source="live"`.
- `exposure.build_portfolio` already accepts live Portfolio Tracker rows
  (including `market_value_base` for true market-value weighting).

No engine code changes are required to move from sample to live data.

---

## P1 upgrade — Chinese cockpit, future events, sources, dedupe, decay

### Chinese UI & explanations
The cockpit (`v6.html` / `v6.js`) and all generated explanations are in
professional finance Chinese (偏利好 / 偏利空 / 中性 / 多空分歧 / 不确定; 直接影响 /
二次传导 / 反身性·情绪). Tickers, company names and source names stay in English.
The banned-phrase guard (`templates.BANNED_PHRASES`) now also blocks Chinese
instruction terms (买入/卖出/止损/加仓…). Source headlines echoed inside straight
quotes are data, not advice, and are excluded from the guard.

### Future-event countdown (`timing.py`)
Scheduled catalysts (FOMC, CPI, jobs, earnings dates, product launches, policy
announcements) carry `scheduled_at` / `effective_at` plus `anticipation_score`,
`priced_in_score`, `surprise_sensitivity`, `post_event_decay_hours`, and
`sell_the_news_risk`. `temporal_profile(event, now)` derives:

- **phase** — `upcoming` → `anticipation` → `live` → `post_event` → `expired`.
- **countdown** — signed seconds/days to the release.
- **time_weight** (0..1) — ramps UP during anticipation (the market pre-prices
  expectations, capped at the anticipation fraction) and decays DOWN after the
  release (half-life `post_event_decay_hours`).
- **direction_factor** (-1..1) — normally 1; right after a high priced-in /
  high sell-news release it goes toward 0 or flips negative → **利好出尽**.

The engine multiplies each contribution by the signed
`temporal_multiplier = time_weight × direction_factor`. Thus a future event is
included in scoring *before* it happens (to the extent it is pre-priced), peaks
around the release, then fades — a transparent
`future_impact = base × anticipation × confidence × relevance × time_weight`.
The portfolio payload also exposes a sorted `future_timeline` for the countdown
section. **Three catalyst behaviours** are distinguished:
A) announce-only (Fed) — low pre-pricing, most impact on release;
B) pre-priced (earnings/CPI) — meaningful anticipation weight;
C) sell-the-news (high priced-in + risk) — realized direction may flip.

### Time decay
Recent past headlines decay by a per-event-type half-life (`timing._RECENT_DECAY_H`);
scheduled events decay by `post_event_decay_hours`. The UI shows the state as
预期升温 / 进行中 / 影响衰减 / 利好出尽风险 / 事件已兑现.

### Event dedupe (`dedupe.py`)
The same story from multiple feeds is collapsed by a
`(event_type, entity, day-bucket)` signature plus a token-Jaccard near-duplicate
check. The representative keeps the highest confidence/magnitude, records
`source_count` + `source_list`, and gets a small **capped** confidence boost
(≤ +0.10). Impact is never multiplied by source count.

### Public source adapters (`sources/`)
Keyless, isolated from the engine, each honest about its `data_mode`:

| adapter | source | status |
|---|---|---|
| `yahoo_rss` | Yahoo Finance headline RSS (per ticker) | **live-capable**, fixture fallback |
| `google_news_rss` | Google News RSS search | **live-capable**, fixture fallback |
| `sec_edgar` | SEC EDGAR submissions JSON (ticker→CIK) | **live-capable** for covered CIKs, else unavailable |
| `fred_calendar` | macro calendar | **fixture-only** (FRED needs an API key → out of scope) |
| `analyst_headlines` | analyst calls | **fixture-only** (public research is paywalled) |

The `registry` runs every adapter in isolation (one failure never aborts the
page), classifies items into events, dedupes, caches results for 120 s, and
rolls per-source modes into one `sources_overall_mode`. Network is **off by
default** (fixture mode, instant); `?live=1` attempts live fetches with a 4 s
per-request timeout. Modes: `live` / `live-partial` / `fixture` / `unavailable`
/ `error`.

### Broader coverage & demo portfolios
The exposure registry now covers AAPL, MSFT, NVDA, AMD, TSLA, META, GOOGL, JPM,
XOM, UNH, TSM and ETF/leveraged/factor assets QQQ, TQQQ, SGOV, GLD (plus the
original HK/A-share names). Five named demo portfolios are selectable via
`?demo=<id>`. Unknown tickers fall back to a flagged generic profile.

### How to add things
- **New ticker/exposure**: add a `HoldingExposure` to `exposure._PROFILES`
  (or `_PROFILES_EXTRA`). Use the signed-beta-vs-broad-direction convention.
- **New demo portfolio**: add an entry to `exposure.DEMO_PORTFOLIOS`.
- **New event type / keyword**: add a `_Rule` to `classifier._RULES` and the
  type to `schemas.EVENT_TYPES` (+ Chinese label in `templates.EVENT_TYPE_CN`).
- **New source**: implement an adapter class with `id`/`name`/`source_type`/
  `fetch(...) -> FetchResult` in `sources/adapters.py` and append it to
  `ALL_ADAPTERS`. Return fixture items when `allow_network` is False.

---

## How to run

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000/> → click the **V6 · Market Intelligence** banner,
or go directly to <http://127.0.0.1:5000/modeling/v6>. Use the 组合 selector to
switch between **我的持仓** and the demo portfolios, and **合并来源** to merge the
public-source feed (fixture mode).

## How to test

```bash
# focused V6 suite (offline, deterministic)
python -m pytest tests/test_v6_classifier.py tests/test_v6_impact_engine.py \
  tests/test_v6_boundaries.py tests/test_v6_timing.py tests/test_v6_dedupe.py \
  tests/test_v6_sources.py tests/test_v6_chinese.py -q
```

Coverage: two-stage classification and morphology; event→holding matching (all channels + match-kind);
impact scoring; portfolio-weighted scoring; conflict aggregation; future-event
phases / anticipation ramp / decay / sell-the-news; dedupe; RSS+Atom parsing
(from saved samples, **no network**) and registry fixture behaviour; Chinese
localization + the no-buy/sell guarantee (English + Chinese); broad demo
portfolios + unknown-ticker fallback; and the no-LLM static guard.

---

## Known limitations

- Live source fetching is best-effort and **off by default**; without network
  (or for FRED/analyst sources) the feed runs in fixture mode, clearly labelled.
- Exposure profiles are hand-curated; unknown tickers use a neutral generic
  profile (flagged `matched_profile: false`).
- Weighting uses cost basis (or equal-weight fallback) unless live market values
  are supplied; it is labelled accordingly.
- Anticipation/priced-in/sell-the-news parameters are deterministic heuristics,
  not calibrated to historical data — they are transparent, not predictive.
- Gold's inflation-fear / safe-haven support and real-yield / dollar pressure
  are deterministic heuristic exposures; they may correctly produce a mixed
  result, but are not calibrated forecasts.
- SEC EDGAR live coverage is limited to a small built-in ticker→CIK map.

## Recommended next 5 improvements

1. Wire real market-value weighting from the live `/api/portfolio` rows.
2. Persist live-fetched events with their real publish timestamps so decay and
   dedupe operate on genuine multi-feed data.
3. Expand the ticker→CIK map (or fetch the official mapping) for full EDGAR
   coverage, and add an earnings-calendar source for real `scheduled_at` dates.
4. Calibrate anticipation/sell-the-news parameters per event type from history.
5. Add a macro-theme scenario view (group drivers by theme) and a holdings
   heat-map across channels.
