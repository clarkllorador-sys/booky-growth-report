import os
from datetime import date, timedelta, datetime
from dotenv import load_dotenv
from collections import defaultdict
import requests
import json
import csv
import io
import time

# ── Load .env ──────────────────────────────────────────────────────────────
# Place your .env file at the same directory as this notebook
# Required keys:
#   TABLEAU_SERVER   = https://prod-<region>.online.tableau.com
#   TABLEAU_SITE     = <your-tableau-site>
#   TABLEAU_TOKEN_NAME  = <your PAT name>
#   TABLEAU_TOKEN_VALUE = <your PAT value>
#   SLACK_BOT_TOKEN  = xoxb-...
#   ANTHROPIC_API_KEY = sk-ant-...
#   GA4_PROPERTY_ID  = <your-ga4-property-id>
#   GOOGLE_APPLICATION_CREDENTIALS = /path/to/service-account.json

load_dotenv()

TABLEAU_SERVER     = os.getenv("TABLEAU_SERVER")
TABLEAU_SITE       = os.getenv("TABLEAU_SITE")
TABLEAU_TOKEN_NAME = os.getenv("TABLEAU_PAT_NAME")
TABLEAU_TOKEN_VALUE= os.getenv("TABLEAU_PAT_SECRET")
SLACK_BOT_TOKEN    = os.getenv("SLACK_BOT_TOKEN")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
GA4_PROPERTY_ID    = os.getenv("GA4_PROPERTY_ID")

# ── Validate secrets loaded ─────────────────────────────────────────────────
secrets = {
    "TABLEAU_SERVER":      TABLEAU_SERVER,
    "TABLEAU_SITE":        TABLEAU_SITE,
    "TABLEAU_TOKEN_NAME":  TABLEAU_TOKEN_NAME,
    "TABLEAU_TOKEN_VALUE": TABLEAU_TOKEN_VALUE,
    "SLACK_BOT_TOKEN":     SLACK_BOT_TOKEN,
    # "ANTHROPIC_API_KEY":   ANTHROPIC_API_KEY,
    "GA4_PROPERTY_ID":     GA4_PROPERTY_ID,
}


# ── View LUIDs ──────────────────────────────────────────────────────────────
VIEWS = {
    "d_transactions":  "<your-daily-transactions-view-luid>",
    "d_conversion":    "<your-daily-conversion-view-luid>",
    "w_conversion":    "<your-weekly-conversion-view-luid>",
}

# ── Slack config ─────────────────────────────────────────────────────────────
# SLACK_CHANNEL_ID = "<your-slack-channel-id>"  # #growth
SLACK_CHANNEL_ID = "<your-slack-channel-id>"  # #your-channel

# ── Paths ────────────────────────────────────────────────────────────────────
TEMPLATE_PATH = "inputs/MAIN_TEMPLATE.html"
OUTPUT_DIR    = "outputs/"

WEEKLY_TARGETS = {
    19: {"Total": 885994, "App": 799526, "Web": 53127, "MP": 33341},
    20: {"Total": 948014, "App": 855493, "Web": 56845, "MP": 35675},
    21: {"Total": 1014375, "App": 915378, "Web": 60825, "MP": 38172},
    22: {"Total": 1085381, "App": 979454, "Web": 65082, "MP": 40844},
    23: {"Total": 0, "App": 0, "Web": 0, "MP": 0},
}

print("=== Secrets ===")
all_loaded = True
for k, v in secrets.items():
    if v:
        masked = v[:6] + "..." + v[-4:] if len(v) > 10 else "***"
        print(f"  ✅ {k}: {masked}")
    else:
        print(f"  ❌ {k}: MISSING")
        all_loaded = False

if not all_loaded:
    raise EnvironmentError("One or more required secrets are missing. Check your .env file.")

# ── Compute Dates ───────────────────────────────────────────────────────────
today        = date.today()
REPORT_DATE  = today - timedelta(days=1)          # yesterday
DATE_1D      = REPORT_DATE - timedelta(days=1)     # day before report
PREV_DATE    = REPORT_DATE - timedelta(days=7)     # same day last week

# ISO week — Monday = start of week
iso_cal      = REPORT_DATE.isocalendar()
ISO_WEEK     = iso_cal[1]
WEEK_START   = REPORT_DATE - timedelta(days=REPORT_DATE.weekday())  # Monday

# Date range for Tableau fetch — Mon of current week → REPORT_DATE
# We also need PREV_DATE (7D ago) for vs7d metrics
# So we fetch from: WEEK_START - 7 days to cover all periods
FETCH_FROM   = WEEK_START - timedelta(days=7)
FETCH_TO     = REPORT_DATE

# Labels
DAY_NAMES    = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
REPORT_DAY_LABEL = f"{REPORT_DATE.strftime('%A')} · {REPORT_DATE.strftime('%b %-d')}"
PREV_DAY_LABEL   = f"{PREV_DATE.strftime('%A')} · {PREV_DATE.strftime('%b %-d')}"
WEEK_LABEL       = f"{WEEK_START.strftime('%b %-d')}–{REPORT_DATE.strftime('%b %-d')}"

# Week waterfall dates (Mon → Sun of current ISO week)
WATERFALL_DATES = [
    (WEEK_START + timedelta(days=i)).strftime("%b %-d")
    for i in range(7)
]
WATERFALL_FUTURE = [
    (WEEK_START + timedelta(days=i)) > REPORT_DATE
    for i in range(7)
]

print("\n=== Dates ===")
print(f"  Today:          {today}")
print(f"  REPORT_DATE:    {REPORT_DATE}  ({REPORT_DAY_LABEL})")
print(f"  DATE_1D:        {DATE_1D}")
print(f"  PREV_DATE:      {PREV_DATE}  ({PREV_DAY_LABEL})")
print(f"  WEEK_START:     {WEEK_START}")
print(f"  ISO_WEEK:       Wk {ISO_WEEK}")
print(f"  WEEK_LABEL:     {WEEK_LABEL}")
print(f"  FETCH_FROM:     {FETCH_FROM}")
print(f"  FETCH_TO:       {FETCH_TO}")

print("\n=== Waterfall (Mon→Sun) ===")
for i, (d, future) in enumerate(zip(WATERFALL_DATES, WATERFALL_FUTURE)):
    status = "future (no bar)" if future else "complete"
    print(f"  {DAY_NAMES[i]}: {d}  [{status}]")

print("\n✅ Step 1 complete.")

# ── Sign in via Personal Access Token ──────────────────────────────────────
signin_url = f"{TABLEAU_SERVER}/api/3.21/auth/signin"

payload = {
    "credentials": {
        "personalAccessTokenName": TABLEAU_TOKEN_NAME,
        "personalAccessTokenSecret": TABLEAU_TOKEN_VALUE,
        "site": {
            "contentUrl": TABLEAU_SITE
        }
    }
}

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}

print(f"Signing in to: {signin_url}")
print(f"Site:          {TABLEAU_SITE}")
print(f"Token name:    {TABLEAU_TOKEN_NAME}")

