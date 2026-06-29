# Booky Growth Report — Pipeline Specification

> This spec drives the Claude pipeline. A Python implementation would follow the same data rules, swapping Claude + MCP tool calls for direct Tableau REST API + GA4 Python client calls.

Role: Senior BI Analyst | Output: `outputs/` | Template: `inputs/MAIN_TEMPLATE.html`
REPORT_DATE = TODAY - 1

## Output Rule
Populate ONLY the JSON in `<script id="report-data">`. Return ONLY valid JSON. No HTML/CSS/JS changes.

## Data Source
Workbook: `Growth Tracker - MCP v2` · `<your-tableau-workbook-id>`
⚠️ ONLY use `get-view-data`. NEVER query datasource directly.
Rate limit: 10 req/hr — max 2 per batch.

## Views
| ID | View | Use For |
|---|---|---|
| `<view-id-transactions-daily>` | [d] Transactions | Purchases, GTV, Users, Avg Tranx, Source Split |
| `<view-id-funnel-daily>` | [d] Conversion Funnel | App + Mini + Web funnel (Latest, 1D, 7D) |
| `<view-id-transactions-weekly-source>` | [w] Transactions (Source) | WTD transactions by source |
| `<view-id-transactions-weekly-channel>` | [w] Transactions (BBBJO) | WTD transactions by channel |
| `<view-id-funnel-weekly>` | [w] Conversion Funnel | App + Mini + Web funnel (WTD only) |
| `<view-id-max-date>` | MAX DATE | Latest available data date |

## Fetch Order (Daily)
1. `<view-id-transactions-daily>` → transactions + source split (fetch enough history for full week waterfall + vs1d + vs7d + WTD merchants + ATV)
2. `<view-id-funnel-daily>` → funnel Latest, 1D, 7D only
3. `<view-id-funnel-weekly>` → funnel WTD only (weekly views give correct deduped WTD totals)
4. GA4 `voucher_details_view` activeUsers → Web CR denominator for all periods (single call with named date ranges, no date dimension)

## Rules
- Compare REPORT_DATE vs same day last week (REPORT_DATE - 7).
- Period = Mon → REPORT_DATE.
- [d] views → Latest, 1D, 7D CR only. Never use [d] views for WTD CR.
- [w] views → WTD CR only. Never use [w] views for daily CR.
- Web CR denominator = GA4 `voucher_details_view` activeUsers (property `<your-ga4-property-id>`, booky.ph - GA4). Use a single call with named date ranges (no date dimension) so each period is correctly deduplicated.
- Filters pre-applied in views (activated, published_partner, open). Do not re-filter.
- Output: numbers only. No nulls, no ₱/% strings. No empty arrays.

## CSV Parsing (Tableau get-view-data)
The raw result is a single JSON string with `\n`-escaped newlines and `\"`-escaped quotes around numeric values containing commas (e.g. `\"40,646\"`).
**Always unescape before parsing:**
1. Strip the wrapping `"` from the outer string
2. Split on literal `\n` to get rows
3. Replace `\"` → `"` so Python's csv module correctly handles quoted fields
4. Parse with `csv.reader` — do NOT split on commas manually
5. Strip commas from numeric values before casting to float

Skipping step 3 causes quoted numbers like `"40,646"` to be split into two fields, truncating values and producing incorrect totals.

## Conversion Rate Formula
**CR denominator = voucher detail page (VD) visitors, not homepage/listing page visitors.**

**Per source:**
- App CR = `(app.purchasedFrom + app.purchasedNotFrom) / (app.reachedFrom + app.reachedNotFrom)`
  - denominator = `events_app_vd_via_homepage_users + events_app_reached_vds_not_from_homepage`
- Mini CR = `(mini.purchasedFrom + mini.purchasedNotFrom) / (mini.reachedFrom + mini.reachedNotFrom)`
  - denominator = `events_mp_homepage_to_vds_users + events_mp_not_via_homepage (abs)`
- Web CR = `(web.purchasedFrom + web.purchasedNotFrom) / GA4_voucher_details_view_activeUsers`
  - numerator = `uuwp_web_from_listingpage + uuwp_web_not_from_listingpage` (from BOFU view)
  - denominator = GA4 `voucher_details_view` activeUsers (property `<your-ga4-property-id>`) — NOT TOFU listing page visitors
  - Use a **single GA4 call with named date ranges, no date dimension** so each period is correctly deduplicated

