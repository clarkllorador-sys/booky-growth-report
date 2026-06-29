# Booky Daily Growth Report

A daily automated analytics report for [Booky](https://booky.ph) — a Philippine food voucher and restaurant discovery app. Every morning it produces a self-contained interactive HTML dashboard and posts a PNG snapshot to Slack before the team starts their day.

---

## What it produces

- **GTV (Gross Transaction Value)** — daily and week-to-date, broken down by App, Web, and Miniprogram (WeChat), with vs-yesterday and vs-same-day-last-week comparisons
- **Conversion rates** — per channel per period (Latest / 1D / 7D / WTD), displayed as a heatmap
- **Average Transaction Value** — same breakdown, same heatmap treatment
- **Top merchants** — gainers and losers by absolute ₱ delta, filterable by channel
- **Weekly waterfall chart** — Mon → Sun GTV bars with future days stubbed out, plotted against the week's North Star target

Reports are delivered to Slack as: anchor message → PNG screenshot → interactive HTML file (all in one thread).

---

## Sample output

```bash
python scripts/generate_dummy_data.py
open outputs/sample_report.html
```

`scripts/generate_dummy_data.py` seeds the template with realistic synthetic data so you can preview the full dashboard without credentials. The output is written to `outputs/sample_report.html`.

---

## Architecture

```
booky-growth-report/
├── inputs/
│   ├── MAIN_TEMPLATE.html       # Self-contained React dashboard (single file)
│   ├── screenshot_watcher.py    # Mac-side Playwright watcher (see below)
│   └── install_watcher.sh       # One-time Launch Agent setup
├── outputs/
│   ├── report_YYYY-MM-DD.html   # Final report (gitignored — regenerate locally)
│   └── report_YYYY-MM-DD.png    # Screenshot (gitignored)
├── scripts/
│   └── generate_dummy_data.py   # Generates sample_report.html for preview
└── pipeline_spec.md             # Full data engineering spec (schema, rules, column mapping)
```

`MAIN_TEMPLATE.html` is the entire front-end: a React app (Babel-in-browser, no build step) with a single `<script id="report-data">` block where the pipeline injects a JSON payload. Open it in Chrome and it renders immediately — no server, no dependencies to install.

---

## How the pipeline works

1. **Fetch** — pull view data from two Tableau views (Transactions, Conversion Funnel) and one GA4 property (Web CR denominator)
2. **Compute** — derive GTV deltas, conversion rates, ATV, merchant gainers/losers, weekly waterfall, and WTD progress against target
3. **Inject** — serialize all metrics to JSON and write into `<script id="report-data">` in a copy of the template
4. **Screenshot** — trigger a local Mac-side Playwright instance to render the HTML and capture a full-page PNG (see [Screenshot infrastructure](#screenshot-infrastructure))
5. **Deliver** — post to Slack: anchor message → PNG reply → HTML file reply (all in one thread)

---

## Tech stack

| Layer | Technology |
|---|---|
| Dashboard front-end | React 18 (Babel-in-browser), plain CSS-in-JS, SVG charts |
| Primary data source | Tableau (transactions, funnel, merchant breakdown) |
| Web CR denominator | Google Analytics 4 — `voucher_details_view` activeUsers |
| Screenshot | Playwright (local Mac) via file-based trigger/watcher pattern |
| Delivery | Slack API — file uploads with thread chaining |
| Currency | Philippine Peso (₱) |

---

## Two pipeline implementations

### Claude-as-pipeline (current)

Claude (running in Anthropic's Cowork desktop app) acts as the data orchestrator. It calls Tableau and GA4 via MCP tool calls, computes all metrics in-context, injects the JSON, and posts to Slack via the Slack MCP — all driven by the prompt spec in `pipeline_spec.md`. There is no boilerplate pipeline code; the logic lives entirely in the spec.

This approach is well-suited for metrics that require judgment calls (e.g. handling data gaps, GA4 ingestion delays, partial-week WTD logic) because the reasoning layer is the pipeline.

### Python implementation (equivalent)

The same pipeline can be built conventionally:

```python
# Data
import tableauserverclient as TSC          # Tableau REST API
from google.analytics.data_v1beta import  # GA4 Python client
    BetaAnalyticsDataClient

# Delivery
from slack_sdk import WebClient

# Injection
import re
re.sub(r'(<script id="report-data">).*?(</script>)',
       rf'\g<1>{json_payload}\g<2>', template, flags=re.DOTALL)
```

Schedule with cron or an Airflow DAG. The `pipeline_spec.md` spec drives both approaches — column mappings, CR formulas, waterfall logic, and merchant rules are source-of-truth there.

---

## Screenshot infrastructure

Generating a PNG from a React/Babel HTML file inside a sandboxed Linux container is non-trivial: Chromium v1217 on ARM64 crashes with `SIGTRAP` due to a kernel seccomp regression, making in-sandbox Playwright unusable.

The workaround: a lightweight Python watcher (`inputs/screenshot_watcher.py`) runs on the Mac as a Launch Agent (auto-start on login, restart on crash). The pipeline communicates with it via files in the workspace folder:

1. Pipeline copies the standalone HTML to the workspace and writes `screenshot_trigger_YYYY-MM-DD.txt`
2. The watcher detects the trigger, screenshots with local Chromium, writes `screenshot_done_YYYY-MM-DD.txt`
3. Pipeline polls for the done file (max ~30s), then uploads the PNG to Slack

The standalone HTML is a pre-compiled version of the report — React and the JSX are bundled inline so the watcher doesn't need network access to CDNs.

One-time setup:

```bash
bash inputs/install_watcher.sh
```

---

## Data schema

The JSON payload injected into the template covers: `meta` (report date, week label, ISO week number), `gtv` (current / vs1d / vs7d / wtd / target / daily waterfall / future flags), `conv` (conversion rates per channel per period), `atv` (average transaction value), and `merchants` (top merchants per channel with multi-period GTV).

See `pipeline_spec.md` for the complete JSON schema, column mappings, CR formulas, waterfall logic, and merchant extraction rules.