resp = requests.post(signin_url, json=payload, headers=headers)

print(f"\nHTTP Status: {resp.status_code}")

if resp.status_code != 200:
    print("❌ Auth failed:")
    print(resp.text)
    raise Exception(f"Tableau sign-in failed: {resp.status_code}")

auth_data      = resp.json()
tableau_token  = auth_data["credentials"]["token"]
site_id        = auth_data["credentials"]["site"]["id"]
user_id        = auth_data["credentials"]["user"]["id"]

# Auth header for all subsequent calls
AUTH_HEADERS = {
    "X-Tableau-Auth": tableau_token,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

print(f"\n=== Auth Success ===")
print(f"  Site ID:  {site_id}")
print(f"  User ID:  {user_id}")
print(f"  Token:    {tableau_token[:12]}...{tableau_token[-6:]}")

print("\n✅ Step 2 complete — Tableau token ready.")

def fetch_view(view_id, view_name, site_id, auth_headers, tableau_server):
    """
    Fetch a Tableau view as CSV using get-view-data.
    Returns parsed list of dicts.
    
    Follows CLAUDE.md CSV parsing rules:
    1. Strip wrapping quotes from outer string
    2. Split on literal \\n
    3. Replace \\" → " for quoted numeric fields
    4. Parse with csv.reader
    5. Strip commas from numeric values before casting
    """
    url = f"{tableau_server}/api/3.21/sites/{site_id}/views/{view_id}/data"
    
    resp = requests.get(url, headers=auth_headers)
    
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch view {view_name} ({view_id}): {resp.status_code}\n{resp.text}")
    
    raw = resp.text
    
    # ── CSV Parsing per CLAUDE.md ──────────────────────────────────────────
    # Step 1: Strip outer wrapping quotes if present
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    
    # Step 2: Split on literal \n
    raw = raw.replace('\\n', '\n')
    
    # Step 3: Replace \" → " so csv.reader handles quoted numeric fields
    raw = raw.replace('\\"', '"')
    
    # Step 4: Parse with csv.reader
    reader = csv.DictReader(io.StringIO(raw))
    
    rows = []
    for row in reader:
        cleaned = {}
        for k, v in row.items():
            if v is not None:
                # Step 5: Strip commas from numeric values
                cleaned[k.strip()] = v.strip().replace(',', '') if v else v
            else:
                cleaned[k.strip()] = v
        rows.append(cleaned)
    
    return rows


def safe_float(val):
    """Convert string to float, return 0.0 if empty/null."""
    try:
        return float(str(val).replace(',', '').strip()) if val else 0.0
    except (ValueError, TypeError):
        return 0.0


print("✅ Helper functions defined.")
print(f"   Views to fetch: {list(VIEWS.keys())}")

# ── Fetch Views (2 per batch, 6s pause between batches) ────────────────────
# Batch 1: d_transactions + d_conversion
# Batch 2: w_conversion (solo)

raw_data = {}

batches = [
    ["d_transactions", "d_conversion"],
    ["w_conversion"],
]

for batch_num, batch in enumerate(batches, 1):
    print(f"\n--- Batch {batch_num}: {batch} ---")
    
    for view_name in batch:
        view_id = VIEWS[view_name]
        print(f"  Fetching {view_name} ({view_id})...", end=" ")
        
        rows = fetch_view(
            view_id    = view_id,
            view_name  = view_name,
            site_id    = site_id,
            auth_headers = AUTH_HEADERS,
            tableau_server = TABLEAU_SERVER
        )
        
        raw_data[view_name] = rows
        print(f"✅ {len(rows)} rows")
        
        if rows:
            print(f"     Columns: {list(rows[0].keys())}")
    
    # Pause between batches (not after the last one)
    if batch_num < len(batches):
        print(f"  ⏳ Pausing 6s before next batch...")
        time.sleep(6)

print("\n✅ Step 3 complete — all views fetched.")
print("\n=== Summary ===")
for view_name, rows in raw_data.items():
    print(f"  {view_name:20s}: {len(rows):>4} rows")

# ── Validation — Spot check d_transactions ─────────────────────────────────
# Print first 5 rows of d_transactions to confirm fields look right

print("=== d_transactions — First 5 rows ===")
for i, row in enumerate(raw_data["d_transactions"][:5]):
    print(f"\nRow {i+1}:")
    for k, v in row.items():
        print(f"  {k}: {v}")

print("\n=== d_conversion — First 3 rows ===")
for i, row in enumerate(raw_data["d_conversion"][:3]):
    print(f"\nRow {i+1}: {row}")

print("\n=== w_conversion — First 3 rows ===")
for i, row in enumerate(raw_data["w_conversion"][:3]):
    print(f"\nRow {i+1}: {row}")

print("\n✅ Validation complete. Check the column names above match CLAUDE.md mappings.")
print("""
Key columns to confirm in d_transactions:
  - cpc_tranx_date (transaction date)
  - Level 5: Purchase Source Tagging (Booky-App / Booky-Web / Miniprogram)
  - Purchases
  - SUM(gross_transaction_value)
  - Merchant Name (or similar)

Key columns to confirm in d_conversion:
  - date_scaffold (funnel date — shared by TOFU and BOFU rows)
  - Measure Names
  - Measure Values
""")

# ── Source mapping ──────────────────────────────────────────────────────────
SOURCE_MAP = {
    "Booky-App":    "App",
    "Booky-Web":    "Web",
    "Miniprogram":  "MP",
}

def map_source(raw):
    """Map raw source label to App/Web/MP. NULL → App."""
    if not raw or raw.strip() == "":
        return "App"
    return SOURCE_MAP.get(raw.strip(), "App")

def parse_date(raw_date):
    """Parse M/D/YYYY or YYYY-MM-DD to date string YYYY-MM-DD."""
    raw_date = str(raw_date).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d %Y"):
        try:
            return datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {raw_date}")

# ── Pivot d_transactions ────────────────────────────────────────────────────
# Structure: (date, source, merchant) → {measure: value}
txn = defaultdict(lambda: defaultdict(float))

# Measure name normalisation — map Tableau measure names to clean keys
MEASURE_MAP = {
    "Purchases":                          "Purchases",
    "Claims":                             "Claims",
    "GTV":            "GTV",
    "Unique Users with Success Payment":  "Users",
}

skipped = 0
for row in raw_data["d_transactions"]:
    raw_date    = row.get("date_scaffold", "")
    raw_source  = row.get("Level 5: Purchase Source Tagging", "")
    merchant    = row.get("merchant_name", "Unknown").strip()
    measure_raw = row.get("Measure Names", "").strip()
    value_raw   = row.get("Measure Values", "0")

    # Skip rows with unmapped measures
    measure = MEASURE_MAP.get(measure_raw)
    if not measure:
        skipped += 1
        continue

    # Skip Tableau grand total rows and empty dates
    if not raw_date or raw_date.strip().lower() == "all":
        skipped += 1
        continue

    date_str = parse_date(raw_date)
    source   = map_source(raw_source)
    value    = safe_float(value_raw)

    txn[(date_str, source, merchant)][measure] += value

print(f"d_transactions parsed: {len(txn)} unique (date × source × merchant × measure) combos")
print(f"Skipped rows (unmapped measures): {skipped}")

# ── Roll up to (date, source) totals ────────────────────────────────────────
txn_by_date_source = defaultdict(lambda: defaultdict(float))

for (date_str, source, merchant), measures in txn.items():
    for measure, value in measures.items():
        txn_by_date_source[(date_str, source)][measure] += value

# ── Roll up to (date) totals across all sources ──────────────────────────────
txn_by_date = defaultdict(lambda: defaultdict(float))

for (date_str, source), measures in txn_by_date_source.items():
    for measure, value in measures.items():
        txn_by_date[date_str][measure] += value

# ── Quick spot check ─────────────────────────────────────────────────────────
print(f"\n=== txn_by_date_source — REPORT_DATE ({REPORT_DATE}) ===")
report_date_str = REPORT_DATE.strftime("%Y-%m-%d")
date_1d_str     = DATE_1D.strftime("%Y-%m-%d")
prev_date_str   = PREV_DATE.strftime("%Y-%m-%d")
week_start_str  = WEEK_START.strftime("%Y-%m-%d")

for source in ["App", "Web", "MP"]:
    key = (report_date_str, source)
    d = txn_by_date_source.get(key, {})
    print(f"  {source}: Purchases={d.get('Purchases',0):.0f}  GTV={d.get('GTV',0):,.0f}  Users={d.get('Users',0):.0f}")

total = txn_by_date.get(report_date_str, {})
print(f"  Total: Purchases={total.get('Purchases',0):.0f}  GTV={total.get('GTV',0):,.0f}")

print(f"\n=== Available dates in d_transactions ===")
all_dates = sorted(set(k[0] for k in txn_by_date_source.keys()))
for d in all_dates:
    t = txn_by_date.get(d, {})
    print(f"  {d}: Purchases={t.get('Purchases',0):.0f}  GTV={t.get('GTV',0):,.0f}")

print("\n✅ Cell 4A complete.")

# ── Pivot d_conversion (TOFU + BOFU combined) ────────────────────────────────
tofu_daily = defaultdict(lambda: defaultdict(float))
bofu_daily = defaultdict(lambda: defaultdict(float))

for row in raw_data["d_conversion"]:
    raw_date = row.get("Day of date_scaffold", "") or row.get("date_scaffold", "")
    measure_raw = row.get("Measure Names", "").strip()
    value_raw   = row.get("Measure Values", "0")

    if not raw_date or not measure_raw:
        continue

    date_str = parse_date(raw_date)

    if measure_raw.startswith("events_"):
        tofu_daily[date_str][measure_raw] += safe_float(value_raw)
    elif measure_raw.startswith("uuwp_"):
        bofu_daily[date_str][measure_raw] += safe_float(value_raw)

print(f"d_conversion parsed: {len(tofu_daily)} TOFU dates, {len(bofu_daily)} BOFU dates")
print(f"Available dates: {sorted(tofu_daily.keys())}")

# Show measures available
if tofu_daily:
    sample_date = sorted(tofu_daily.keys())[-1]
    print(f"\nMeasures in tofu_daily (sample date {sample_date}):")
    for k, v in tofu_daily[sample_date].items():
        print(f"  {k}: {v:,.0f}")

if bofu_daily:
    sample_date = sorted(bofu_daily.keys())[-1]
    print(f"\nMeasures in bofu_daily (sample date {sample_date}):")
    for k, v in bofu_daily[sample_date].items():
        print(f"  {k}: {v:,.0f}")

# ── Spot check key funnel fields for REPORT_DATE ─────────────────────────────
print(f"\n=== TOFU on REPORT_DATE ({report_date_str}) ===")
t = tofu_daily.get(report_date_str, {})
print(f"  App reachedFrom (events_app_vd_via_homepage_users):          {t.get('events_app_vd_via_homepage_users', 'MISSING'):>10}")
print(f"  App reachedNotFrom (events_app_reached_vds_not_from_homepage): {t.get('events_app_reached_vds_not_from_homepage', 'MISSING'):>8}")
print(f"  MP reachedFrom (events_mp_homepage_to_vds_users):             {t.get('events_mp_homepage_to_vds_users', 'MISSING'):>10}")
print(f"  MP reachedNotFrom (events_mp_j4y_to_vds_users):         {t.get('events_mp_j4y_to_vds_users', 'MISSING'):>10}")

print(f"\n=== BOFU on REPORT_DATE ({report_date_str}) ===")
b = bofu_daily.get(report_date_str, {})
print(f"  App purchasedFrom (uuwp_app_from_homepage):       {b.get('uuwp_app_from_homepage', 'MISSING'):>10}")
print(f"  App purchasedNotFrom (uuwp_app_not_from_homepage): {b.get('uuwp_app_not_from_homepage', 'MISSING'):>10}")
print(f"  MP purchasedFrom (uuwp_mp_from_homepage):         {b.get('uuwp_mp_from_homepage', 'MISSING'):>10}")
print(f"  MP purchasedFrom (uuwp_mp_j4y):         {b.get('uuwp_mp_j4y', 'MISSING'):>10}")
print(f"  MP purchasedNotFrom (uuwp_mp_not_from_homepage):  {b.get('uuwp_mp_not_from_homepage', 'MISSING'):>10}")
print(f"  Web purchasedFrom (uuwp_web_from_listingpage):    {b.get('uuwp_web_from_listingpage', 'MISSING'):>10}")
print(f"  Web purchasedNotFrom (uuwp_web_not_from_listingpage): {b.get('uuwp_web_not_from_listingpage', 'MISSING'):>10}")

print("\n✅ Cell 4B complete.")

# Current ISO week label — Tableau uses "Week {N}" format
current_week_label = f"Week {ISO_WEEK}"
print(f"Filtering weekly views to: '{current_week_label}'")

# ── Pivot w_conversion (TOFU + BOFU combined) ────────────────────────────────
tofu_wtd = defaultdict(float)
bofu_wtd = defaultdict(float)
weeks_found = set()

for row in raw_data["w_conversion"]:
    week_raw    = row.get("Week of date_scaffold", "").strip()
    measure_raw = row.get("Measure Names", "").strip()
    value_raw   = row.get("Measure Values", "0")

    weeks_found.add(week_raw)

    if week_raw != current_week_label:
        continue

    if measure_raw.startswith("events_"):
        tofu_wtd[measure_raw] += safe_float(value_raw)
    elif measure_raw.startswith("uuwp_"):
        bofu_wtd[measure_raw] += safe_float(value_raw)

print(f"\nw_conversion — weeks found: {sorted(weeks_found)}")
print(f"\nTOFU measures for {current_week_label}:")
for k, v in tofu_wtd.items():
    print(f"  {k}: {v:,.0f}")

print(f"\nBOFU measures for {current_week_label}:")
for k, v in bofu_wtd.items():
    print(f"  {k}: {v:,.0f}")

# ── Sanity check — warn if current week not found ────────────────────────────
if current_week_label not in weeks_found:
    print(f"\n⚠️  WARNING: '{current_week_label}' not found in w_conversion. WTD CR will be 0.")
    print(f"   Weeks available: {sorted(weeks_found)}")
else:
    print(f"\n✅ '{current_week_label}' found in w_conversion.")

print("\n✅ Cell 4C complete.")

print("=" * 60)
print("STEP 4 VALIDATION SUMMARY")
print("=" * 60)

checks = []

def check(label, condition, detail=""):
    status = "✅" if condition else "❌"
    msg = f"  {status} {label}"
    if detail:
        msg += f" ({detail})"
    print(msg)
    checks.append(condition)

print("\n--- d_transactions ---")
for date_str, label in [
    (report_date_str, "REPORT_DATE"),
    (date_1d_str,     "DATE_1D"),
    (prev_date_str,   "PREV_DATE (7D ago)"),
    (week_start_str,  "WEEK_START (Mon)"),
]:
    has_data = date_str in txn_by_date and txn_by_date[date_str].get("GTV", 0) > 0
    gtv = txn_by_date.get(date_str, {}).get("GTV", 0)
    check(f"{label} ({date_str}) has GTV", has_data, f"₱{gtv:,.0f}")

print("\n--- d_conversion (daily funnel) ---")
for date_str, label in [
    (report_date_str, "REPORT_DATE"),
    (date_1d_str,     "DATE_1D"),
    (prev_date_str,   "PREV_DATE"),
]:
    has_data = date_str in tofu_daily and len(tofu_daily[date_str]) > 0
    check(f"{label} ({date_str}) has TOFU data", has_data,
          f"{len(tofu_daily.get(date_str, {}))} measures")

for date_str, label in [
    (report_date_str, "REPORT_DATE"),
    (date_1d_str,     "DATE_1D"),
    (prev_date_str,   "PREV_DATE"),
]:
    has_data = date_str in bofu_daily and len(bofu_daily[date_str]) > 0
    check(f"{label} ({date_str}) has BOFU data", has_data,
          f"{len(bofu_daily.get(date_str, {}))} measures")

print("\n--- Weekly views (WTD) ---")
check(f"w_conversion TOFU has data for {current_week_label}",
      len(tofu_wtd) > 0, f"{len(tofu_wtd)} measures")
check(f"w_conversion BOFU has data for {current_week_label}",
      len(bofu_wtd) > 0, f"{len(bofu_wtd)} measures")

print("\n--- Key measure presence ---")
check("App TOFU reachedFrom present",
      "events_app_vd_via_homepage_users" in tofu_daily.get(report_date_str, {}))
check("App BOFU purchasedFrom present",
      "uuwp_app_from_homepage" in bofu_daily.get(report_date_str, {}))
check("MP Gdeals TOFU reachedFrom present",
      "events_mp_homepage_to_vds_users" in tofu_daily.get(report_date_str, {}))
check("MP J4Y TOFU reachedFrom present",
      "events_mp_j4y_to_vds_users" in tofu_daily.get(report_date_str, {}))      
check("Web BOFU purchasedFrom present",
      "uuwp_web_from_listingpage" in bofu_daily.get(report_date_str, {}))

print("\n" + "=" * 60)
passed = sum(checks)
total  = len(checks)
print(f"  {passed}/{total} checks passed")

if passed == total:
    print("  ✅ All checks passed — ready for Step 5 (metric computation)")
else:
    print("  ⚠️  Some checks failed — review missing dates/measures above before proceeding")
print("=" * 60)

SOURCES = ["App", "Web", "MP"]

def get_gtv(date_str, source=None):
    if source:
        return txn_by_date_source.get((date_str, source), {}).get("GTV", 0.0)
    return txn_by_date.get(date_str, {}).get("GTV", 0.0)

def get_purchases(date_str, source=None):
    if source:
        return txn_by_date_source.get((date_str, source), {}).get("Purchases", 0.0)
    return txn_by_date.get(date_str, {}).get("Purchases", 0.0)

gtv_current = {"Total": get_gtv(report_date_str)}
gtv_vs1d    = {"Total": get_gtv(date_1d_str)}
gtv_vs7d    = {"Total": get_gtv(prev_date_str)}

for src in SOURCES:
    gtv_current[src] = get_gtv(report_date_str, src)
    gtv_vs1d[src]    = get_gtv(date_1d_str, src)
    gtv_vs7d[src]    = get_gtv(prev_date_str, src)

gtv_wtd = {"Total": 0.0, "App": 0.0, "Web": 0.0, "MP": 0.0}
current_day = WEEK_START
while current_day <= REPORT_DATE:
    d = current_day.strftime("%Y-%m-%d")
    gtv_wtd["Total"] += get_gtv(d)
    for src in SOURCES:
        gtv_wtd[src] += get_gtv(d, src)
    current_day += timedelta(days=1)

print("=== GTV ===")
print(f"{'':6} {'Total':>12} {'App':>12} {'Web':>12} {'MP':>12}")
for label, d in [("Latest", gtv_current), ("vs1d", gtv_vs1d), ("vs7d", gtv_vs7d), ("WTD", gtv_wtd)]:
    print(f"{label:6} {d['Total']:>12,.0f} {d['App']:>12,.0f} {d['Web']:>12,.0f} {d['MP']:>12,.0f}")

print("\n✅ Cell 5A complete.")

daily_gtv     = {"Total": [], "App": [], "Web": [], "MP": []}
daily_future  = []
daily_dates   = []
daily_days    = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

for i in range(7):
    day_date  = WEEK_START + timedelta(days=i)
    day_str   = day_date.strftime("%Y-%m-%d")
    is_future = day_date > REPORT_DATE

    daily_future.append(is_future)
    daily_dates.append(day_date.strftime("%b %-d"))

    if is_future:
        daily_gtv["Total"].append(0)
        for src in SOURCES:
            daily_gtv[src].append(0)
    else:
        daily_gtv["Total"].append(round(get_gtv(day_str), 2))
        for src in SOURCES:
            daily_gtv[src].append(round(get_gtv(day_str, src), 2))

wtd_label = f"{WEEK_START.strftime('%b %-d')}–{REPORT_DATE.strftime('%b %-d')}"

print("=== Daily Waterfall ===")
print(f"{'Day':4} {'Date':8} {'Future':7} {'Total':>10} {'App':>10} {'Web':>10} {'MP':>10}")
for i in range(7):
    print(f"{daily_days[i]:4} {daily_dates[i]:8} {str(daily_future[i]):7} "
          f"{daily_gtv['Total'][i]:>10,.0f} {daily_gtv['App'][i]:>10,.0f} "
          f"{daily_gtv['Web'][i]:>10,.0f} {daily_gtv['MP'][i]:>10,.0f}")

print(f"\nWTD Label: {wtd_label}")
print("\n✅ Cell 5B complete.")

gtv_target = WEEKLY_TARGETS.get(ISO_WEEK)

if not gtv_target:
    print(f"⚠️  WARNING: No target found for ISO Week {ISO_WEEK}.")
    print(f"   Add Wk {ISO_WEEK} to WEEKLY_TARGETS.")
    gtv_target = {"Total": 0, "App": 0, "Web": 0, "MP": 0}
else:
    print(f"=== Weekly Targets — ISO Week {ISO_WEEK} ===")
    for k, v in gtv_target.items():
        pct = (gtv_wtd[k] / v * 100) if v > 0 else 0
        print(f"  {k:6}: Target ₱{v:>12,.0f}  |  WTD ₱{gtv_wtd[k]:>10,.0f}  |  {pct:.1f}% achieved")

print("\n✅ Cell 5C complete.")

def calc_atv(gtv, purchases):
    return round(gtv / purchases, 2) if purchases > 0 else 0

wtd_dates = [
    (WEEK_START + timedelta(days=i)).strftime("%Y-%m-%d")
    for i in range((REPORT_DATE - WEEK_START).days + 1)
]

atv = {}
for src in SOURCES:
    wtd_purchases = sum(get_purchases(d, src) for d in wtd_dates)
    atv[src] = {
        "Latest": calc_atv(get_gtv(report_date_str, src), get_purchases(report_date_str, src)),
        "1D":     calc_atv(get_gtv(date_1d_str, src),     get_purchases(date_1d_str, src)),
        "7D":     calc_atv(get_gtv(prev_date_str, src),   get_purchases(prev_date_str, src)),
        "WTD":    calc_atv(gtv_wtd[src], wtd_purchases),
    }

wtd_total_purchases = sum(get_purchases(d) for d in wtd_dates)
atv["Total"] = {
    "Latest": calc_atv(gtv_current["Total"], get_purchases(report_date_str)),
    "1D":     calc_atv(gtv_vs1d["Total"],    get_purchases(date_1d_str)),
    "7D":     calc_atv(gtv_vs7d["Total"],    get_purchases(prev_date_str)),
    "WTD":    calc_atv(gtv_wtd["Total"],     wtd_total_purchases),
}

print("=== ATV ===")
print(f"{'':8} {'Latest':>10} {'1D':>10} {'7D':>10} {'WTD':>10}")
for src in ["Total", "App", "Web", "MP"]:
    d = atv[src]
    print(f"{src:8} {d['Latest']:>10,.0f} {d['1D']:>10,.0f} {d['7D']:>10,.0f} {d['WTD']:>10,.0f}")

print("\n✅ Cell 5D complete.")

def calc_cr(numerator, denominator):
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)