**Express as percentage value** (e.g. `7.4` not `0.074`).
Compute for REPORT_DATE (Latest) AND for REPORT_DATE - 1 (1D) AND for REPORT_DATE - 7 (7D).
WTD CR — use `[w]` weekly views only (never sum daily `[d]` views for WTD):
- App/MP WTD CR = `[w] BOFU (uuwp_*)` / `[w] TOFU (vd visitors)` for the current ISO week
- Web WTD CR = `[w] BOFU (uuwp_web_*)` / GA4 `voucher_details_view` activeUsers for Mon→REPORT_DATE (single range call)

## 7D Waterfall Chart Logic
Chart must always show Mon–Sun (7 bars) in `gtv.daily`.
- **Complete days** (Mon → REPORT_DATE): use real GTV values per source. `future: false`.
- **Incomplete days** (REPORT_DATE+1 → Sun): set GTV to `0` and `future: true`. The chart renders no bar for these slots but still shows the axis label.
- `future: true` days — the `dates` entry must use the **actual current-week calendar date** (e.g. if REPORT_DATE is Wed Apr 8, Thu = Apr 9, Fri = Apr 10, etc.). Do NOT use last week's dates.
- Never leave a complete day with 0 if data exists. Never skip days.
- `gtv.wtd` = sum of Mon → REPORT_DATE per source (complete days only, not future).
- `gtv.wtdLabel` = e.g. `"Mar 30–Apr 5"` — first date of week to REPORT_DATE.

## Weekly Targets (gtv.target)
Source targets from the **North Star weekly tracker** for the current ISO week number.
- `Total`, `App`, `Web`, `MP` weekly GTV targets as absolute numbers.
- `meta.weekNumber` = ISO week number for REPORT_DATE (e.g. `15` for week of Apr 6–12 2026).
- Use the table below — do NOT hardcode targets outside this table.

| ISO Week | Dates | Total | App | Web | MP |
|---|---|---|---|---|---|
| Wk 15 | Apr 6–12 | 1,509,722 | 1,364,613 | 114,814 | 30,295 |
| Wk 16 | Apr 13–19 | 1,615,403 | 1,460,136 | 122,851 | 32,416 |
| Wk 17 | Apr 20–26 | 1,728,481 | 1,562,345 | 131,451 | 34,685 |
| Wk 18 | Apr 27–May 3 | 1,849,474 | 1,671,709 | 140,652 | 37,113 |
| Wk 19 | May 4–10 | 1,978,938 | 1,788,729 | 150,498 | 39,711 |

## vs1d and vs7d
- `gtv.vs1d` = REPORT_DATE - 1 GTV per source (Total, App, Web, MP)
- `gtv.vs7d` = REPORT_DATE - 7 GTV per source (Total, App, Web, MP)

## Conversion Data (gtv.conv)
Populate per source (App, Web, MP) and per period:
- `Latest` = CR on REPORT_DATE — use `[d]` BOFU + TOFU views
- `1D`     = CR on REPORT_DATE - 1 — use `[d]` BOFU + TOFU views
- `7D`     = CR on REPORT_DATE - 7 — use `[d]` BOFU + TOFU views
- `WTD`    = cumulative CR Mon → REPORT_DATE — use `[w]` BOFU + TOFU views (correct deduped weekly totals)

⚠️ **WTD App/MP CR: NEVER sum daily [d] views. Always use weekly view data from the weekly TOFU and BOFU views for the current ISO week row.**

**Per source:**
- App/MP: numerator = `uuwp_*` from BOFU; denominator = VD visitors from TOFU (`reachedFrom + reachedNotFrom`)
- Web: numerator = `uuwp_web_*` from BOFU; denominator = GA4 `voucher_details_view` activeUsers (single-range call, no date dimension)

- Any CR = `0` (App, Web, or MP) means no purchases occurred — the template displays `0.00%`.
- Set `gtv.convMock[period]` to `false` for all periods with real data. Only set `true` if a date is genuinely missing from the views.
- **Denominator is VD visitors** (reachedFrom + reachedNotFrom), NOT homepage visitors.