def get_app_cr(date_str):
    t = tofu_daily.get(date_str, {})
    b = bofu_daily.get(date_str, {})
    num = safe_float(b.get("uuwp_app_from_homepage", 0)) + safe_float(b.get("uuwp_app_not_from_homepage", 0))
    den = safe_float(t.get("events_app_vd_via_homepage_users", 0)) + safe_float(t.get("events_app_reached_vds_not_from_homepage", 0))
    return calc_cr(num, den)

def get_mp_cr(date_str):
    t = tofu_daily.get(date_str, {})
    b = bofu_daily.get(date_str, {})
    num = safe_float(b.get("uuwp_mp_from_homepage", 0)) + safe_float(b.get("uuwp_mp_j4y", 0))
    den = safe_float(t.get("events_mp_homepage_to_vds_users", 0)) + safe_float(t.get("events_mp_j4y_to_vds_users", 0))
    return calc_cr(num, den)

def get_wtd_app_cr():
    num = safe_float(bofu_wtd.get("uuwp_app_from_homepage", 0)) + safe_float(bofu_wtd.get("uuwp_app_not_from_homepage", 0))
    den = safe_float(tofu_wtd.get("events_app_vd_via_homepage_users", 0)) + safe_float(tofu_wtd.get("events_app_reached_vds_not_from_homepage", 0))
    return calc_cr(num, den)

def get_wtd_mp_cr():
    num = safe_float(bofu_wtd.get("uuwp_mp_from_homepage", 0)) + safe_float(bofu_wtd.get("uuwp_mp_j4y", 0))
    den = safe_float(tofu_wtd.get("events_mp_homepage_to_vds_users", 0)) + safe_float(tofu_wtd.get("events_mp_j4y_to_vds_users", 0))
    return calc_cr(num, den)

conv = {
    "App": {"Latest": get_app_cr(report_date_str), "1D": get_app_cr(date_1d_str), "7D": get_app_cr(prev_date_str), "WTD": get_wtd_app_cr()},
    "Web": {"Latest": 0, "1D": 0, "7D": 0, "WTD": 0},  # filled in Step 6
    "MP":  {"Latest": get_mp_cr(report_date_str),  "1D": get_mp_cr(date_1d_str),  "7D": get_mp_cr(prev_date_str),  "WTD": get_wtd_mp_cr()},
}

conv_mock = {
    "Latest": tofu_daily.get(report_date_str) is None,
    "1D":     tofu_daily.get(date_1d_str) is None,
    "7D":     tofu_daily.get(prev_date_str) is None,
    "WTD":    len(tofu_wtd) == 0,
}

print("=== Conversion Rates (%) ===")
print(f"{'':6} {'Latest':>8} {'1D':>8} {'7D':>8} {'WTD':>8}")
for src in ["App", "Web", "MP"]:
    d = conv[src]
    note = " ← GA4 pending" if src == "Web" else ""
    print(f"{src:6} {d['Latest']:>8.2f} {d['1D']:>8.2f} {d['7D']:>8.2f} {d['WTD']:>8.2f}{note}")