## Column Mapping
**Source split** → `Level 5: Purchase Source Tagging`: `Booky-App`, `Booky-Web`, `Miniprogram`. NULL → `Booky-App`.
**Purchases** → `Purchases`
**GTV** → `SUM(gross_transaction_value)`
**Avg Tranx** → `GTV / Purchases`

**JSON key mapping for sources:**
- `Booky-App` → `"App"`
- `Booky-Web` → `"Web"`
- `Miniprogram` → `"MP"`

## Funnel Mapping
| JSON Key | App Column | Mini Column |
|---|---|---|
| `visited` | `ph_app_homepage_enter_users` | `ph_mp_homepage_users` |
| `reachedFrom` ⭐ | `events_app_vd_via_homepage_users` | `events_mp_homepage_to_vds_users` |
| `reachedNotFrom` ⭐ | `events_app_reached_vds_not_from_homepage` | `events_mp_not_via_homepage (abs)` |

⭐ **CR denominator** = `reachedFrom + reachedNotFrom` (voucher detail page visitors, not homepage visitors)
| `attemptedFrom` | `ph_app_voucher_payment_page_cta_users` | `ph_mp_attempted_to_pay_from_homepage` |
| `attemptedNotFrom` | `ph_app_attempted_to_pay_from_reached_vds_not_from_homepage` | `ph_mp_attempted_to_pay_not_from_homepage` |
| `purchasedFrom` | `uuwp_app_from_homepage` | `uuwp_mp_from_homepage` |
| `purchasedNotFrom` | `uuwp_app_not_from_homepage` | `uuwp_mp_not_from_homepage` |

**Web funnel columns (GA4 for denominator, BOFU view for numerator):**
| JSON Key | Web Column | Source |
|---|---|---|
| `reachedFrom + reachedNotFrom` ⭐ | `voucher_details_view` activeUsers | GA4 property `<your-ga4-property-id>` (single-range call) |
| `purchasedFrom` | `uuwp_web_from_listingpage` | BOFU view |
| `purchasedNotFrom` | `uuwp_web_not_from_listingpage` | BOFU view |

⚠️ Web CR denominator is **no longer** sourced from TOFU `events_web_vd_*` columns. Use GA4 only.
entryLabel: `Homepage` (app/mini), `Listing Page` (web).

## JSON Schema
```json
{
  "meta": {
    "generatedAt": "",
    "source": "growth_raw_ds_v4",
    "reportDate": "",
    "reportDayLabel": "",
    "prevDate": "",
    "prevDayLabel": "",
    "weekLabel": "",
    "weekNumber": 0
  },
  "gtv": {
    "current":  { "Total": 0, "App": 0, "Web": 0, "MP": 0 },
    "vs1d":     { "Total": 0, "App": 0, "Web": 0, "MP": 0 },
    "vs7d":     { "Total": 0, "App": 0, "Web": 0, "MP": 0 },
    "wtd":      { "Total": 0, "App": 0, "Web": 0, "MP": 0 },
    "target":   { "Total": 0, "App": 0, "Web": 0, "MP": 0 },
    "daily": {
      "Total": [0,0,0,0,0,0,0],
      "App":   [0,0,0,0,0,0,0],
      "Web":   [0,0,0,0,0,0,0],
      "MP":    [0,0,0,0,0,0,0]
    },
    "future":   [false,false,false,false,false,false,false],
    "days":     ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    "dates":    ["","","","","","",""],
    "wtdLabel": "",
    "conv": {
      "App": { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 },
      "Web": { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 },
      "MP":  { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 }
    },
    "convMock": { "Latest": false, "1D": false, "7D": false, "WTD": false },
    "merchants": {
      "Total": [{ "name": "", "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 }],
      "MP":    [{ "name": "", "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 }],
      "Web":   [{ "name": "", "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 }],
      "App":   [{ "name": "", "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 }]
    },
    "merchantMock": { "Total": false, "MP": false, "Web": false, "App": false },
    "atv": {
      "Total": { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 },
      "MP":    { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 },
      "Web":   { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 },
      "App":   { "Latest": 0, "1D": 0, "7D": 0, "WTD": 0 }
    },
    "atvMock": false
  }
}
```