print(f"\nconvMock: {conv_mock}")
print("\n✅ Cell 5E complete.")

wtd_dates = [
    (WEEK_START + timedelta(days=i)).strftime("%Y-%m-%d")
    for i in range((REPORT_DATE - WEEK_START).days + 1)
]

# ── Step 1: Get merchants with transactions on REPORT_DATE only ──────────────
report_date_merchants = set()
for (date_str, source, merchant) in txn.keys():
    if date_str == report_date_str:
        report_date_merchants.add((source, merchant))

print(f"Merchants active on REPORT_DATE: {len(report_date_merchants)}")

# ── Step 2: For each REPORT_DATE merchant, look up 1D, 7D, WTD ──────────────
merchants = {"Total": {}, "App": {}, "Web": {}, "MP": {}}

for (source, merchant) in report_date_merchants:
    latest  = txn.get((report_date_str, source, merchant), {}).get("GTV", None)
    gtv_1d  = txn.get((date_1d_str,    source, merchant), {}).get("GTV", None)
    gtv_7d  = txn.get((prev_date_str,  source, merchant), {}).get("GTV", None)
    wtd_val = sum(txn.get((d, source, merchant), {}).get("GTV", 0) for d in wtd_dates)

    record = {
        "name":   merchant,
        "Latest": round(latest, 2) if latest else None,
        "1D":     round(gtv_1d, 2) if gtv_1d else None,
        "7D":     round(gtv_7d, 2) if gtv_7d else None,
        "WTD":    round(wtd_val, 2),
    }
    merchants[source][merchant] = record

    if merchant not in merchants["Total"]:
        merchants["Total"][merchant] = {"name": merchant, "Latest": 0.0, "1D": 0.0, "7D": 0.0, "WTD": 0.0}
    t = merchants["Total"][merchant]
    t["Latest"] = (t["Latest"] or 0) + (latest or 0)
    t["1D"]     = (t["1D"] or 0)     + (gtv_1d or 0)
    t["7D"]     = (t["7D"] or 0)     + (gtv_7d or 0)
    t["WTD"]    = (t["WTD"] or 0)    + wtd_val