### Field notes
| Field | Description |
|---|---|
| `meta.reportDate` | REPORT_DATE as `YYYY-MM-DD` |
| `meta.reportDayLabel` | e.g. `"Thursday · Apr 9"` |
| `meta.prevDate` | REPORT_DATE - 7 as `YYYY-MM-DD` |
| `meta.prevDayLabel` | e.g. `"Thursday · Apr 2"` |
| `meta.weekLabel` | e.g. `"Mar 30–Apr 5"` (Mon of week → REPORT_DATE) |
| `meta.weekNumber` | ISO week number, e.g. `14` |
| `gtv.current` | REPORT_DATE GTV per source |
| `gtv.vs1d` | REPORT_DATE - 1 GTV per source |
| `gtv.vs7d` | REPORT_DATE - 7 GTV per source |
| `gtv.wtd` | Mon → REPORT_DATE cumulative GTV per source |
| `gtv.target` | Weekly North Star target per source (current ISO week) |
| `gtv.daily[k]` | 7-element array Mon→Sun; complete days = real GTV, future days = `0` (no bar rendered) |
| `gtv.future` | 7-element bool array; `true` = day not yet complete |
| `gtv.dates` | 7-element array of display dates; future slots use **current week** dates |
| `gtv.wtdLabel` | e.g. `"Mar 30–Apr 5"` for WTD bar sub-label |
| `gtv.conv` | Conversion rates per source per period (expressed as %, e.g. `3.86`) |
| `gtv.convMock` | Mock flags per period; all periods are `false` (real data from views/GA4). Set `true` only if a date is genuinely missing. |
| `gtv.merchants` | Top merchants by GTV per source. Use `null` for unavailable periods. All sources (Total, App, Web, MP) are real from the Transactions view. |
| `gtv.merchantMock` | Always `false` for all sources — all merchant data is real |
| `gtv.atv` | Avg Transaction Value per source per period. Includes `Total` (all sources combined), `App`, `Web`, `MP`. Compute as `GTV / Purchases` from Transactions view. Set `atvMock: false`. |
| `gtv.atvMock` | `false` — ATV is real, computed from Transactions view |

## Merchant Data Rules
**Step 1 — Get merchants with transactions on REPORT_DATE only.**
**Step 2 — For each of those merchants, look up their 1D, 7D, and WTD values.**

This means the merchant list only contains merchants that had actual GTV on REPORT_DATE. No drop-off merchants, no merchants from other dates.

- `gtv.merchants.App / Web / MP` — merchants with GTV > 0 on REPORT_DATE for that source, sorted by REPORT_DATE GTV desc. For each: `Latest` = REPORT_DATE GTV, `1D` = REPORT_DATE-1 GTV (`null` if none), `7D` = REPORT_DATE-7 GTV (`null` if none), `WTD` = Mon→REPORT_DATE cumulative.
- `gtv.merchants.Total` — merchants with GTV > 0 on REPORT_DATE across ANY source, sorted by REPORT_DATE total GTV desc. 1D/7D/WTD summed across all sources.
- Set all `merchantMock` flags to `false`.
- **If a source truly has zero transactions on REPORT_DATE**: use an empty array `[]`. Do NOT pull merchants from other dates.
- Never output empty arrays for Total — if truly no merchants at all, use one placeholder row with zeroes.
- ⚠️ **Extraction warning**: Parse ALL rows from the Transactions view CSV for REPORT_DATE — do not cap at top-5 or top-10. Use the full csv.reader parse per CSV Parsing rules above.
- ⚠️ **Relevant dates for lookup only**: REPORT_DATE (Latest), D1=REPORT_DATE-1, D7=REPORT_DATE-7, WTD=Mon→REPORT_DATE. Do NOT include merchants from other dates in the view (e.g. dates between D7 and D1).

## ATV Data Rules
- `gtv.atv` — compute as `GTV / Purchases` per source per period directly from the Transactions view.
  - `Latest` = REPORT_DATE ATV per source
  - `1D` = REPORT_DATE - 1 ATV per source
  - `7D` = REPORT_DATE - 7 ATV per source
  - `WTD` = sum(GTV Mon→REPORT_DATE) / sum(Purchases Mon→REPORT_DATE) per source
- **Total ATV** = `(App GTV + Web GTV + MP GTV) / (App Purchases + Web Purchases + MP Purchases)` per period. Always populate `gtv.atv.Total` for all four periods. The template renders it as the top row of the ATV heatmap in teal.
- If a source had **zero purchases** on a given day (e.g. MP on a slow Monday), set ATV to `0` in the JSON — the template renders `–` for any value ≤ 0. Do NOT omit the key.
- Always set `gtv.atvMock = false` — ATV is fully computable from the Transactions view.