# ── Null-out zeros on Total (no transactions = null, not 0) ─────────────────
for m in merchants["Total"].values():
    if m["Latest"] == 0: m["Latest"] = None
    if m["1D"] == 0:     m["1D"]     = None
    if m["7D"] == 0:     m["7D"]     = None

# ── Sort by REPORT_DATE GTV desc ─────────────────────────────────────────────
merchants_list = {
    src: sorted(merchants[src].values(), key=lambda r: r["Latest"] or 0, reverse=True)
    for src in ["Total", "App", "Web", "MP"]
}

print("\n=== Merchant counts per source ===")
for src in ["Total", "App", "Web", "MP"]:
    total_m  = len(merchants_list[src])
    active_m = sum(1 for m in merchants_list[src] if m["Latest"])
    print(f"  {src:6}: {total_m} merchants ({active_m} with REPORT_DATE GTV)")

print("\n=== Top 5 App merchants (Latest GTV) ===")
for m in merchants_list["App"][:5]:
    print(f"  {m['name']:35} Latest={m['Latest'] or 0:>10,.0f}  WTD={m['WTD']:>10,.0f}")

print("\n✅ Cell 5F complete.")

print("=" * 60)
print("STEP 5 VALIDATION SUMMARY")
print("=" * 60)

checks = []
def check(label, condition, detail=""):
    status = "✅" if condition else "❌"
    msg = f"  {status} {label}"
    if detail: msg += f" ({detail})"
    print(msg)
    checks.append(condition)

print("\n--- GTV ---")
check("GTV current Total > 0",  gtv_current["Total"] > 0, f"₱{gtv_current['Total']:,.0f}")
check("GTV vs1d Total > 0",     gtv_vs1d["Total"] > 0,    f"₱{gtv_vs1d['Total']:,.0f}")
check("GTV vs7d Total > 0",     gtv_vs7d["Total"] > 0,    f"₱{gtv_vs7d['Total']:,.0f}")
check("GTV WTD Total > 0",      gtv_wtd["Total"] > 0,     f"₱{gtv_wtd['Total']:,.0f}")
check("Weekly target loaded",   gtv_target["Total"] > 0,  f"₱{gtv_target['Total']:,.0f}")

print("\n--- Daily waterfall ---")
complete_days = [i for i, f in enumerate(daily_future) if not f]
future_days   = [i for i, f in enumerate(daily_future) if f]
check("Complete days have GTV > 0", all(daily_gtv["Total"][i] > 0 for i in complete_days), f"{len(complete_days)} days")
check("Future days have GTV = 0",   all(daily_gtv["Total"][i] == 0 for i in future_days),  f"{len(future_days)} days")
check("7 days in waterfall",        len(daily_gtv["Total"]) == 7)

print("\n--- ATV ---")
check("ATV Total Latest > 0", atv["Total"]["Latest"] > 0, f"₱{atv['Total']['Latest']:,.0f}")
check("ATV App Latest > 0",   atv["App"]["Latest"] > 0,   f"₱{atv['App']['Latest']:,.0f}")

print("\n--- Conversion rates ---")
check("App CR Latest > 0",          conv["App"]["Latest"] > 0,  f"{conv['App']['Latest']:.2f}%")
check("App CR WTD > 0",             conv["App"]["WTD"] > 0,     f"{conv['App']['WTD']:.2f}%")
check("MP CR Latest >= 0",          conv["MP"]["Latest"] >= 0,  f"{conv['MP']['Latest']:.2f}%")
check("Web CR = 0 (GA4 pending)",   conv["Web"]["Latest"] == 0, "filled in Step 6")

print("\n--- Merchants ---")
check("App merchants > 0",    len(merchants_list["App"]) > 0,   f"{len(merchants_list['App'])} merchants")
check("Total merchants > 0",  len(merchants_list["Total"]) > 0, f"{len(merchants_list['Total'])} merchants")
check("No empty merchant arrays", all(len(merchants_list[s]) > 0 for s in ["Total","App"]))

print("\n" + "=" * 60)
passed = sum(checks)
total  = len(checks)
print(f"  {passed}/{total} checks passed")
if passed == total:
    print("  ✅ All checks passed — ready for Step 6 (GA4 Web CR)")
else:
    print("  ⚠️  Some checks failed — review above before proceeding")
print("=" * 60)

import google.auth
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Metric, FilterExpression,
    Filter, MetricAggregation
)
import os

GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")

# Use Application Default Credentials from gcloud
credentials, project = google.auth.default(
    scopes=["https://www.googleapis.com/auth/analytics.readonly"]
)

ga4_client = BetaAnalyticsDataClient(credentials=credentials)

print(f"✅ GA4 client ready")
print(f"   Property ID: {GA4_PROPERTY_ID}")
print(f"   Project:     {project}")
print(f"   Credentials: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")

request = RunReportRequest(
    property=f"properties/{GA4_PROPERTY_ID}",
    date_ranges=[
        DateRange(start_date=report_date_str, end_date=report_date_str, name="Latest"),
        DateRange(start_date=date_1d_str,     end_date=date_1d_str,     name="1D"),
        DateRange(start_date=prev_date_str,   end_date=prev_date_str,   name="7D"),
        DateRange(start_date=week_start_str,  end_date=report_date_str, name="WTD"),
    ],
    metrics=[Metric(name="activeUsers")],
    dimension_filter=FilterExpression(
        filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="voucher_details_view",
                case_sensitive=True,
            )
        )
    ),
)

response = ga4_client.run_report(request)

ga4_active_users = {"Latest": 0, "1D": 0, "7D": 0, "WTD": 0}

for i, row in enumerate(response.rows):
    value = int(row.metric_values[0].value)
    print(f"Row {i}: {value}")

# With multiple named date ranges and no dimensions,
# rows come back in order: Latest, 1D, 7D, WTD
period_order = ["Latest", "1D", "7D", "WTD"]
for i, row in enumerate(response.rows):
    if i < len(period_order):
        ga4_active_users[period_order[i]] = int(row.metric_values[0].value)

print("\n=== GA4 voucher_details_view activeUsers ===")
for period, val in ga4_active_users.items():
    print(f"  {period:6}: {val:>8,}")

if ga4_active_users["Latest"] == 0:
    print("\n⚠️  WARNING: Latest = 0 — GA4 ingestion delay.")
else:
    print("\n✅ GA4 data looks good.")