## Report Generation — Final Step
After populating all JSON fields, write the final report file:
- Copy `inputs/MAIN_TEMPLATE.html` with the populated JSON block to `outputs/report_{REPORT_DATE}.html`
- Then build a standalone version for screenshotting (the sandbox has no outbound network, so CDN scripts cannot load in Playwright — the standalone inlines everything):

```python
import re, subprocess

REPORT_DATE = "YYYY-MM-DD"  # set dynamically
report_html = f"outputs/report_{REPORT_DATE}.html"
standalone  = f"{WORK_DIR}/report_standalone.html"

with open(report_html) as f:
    html = f.read()

# Transpile JSX
jsx = re.search(r'<script type="text/babel">(.*?)</script>', html, re.DOTALL).group(1)
with open(f"{WORK_DIR}/temp_report.jsx", "w") as f:
    f.write(jsx)

subprocess.run(["node", "-e", """
const babel = require('./node_modules/@babel/standalone/babel.js');
const fs = require('fs');
const code = fs.readFileSync('/sessions/<current-session>/temp_report.jsx', 'utf8');
const out = babel.transform(code, { presets: ['react'] });
fs.writeFileSync('/sessions/<current-session>/temp_report_compiled.js', out.code);
"""], cwd=WORK_DIR, check=True)

with open(f"{WORK_DIR}/temp_report_compiled.js") as f:
    compiled_js = f.read()
with open(f"{WORK_DIR}/react_bundle.js") as f:
    react_bundle = f.read()

new_html = re.sub(r'\s*<script src="https://cdnjs[^"]+(?:react|babel)[^"]+"></script>', '', html)
start = new_html.find('<script type="text/babel">')
end   = new_html.find('</script>', start) + len('</script>')
new_html = new_html[:start] + f"<script>\n{react_bundle}\n</script>\n<script>\n{compiled_js}\n</script>" + new_html[end:]

with open(standalone, "w") as f:
    f.write(new_html)
```

## Step 0: Pre-warm — run THIS FIRST, before any data fetching

Kick off in the very first bash call so npm packages are ready before screenshotting.

```bash
WORK_DIR=$(pwd)

# Install npm packages if missing (also in background)
[ ! -f "$WORK_DIR/react_bundle.js" ] && \
  npm install @babel/standalone esbuild react@18 react-dom@18 --cache /tmp/npm-cache -s &
echo "npm install started in background"
```

## Slack Delivery
Channel: `#Growth` (`<slack-channel-growth>`) - send live reports here
Channel: `#tests_claude_daily_updates` (`<slack-channel-tests>`) - send test/preview reports here

### Step 1 — Post anchor message to channel
  - Post anchor message to channel: `Growth Daily Report - As of {REPORT_DATE}`
  - Capture the `ts` value from the message response and save it as `anchor_thread_ts`

### Step 2 — Screenshot standalone HTML → post PNG as thread reply

#### How it works
A lightweight watcher (`screenshot_watcher.py`) runs as a Launch Agent (auto-starts on login, always running). To trigger a screenshot:
1. Copy the standalone HTML to the workspace folder
2. Write a trigger file → watcher picks it up, screenshots with local Chromium, writes a done file
3. Poll for the done file (max ~15s), then use the PNG

#### Screenshot trigger code
```python
import time, shutil
from pathlib import Path

REPORT_DATE = "YYYY-MM-DD"  # set dynamically
WORKSPACE   = "/path/to/workspace/growth_daily_reports"  # set dynamically
WORK_DIR    = "/path/to/work_dir"  # set dynamically

# 1. Copy standalone HTML to workspace so watcher can reach it
shutil.copy(f"{WORK_DIR}/report_standalone.html", f"{WORKSPACE}/report_{REPORT_DATE}_standalone.html")

# 2. Write trigger file
Path(f"{WORKSPACE}/screenshot_trigger_{REPORT_DATE}.txt").write_text("trigger")

# 3. Poll for done or error (max 30s)
done  = Path(f"{WORKSPACE}/screenshot_done_{REPORT_DATE}.txt")
error = Path(f"{WORKSPACE}/screenshot_error_{REPORT_DATE}.txt")
for _ in range(15):
    if done.exists():
        print(f"Screenshot ready: {WORKSPACE}/outputs/report_{REPORT_DATE}.png")
        break
    if error.exists():
        print(f"Screenshot error: {error.read_text()}")
        break
    time.sleep(2)
else:
    print("Watcher timeout — is screenshot_watcher.py running?")
```

  - Upload PNG using `slack_upload_file` with:
    - `thread_ts` = `anchor_thread_ts`
    - File: `outputs/report_{REPORT_DATE}.png`
    - Caption format: Lead with **GTV** (total + absolute diff vs 1D, with % in parenthesis), then **Merchant callout** (Top 3 by Latest GTV if GTV is up vs 1D; Bottom 3 / Top 3 Losers if GTV is down vs 1D), then **Conversion rates per source** (App, Web, MP — Latest values only, no directional commentary). Executive-friendly, 2–3 sentences max. Use strong adjectives ("surged", "jumped") only if the magnitude is >100%; otherwise use neutral language ("rose", "climbed", "improved", "up").
    - Example (GTV up): `GTV came in at ₱135K on Apr 20, up from ₱132K the day prior (+2%). Alba, Vikings, and Tim Ho Wan led with ₱75.6K, ₱21.9K, and ₱17K respectively. App CR: 7.92%, Web: 2.32%, MP: 0.33%.`
    - Example (GTV down): `GTV came in at ₱135K on Apr 20, down from ₱137K the day prior (-1%). Top losers vs 1D: Mesa (-₱3.9K), Kuro Gyukatsu (-₱4.5K), Tim Ho Wan (-₱39.1K). App CR: 7.92%, Web: 2.32%, MP: 0.33%.`

### Step 3 — Upload HTML as reply in anchor thread
  - Upload the already-generated report HTML (not the standalone) using `slack_upload_file` with:
    - `thread_ts` = `anchor_thread_ts`
    - File: `outputs/report_{REPORT_DATE}.html`
    - Initial comment: `Download the HTML File for the Interactive Dashboard. Open in Chrome for best experience.`

  Rules:
  - Do NOT create a new parent message for the HTML file
  - Do NOT post a separate summary message
  - Do NOT post the HTML as a standalone message
  - The HTML upload must appear only as a reply inside the anchor thread
  - If `anchor_thread_ts` is missing, stop and do not upload the HTML

⚠️ Step 3 MUST reference `thread_ts` from Step 1. Never post HTML as a standalone message.

### Step 4 — Cleanup temporary files
After all uploads are confirmed, delete build artifacts from the workspace folder to avoid bloating storage:

```python
import os
from pathlib import Path

REPORT_DATE = "YYYY-MM-DD"  # set dynamically
WORKSPACE   = "/path/to/workspace/growth_daily_reports"

files_to_delete = [
    f"{WORKSPACE}/report_{REPORT_DATE}_standalone.html",
    f"{WORKSPACE}/screenshot_trigger_{REPORT_DATE}.txt",
    f"{WORKSPACE}/screenshot_done_{REPORT_DATE}.txt",
    f"{WORKSPACE}/screenshot_error_{REPORT_DATE}.txt",
]

for f in files_to_delete:
    p = Path(f)
    if p.exists():
        p.unlink()
        print(f"Deleted: {p.name}")
    else:
        print(f"Not found (skip): {p.name}")
```

Keep: `outputs/report_{REPORT_DATE}.html`, `outputs/report_{REPORT_DATE}.png` — these are the final deliverables.
Delete: `_standalone.html`, `screenshot_trigger_*.txt`, `screenshot_done_*.txt`, `screenshot_error_*.txt`

## Template UI Notes (as of Apr 17 2026)