def get_web_bofu_numerator(date_str):
    b = bofu_daily.get(date_str, {})
    return safe_float(b.get("uuwp_web_from_listingpage", 0)) + \
           safe_float(b.get("uuwp_web_not_from_listingpage", 0))

def get_wtd_web_bofu_numerator():
    return safe_float(bofu_wtd.get("uuwp_web_from_listingpage", 0)) + \
           safe_float(bofu_wtd.get("uuwp_web_not_from_listingpage", 0))

# Web CR = BOFU numerator / GA4 activeUsers
web_cr_latest = calc_cr(get_web_bofu_numerator(report_date_str), ga4_active_users["Latest"])
web_cr_1d     = calc_cr(get_web_bofu_numerator(date_1d_str),     ga4_active_users["1D"])
web_cr_7d     = calc_cr(get_web_bofu_numerator(prev_date_str),   ga4_active_users["7D"])
web_cr_wtd    = calc_cr(get_wtd_web_bofu_numerator(),            ga4_active_users["WTD"])

# Fill into conv dict (was 0 placeholder from Step 5E)
conv["Web"]["Latest"] = web_cr_latest
conv["Web"]["1D"]     = web_cr_1d
conv["Web"]["7D"]     = web_cr_7d
conv["Web"]["WTD"]    = web_cr_wtd

# Flag for GA4 delay
ga4_delayed = ga4_active_users["Latest"] == 0

print("=== Final Conversion Rates (%) ===")
print(f"{'':6} {'Latest':>8} {'1D':>8} {'7D':>8} {'WTD':>8}")
for src in ["App", "Web", "MP"]:
    d = conv[src]
    note = " ← GA4 DELAYED" if src == "Web" and ga4_delayed else ""
    print(f"{src:6} {d['Latest']:>8.2f} {d['1D']:>8.2f} {d['7D']:>8.2f} {d['WTD']:>8.2f}{note}")

print(f"\nGA4 delayed flag: {ga4_delayed}")
print("\n✅ Cell 6C complete — Web CR filled. Ready for Step 7 (JSON assembly).")

# ── Meta ────────────────────────────────────────────────────────────────────
report_json = {
    "meta": {
        "generatedAt":    datetime.now().isoformat(),
        "source":         "growth_raw_ds_v4",
        "reportDate":     report_date_str,
        "reportDayLabel": REPORT_DAY_LABEL,
        "prevDate":       prev_date_str,
        "prevDayLabel":   PREV_DAY_LABEL,
        "weekLabel":      WEEK_LABEL,
        "weekNumber":     ISO_WEEK,
    },

    # ── GTV ─────────────────────────────────────────────────────────────────
    "gtv": {
        "current": {k: round(v, 2) for k, v in gtv_current.items()},
        "vs1d":    {k: round(v, 2) for k, v in gtv_vs1d.items()},
        "vs7d":    {k: round(v, 2) for k, v in gtv_vs7d.items()},
        "wtd":     {k: round(v, 2) for k, v in gtv_wtd.items()},
        "target":  gtv_target,

        # ── Daily waterfall ──────────────────────────────────────────────────
        "daily": {
            "Total": daily_gtv["Total"],
            "App":   daily_gtv["App"],
            "Web":   daily_gtv["Web"],
            "MP":    daily_gtv["MP"],
        },
        "future":   daily_future,
        "days":     daily_days,
        "dates":    daily_dates,
        "wtdLabel": wtd_label,

        # ── Conversion rates ─────────────────────────────────────────────────
        "conv": {
            "App": conv["App"],
            "Web": conv["Web"],
            "MP":  conv["MP"],
        },
        "convMock": conv_mock,

        # ── Merchants ────────────────────────────────────────────────────────
        "merchants": {
            "Total": merchants_list["Total"],
            "App":   merchants_list["App"],
            "Web":   merchants_list["Web"],
            "MP":    merchants_list["MP"],
        },
        "merchantMock": {
            "Total": False,
            "App":   False,
            "Web":   False,
            "MP":    False,
        },

        # ── ATV ──────────────────────────────────────────────────────────────
        "atv": {
            "Total": atv["Total"],
            "App":   atv["App"],
            "Web":   atv["Web"],
            "MP":    atv["MP"],
        },
        "atvMock": False,
    }
}

# ── Validate JSON is serialisable ────────────────────────────────────────────
try:
    json_str = json.dumps(report_json, indent=2, ensure_ascii=False)
    print(f"✅ JSON serialised successfully")
    print(f"   Size: {len(json_str):,} characters")
except Exception as e:
    print(f"❌ JSON serialisation failed: {e}")
    raise

# ── Spot check key values ────────────────────────────────────────────────────
print(f"\n=== JSON Spot Check ===")
print(f"  reportDate:      {report_json['meta']['reportDate']}")
print(f"  reportDayLabel:  {report_json['meta']['reportDayLabel']}")
print(f"  weekNumber:      {report_json['meta']['weekNumber']}")
print(f"  GTV current:     ₱{report_json['gtv']['current']['Total']:,.0f}")
print(f"  GTV WTD:         ₱{report_json['gtv']['wtd']['Total']:,.0f}")
print(f"  Target:          ₱{report_json['gtv']['target']['Total']:,.0f}")
print(f"  App CR Latest:   {report_json['gtv']['conv']['App']['Latest']}%")
print(f"  Web CR Latest:   {report_json['gtv']['conv']['Web']['Latest']}%")
print(f"  MP CR Latest:    {report_json['gtv']['conv']['MP']['Latest']}%")
print(f"  ATV Total:       ₱{report_json['gtv']['atv']['Total']['Latest']:,.0f}")
print(f"  Merchants App:   {len(report_json['gtv']['merchants']['App'])} records")
print(f"  Merchants Total: {len(report_json['gtv']['merchants']['Total'])} records")
print(f"  Waterfall days:  {report_json['gtv']['days']}")
print(f"  Waterfall dates: {report_json['gtv']['dates']}")
print(f"  Future flags:    {report_json['gtv']['future']}")

print("\n✅ Step 7 complete — ready for Step 8 (HTML injection).")


OUTPUT_PATH   = f"{OUTPUT_DIR}/report_{report_date_str}.html"

if not os.path.exists(TEMPLATE_PATH):
    raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ── Find the script block boundaries and replace content directly ─────────
OPEN_TAG  = '<script id="report-data" type="application/json">'
CLOSE_TAG = '</script>'

start_idx = html.find(OPEN_TAG)
if start_idx == -1:
    raise ValueError('Could not find <script id="report-data"> block in template.')

content_start = start_idx + len(OPEN_TAG)
content_end   = html.find(CLOSE_TAG, content_start)
if content_end == -1:
    raise ValueError('Could not find closing </script> tag for report-data block.')

# Replace only the content between the tags — no regex, no escape issues
new_html = html[:content_start] + "\n" + json_str + "\n" + html[content_end:]

print(f"✅ Injected JSON ({len(json_str):,} chars) into report-data block")