### GTV Chart (Section 1)
- **LeftChart** (left side): shows Apr 14 / vs 1d / vs 7d bars. Scale is **independent** — `mx = Math.max(cur, d1, d7, 1)`. Does NOT share scale with WaterfallChart. Dimensions: `W=208, H=360, BAR_W=52, GAP=18, BOT=298, CHART_H=240`.
- **WaterfallChart** (right side): weekly waterfall Mon→Sun + WTD + gap + target. Dimensions: `DAY_W=34, DAY_GAP=14, BIG_W=44, BIG_GAP=18, BOT=298, CHART_H=240, H=360`. Minimal left/right padding (`dx starts at 4, right pad +4`).
- **Baseline alignment**: both SVGs are exactly `H=360, BOT=298` → 62px below BOT in both. Flex container uses `alignItems:"flex-end"` so baselines visually align. Rule: always keep `H - BOT = 62` on both charts.
- **Colors**: `COL_APP="#F07020"` (orange), `COL_WEB="#22A24A"` (green), `COL_MP="#0E87B0"` (blue).

### Channel Contribution & Conversion (Section 2)
- **Color legends** shown above Stacked Channel Contribution % chart.
- **Stacked Contribution % labels:** Suppress the label when the segment's contribution = 0% — do not render a `<text>` element for zero-value segments (avoids clutter/overlap on thin bars).
- **Web CR** is real — computed from BOFU view (numerator) + GA4 (denominator). Any CR `0` renders as `0.00%`.
- **GA4 delay note:** If Web CR = 0 on REPORT_DATE due to a BigQuery/GA4 ingestion delay, add an italic note below the Web conversion box **in the report file only** (not in `inputs/MAIN_TEMPLATE.html`). Insert as a `<div>` after the ConversionHeatmap SVG: `<div style={{ fontSize:10, color:TXT3, fontStyle:"italic", marginTop:4 }}>* There's a delay in GA4 data and this is expected.</div>`

### Heatmaps — Conversion & ATV (Section 2)
- **Opacity range:** `0.50 + 0.40 * normalised_value`. Zero-value cells use opacity `0.12`.
  - Conversion: `const opFor = (v) => v===0 ? 0.12 : 0.50+0.40*((v-minV)/(maxV-minV||1));`
  - ATV: `const opFor = (v) => v===0 ? 0.12 : 0.50+0.40*((v-minV)/(maxV-minV||1));`
- **Font color:** Always `WHITE` regardless of opacity. Never use a dark font color on heatmap cells.
- **Self-edit instructions:** To adjust opacity, search for `opFor` in `inputs/MAIN_TEMPLATE.html`. There are two instances — one in the ConversionHeatmap component and one in the ATVHeatmap component. Change the `0.50` (base) and/or `0.40` (range) values. The formula is `base + range * normalised`. Zero cells always stay at `0.12`.

### Top Merchants (Section 2)
- Source filter buttons styled to match waterfall channel filters (outline style with color ring on active).
- All sources (Total, App, Web, MP) use **real merchant data** from Transactions view. `merchantMock` all `false`.
- **Only merchants with transactions on REPORT_DATE are shown** — no drop-offs, no merchants from other dates.
- **Top 3 Gainers logic:** Latest > 0, prior period can be null/0 (from-zero merchants included). Sorted by **absolute ₱ delta descending**. % shows "–" when prior was null/0. If fewer than 3 eligible gainers exist, only those that exist are shown.
- **Top 3 Losers logic:** Merchants with REPORT_DATE GTV below their prior-period GTV, sorted by absolute ₱ delta ascending (biggest loss first). Since merchant list only contains REPORT_DATE merchants, losers are merchants who transacted today but less than before.
- Caveats: If a source tab has no eligible gainers or losers, the section shows "None". This is correct — do not pad with placeholders.
- **Expand table button:** Clicking "Expand table ▸" switches the page to a full in-page merchant table view showing all merchants for the selected source, sorted by REPORT_DATE GTV desc. A "◂ Back to report" button returns to the main report. Source tabs in the expanded view let the user switch channels without leaving the expanded view.

### ATV (Section 2)
- Zero purchases → ATV = `0` in JSON → template renders "–". Never show ₱0.
- **Total row** appears at the top of the heatmap in teal, above the per-channel rows (MP, Web, App), separated by a divider line. Formula: `(App + Web + MP GTV) / (App + Web + MP Purchases)` per period.

## Standalone Build — Prerequisites
The session directory changes each time. Always use the **current** session path. The `react_bundle.js` and npm packages must be built fresh each session if not already present:

```bash
# Check if already built
ls /path/to/work_dir/react_bundle.js

# If missing, build it:
cd /path/to/work_dir
npm install @babel/standalone esbuild react@18 react-dom@18
node -e "
const esbuild = require('./node_modules/esbuild');
esbuild.buildSync({
  stdin: { contents: \`
    const React = require('react');
    const ReactDOM = require('react-dom/client');
    window.React = React;
    window.ReactDOM = ReactDOM;
  \`, resolveDir: './node_modules' },
  bundle: true, outfile: 'react_bundle.js', format: 'iife',
  define: { 'process.env.NODE_ENV': '\"production\"' }
});
"
```

⚠️ **Must use React 18** (`react@18 react-dom@18`). React 19 does not expose `ReactDOM.createRoot` the same way and will break rendering silently (page loads but root div stays empty, no console errors).

## Known Issues & Fixes (Apr 2026)

### Merchant data — shallow extraction bug (fixed Apr 16 2026)
**Symptom:** Null values appearing for merchants in the Latest column; Top 3 Gainers showing only 1–2 merchants; Top 3 Losers showing "None".

**Root cause:** The Transactions view returns 30+ merchant rows per day per source. An initial extraction that only captured the top ~5 merchants by name caused most merchants to have `Latest = null` (they weren't in the truncated list), and the Gainers/Losers logic excludes null-prior-period merchants, leaving few or none.

**Fix:** Fully parse the Transactions CSV and extract **every** (date, source, merchant_name) → GTV row. Build merchant lists by iterating over all rows for REPORT_DATE grouped by source, then look up 1D/7D/WTD values from the same full dataset. Never manually enumerate merchant names.

### Gainers/Losers logic — sorting and drop-off bug (fixed Apr 16 2026)
**Symptom:** Top 3 Gainers showed small merchants with large % swings ahead of consistently active high-volume merchants. Top 3 Losers missed merchants who completely dropped off.

**Root cause (Gainers):** Old logic sorted by % change, not absolute ₱ delta. Small merchants with a lucky big % day would outrank high-volume regulars.

**Root cause (Losers):** Old logic only considered merchants present on REPORT_DATE (Latest != null). Merchants who dropped off entirely were invisible. Additionally, the merchants JSON array only contained merchants active on REPORT_DATE.

**Fix (template JS):** Gainers sorted by `delta` (absolute ₱) descending. Losers split into two groups — active-but-dropped + complete drop-offs — merged and sorted by absolute ₱ delta.

**Fix (JSON data):** Include drop-off merchants in every source's merchants array with `Latest: null` and their prior-period GTV values populated. These rows are invisible in the table (Latest shows `–`) but enable the losersDropped logic to surface them.

### Gainers/Losers container overflow (fixed Apr 18 2026)
**Symptom:** Top 3 Losers values overflowed outside the right column boundary (visible on Web tab where values are large).
**Fix (template):** Gainers/Losers row uses `gap:12`, both columns get `minWidth:0, overflow:"hidden"`, name span uses `flex:1, minWidth:0, marginRight:4` (not `maxWidth:"55%"`), value div gets `flexShrink:0, minWidth:52`. Already applied to `inputs/MAIN_TEMPLATE.html`.

### Total merchants — top-10 cap bug (fixed Apr 18 2026)
**Symptom:** Total showed "None" for Top 3 Losers because drop-off merchants (Latest=null) were excluded by the top-10 cut.
**Fix (data):** Build `merchants.Total` from ALL merchants with GTV in any relevant date — do not cap at 10.

### Losers — any-prior-period drop-off bug (fixed Apr 17 2026)
**Symptom:** A merchant with no sales on REPORT_DATE was not appearing in Top 3 Losers even though it had significant prior GTV.

**Root cause:** `losersDropped` only checked `m[glPeriod]` (the active compare period, e.g. "7D"). If the merchant had GTV on `1D` but not on `7D`, and `glPeriod` was "7D", the merchant was invisible. The JSON merchants array also sometimes excluded merchants with `Latest: null`.

**Fix (template JS):** `losersDropped` now checks `(m["1D"] != null && m["1D"] > 0) || (m["7D"] != null && m["7D"] > 0)` regardless of `glPeriod`. The reference delta uses the largest available prior value: `glPeriod` first, then `1D`, then `7D`.

**Fix (JSON data):** Always include all merchants that had GTV in any period (Latest, 1D, 7D, WTD) in the source's merchants array, even if `Latest = null`. This ensures the JS drop-off logic has full visibility.