# ── GA4 delay note ────────────────────────────────────────────────────────
if ga4_delayed:
    delay_note = '<div style="font-size:10px;color:#8899a6;font-style:italic;margin-top:4px">* There\'s a delay in GA4 data and this is expected.</div>'
    new_html = new_html.replace('</body>', f'{delay_note}\n</body>')
    print("⚠️  GA4 delay note added")

# ── Save ──────────────────────────────────────────────────────────────────
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(new_html)

print(f"✅ Report saved: {OUTPUT_PATH}")
print(f"   File size: {os.path.getsize(OUTPUT_PATH):,} bytes")
print(f"\n👉 Open in Chrome to verify: {OUTPUT_PATH}")

import asyncio
from playwright.async_api import async_playwright

OUTPUT_PNG = f"/Users/ClarkLlorador/Documents/claude_projects/output/growth_daily_reports/report_{report_date_str}.png"

async def screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-web-security"])
        page = await browser.new_page(viewport={"width": 1200, "height": 900})
        
        await page.goto(f"file://{OUTPUT_PATH}")
        
        # Wait for page to fully load first, then React to render
        await page.wait_for_load_state("networkidle")
        await page.wait_for_selector("#dgr-report", timeout=30000)
        await page.wait_for_timeout(1500)
        
        report = await page.query_selector("#dgr-report")
        box = await report.bounding_box()
        print(f"Report bounding box: {box}")
        
        await page.set_viewport_size({
            "width":  int(box["width"]) + 40,
            "height": int(box["height"]) + 40
        })
        await page.wait_for_timeout(300)
        
        report = await page.query_selector("#dgr-report")
        await report.screenshot(path=OUTPUT_PNG)
        await browser.close()

# asyncio.run(screenshot())

await screenshot()

import os
print(f"\n✅ Screenshot saved: {OUTPUT_PNG}")
print(f"   File size: {os.path.getsize(OUTPUT_PNG):,} bytes")

SLACK_BOT_TOKEN  = os.getenv("SLACK_BOT_TOKEN")

headers = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    "Content-Type": "application/json"
}

# Post anchor message
anchor_resp = requests.post(
    "https://slack.com/api/chat.postMessage",
    headers=headers,
    json={
        "channel": SLACK_CHANNEL_ID,
        "text": f"Growth Daily Report - As of {report_date_str}"
    }
)

anchor_data = anchor_resp.json()

if not anchor_data.get("ok"):
    raise Exception(f"Failed to post anchor message: {anchor_data.get('error')}")

anchor_thread_ts = anchor_data["ts"]
print(f"✅ Anchor message posted")
print(f"   Thread TS: {anchor_thread_ts}")

def slack_upload_file(token, channel_id, thread_ts, filepath, filename, comment):
    """Upload a file to Slack using the new 2-step API (files.upload is deprecated)."""
    
    # Step 1 — Get upload URL
    with open(filepath, "rb") as f:
        file_bytes = f.read()
    
    url_resp = requests.post(
        "https://slack.com/api/files.getUploadURLExternal",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "filename": filename,
            "length": len(file_bytes),
        }
    ).json()
    
    if not url_resp.get("ok"):
        raise Exception(f"Failed to get upload URL: {url_resp.get('error')}")
    
    upload_url = url_resp["upload_url"]
    file_id    = url_resp["file_id"]
    
    # Step 2 — Upload file bytes to the URL
    upload_resp = requests.post(
        upload_url,
        data=file_bytes,
        headers={"Content-Type": "application/octet-stream"}
    )
    
    if upload_resp.status_code != 200:
        raise Exception(f"Failed to upload file bytes: {upload_resp.status_code}")
    
    # Step 3 — Complete the upload and share to channel/thread
    complete_resp = requests.post(
        "https://slack.com/api/files.completeUploadExternal",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={
            "files": [{"id": file_id}],
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "initial_comment": comment,
        }
    ).json()
    
    if not complete_resp.get("ok"):
        raise Exception(f"Failed to complete upload: {complete_resp.get('error')}")
    
    return file_id

### SLACK CAPTION ###

gtv_diff     = gtv_current["Total"] - gtv_vs1d["Total"]
gtv_diff_pct = round((gtv_diff / gtv_vs1d["Total"]) * 100) if gtv_vs1d["Total"] else 0

if gtv_diff >= 0:
    top3 = [m for m in merchants_list["Total"][:3] if m["Latest"]]
    merchant_str = ", ".join([f"{m['name']} (₱{m['Latest']/1000:.1f}K)" for m in top3])
    caption = f"GTV came in at ₱{gtv_current['Total']/1000:.0f}K on {REPORT_DAY_LABEL}, up from ₱{gtv_vs1d['Total']/1000:.0f}K the day prior (+₱{gtv_diff/1000:.1f}K, +{gtv_diff_pct}%). {merchant_str} led today's transactions. App CR: {conv['App']['Latest']:.2f}%, Web: {conv['Web']['Latest']:.2f}%, MP: {conv['MP']['Latest']:.2f}%."
else:
    losers = sorted(
        [m for m in merchants_list["Total"] if m["Latest"] and m["1D"] and m["Latest"] < m["1D"]],
        key=lambda m: m["Latest"] - m["1D"]
    )[:3]
    loser_str = ", ".join([f"{m['name']} (-₱{(m['1D']-m['Latest'])/1000:.1f}K)" for m in losers])
    caption = f"GTV came in at ₱{gtv_current['Total']/1000:.0f}K on {REPORT_DAY_LABEL}, down from ₱{gtv_vs1d['Total']/1000:.0f}K the day prior (₱{gtv_diff/1000:.1f}K, {gtv_diff_pct}%). Top losers vs 1D: {loser_str}. App CR: {conv['App']['Latest']:.2f}%, Web: {conv['Web']['Latest']:.2f}%, MP: {conv['MP']['Latest']:.2f}%."

print(f"✅ Caption:\n{caption}")

# ── Upload PNG ───────────────────────────────────────────────────────────────
# caption = f"📊 Growth Daily Report — {REPORT_DAY_LABEL} | GTV ₱{gtv_current['Total']/1000:.0f}K | [Claude caption coming soon]"

file_id = slack_upload_file(
    token      = SLACK_BOT_TOKEN,
    channel_id = SLACK_CHANNEL_ID,
    thread_ts  = anchor_thread_ts,
    filepath   = OUTPUT_PNG,
    filename   = f"report_{report_date_str}.png",
    comment    = caption,
)

print(f"✅ PNG uploaded — file_id: {file_id}")

file_id = slack_upload_file(
    token      = SLACK_BOT_TOKEN,
    channel_id = SLACK_CHANNEL_ID,
    thread_ts  = anchor_thread_ts,
    filepath   = OUTPUT_PATH,
    filename   = f"report_{report_date_str}.html",
    comment    = "Download the HTML File for the Interactive Dashboard. Open in Chrome for best experience.",
)

print(f"✅ HTML uploaded — file_id: {file_id}")
print(f"\n🎉 Step 10 complete — full report delivered to #tests_claude_daily_updates")



