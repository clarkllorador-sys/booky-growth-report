"""
generate_dummy_data.py

Generates a sample JSON payload matching the Booky daily growth report schema,
then injects it into inputs/MAIN_TEMPLATE.html to produce outputs/sample_report.html.

REPORT_DATE: 2026-04-09 (Thursday, Week 15)
"""

import json
import random
import re
from datetime import datetime, date
from pathlib import Path

random.seed(42)

ROOT = Path(__file__).parent.parent
TEMPLATE_PATH = ROOT / "inputs" / "MAIN_TEMPLATE.html"
OUTPUT_PATH = ROOT / "outputs" / "sample_report.html"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_gtv(base, spread=0.12):
    """Return a random GTV value near base with ±spread variance."""
    return round(base * (1 + random.uniform(-spread, spread)), 2)


def split_by_source(total):
    """Split a total GTV into App/Web/MP at ~85/10/5."""
    app = round(total * random.uniform(0.83, 0.87), 2)
    web = round(total * random.uniform(0.09, 0.11), 2)
    mp  = round(total - app - web, 2)
    return app, web, mp


def make_gtv_day(base_total):
    total = rand_gtv(base_total)
    app, web, mp = split_by_source(total)
    return {"Total": total, "App": app, "Web": web, "MP": mp}


def rand_cr(lo, hi):
    return round(random.uniform(lo, hi), 2)


def rand_atv(lo, hi):
    return round(random.uniform(lo, hi), 2)


# ---------------------------------------------------------------------------
# Daily GTV  (Mon Apr 6 → Thu Apr 9 are complete; Fri–Sun are future=0)
# ---------------------------------------------------------------------------

DAILY_BASES = [148000, 142000, 155000, 151000]  # Mon Tue Wed Thu

days_data = [make_gtv_day(b) for b in DAILY_BASES]

# Separate arrays per source
daily_total = [d["Total"] for d in days_data] + [0, 0, 0]
daily_app   = [d["App"]   for d in days_data] + [0, 0, 0]
daily_web   = [d["Web"]   for d in days_data] + [0, 0, 0]
daily_mp    = [d["MP"]    for d in days_data] + [0, 0, 0]

# Current = Thu Apr 9 (index 3)
cur = days_data[3]
current = {"Total": cur["Total"], "App": cur["App"], "Web": cur["Web"], "MP": cur["MP"]}

# vs1d = Wed Apr 8 (index 2)
d1 = days_data[2]
vs1d = {"Total": d1["Total"], "App": d1["App"], "Web": d1["Web"], "MP": d1["MP"]}

# vs7d = Thu Apr 2 (same weekday last week) — generate separately
vs7d_base = 149000
vs7d_day = make_gtv_day(vs7d_base)
vs7d = {"Total": vs7d_day["Total"], "App": vs7d_day["App"], "Web": vs7d_day["Web"], "MP": vs7d_day["MP"]}

# WTD = Mon–Thu sum
wtd = {
    "Total": round(sum(daily_total[:4]), 2),
    "App":   round(sum(daily_app[:4]), 2),
    "Web":   round(sum(daily_web[:4]), 2),
    "MP":    round(sum(daily_mp[:4]), 2),
}

# ---------------------------------------------------------------------------
# Conversion rates
# ---------------------------------------------------------------------------

conv = {
    "App": {
        "Latest": rand_cr(7.0, 9.0),
        "1D":     rand_cr(7.0, 9.0),
        "7D":     rand_cr(7.0, 9.0),
        "WTD":    rand_cr(7.0, 9.0),
    },
    "Web": {
        "Latest": rand_cr(2.0, 3.0),
        "1D":     rand_cr(2.0, 3.0),
        "7D":     rand_cr(2.0, 3.0),
        "WTD":    rand_cr(2.0, 3.0),
    },
    "MP": {
        "Latest": rand_cr(0.3, 0.5),
        "1D":     rand_cr(0.3, 0.5),
        "7D":     rand_cr(0.3, 0.5),
        "WTD":    rand_cr(0.3, 0.5),
    },
}

# ---------------------------------------------------------------------------
# ATV
# ---------------------------------------------------------------------------

def make_atv(lo, hi):
    return {"Latest": rand_atv(lo, hi), "1D": rand_atv(lo, hi), "7D": rand_atv(lo, hi), "WTD": rand_atv(lo, hi)}

atv_app = make_atv(350, 420)
atv_web = make_atv(280, 350)
atv_mp  = make_atv(200, 260)

# Total ATV: weighted by GTV and purchases across sources
# purchases ≈ GTV / ATV per period
def total_atv(period):
    app_gtv = current["App"] if period == "Latest" else (vs1d["App"] if period == "1D" else (vs7d["App"] if period == "7D" else wtd["App"]))
    web_gtv = current["Web"] if period == "Latest" else (vs1d["Web"] if period == "1D" else (vs7d["Web"] if period == "7D" else wtd["Web"]))
    mp_gtv  = current["MP"]  if period == "Latest" else (vs1d["MP"]  if period == "1D" else (vs7d["MP"]  if period == "7D" else wtd["MP"]))
    app_a = atv_app[period]
    web_a = atv_web[period]
    mp_a  = atv_mp[period]
    total_g = app_gtv + web_gtv + mp_gtv
    total_p = (app_gtv / app_a) + (web_gtv / web_a) + (mp_gtv / mp_a)
    return round(total_g / total_p, 2)

atv_total = {p: total_atv(p) for p in ["Latest", "1D", "7D", "WTD"]}

atv = {
    "Total": atv_total,
    "App":   atv_app,
    "Web":   atv_web,
    "MP":    atv_mp,
}

# ---------------------------------------------------------------------------
# Merchants
# ---------------------------------------------------------------------------

MERCHANT_NAMES = [
    "Merchant A",
    "Merchant B",
    "Merchant C",
    "Merchant D",
    "Merchant E",
    "Merchant F",
    "Merchant G",
    "Merchant H",
    "Merchant I",
    "Merchant J",
]

def make_merchant(name, base_latest, source_share=1.0):
    latest = round(base_latest * source_share * random.uniform(0.9, 1.1), 2)
    d1_val = round(latest * random.uniform(0.8, 1.2), 2)
    d7_val = round(latest * random.uniform(0.7, 1.3), 2)
    # WTD = ~4 days worth
    wtd_val = round(latest * random.uniform(3.5, 4.5), 2)
    return {"name": name, "Latest": latest, "1D": d1_val, "7D": d7_val, "WTD": wtd_val}

# Base GTV per merchant on REPORT_DATE (Total across all sources)
MERCHANT_BASES = [28000, 21000, 18500, 16000, 12000, 10000, 8500, 7000, 5500, 4000]

merchants_total = [make_merchant(n, b) for n, b in zip(MERCHANT_NAMES, MERCHANT_BASES)]

# App: ~85% of each merchant's total
merchants_app = [make_merchant(n, b, 0.85) for n, b in zip(MERCHANT_NAMES, MERCHANT_BASES)]

# Web: top 6 merchants with smaller share
merchants_web = [make_merchant(n, b, 0.10) for n, b in zip(MERCHANT_NAMES[:6], MERCHANT_BASES[:6])]

# MP: top 5 merchants with smaller share
merchants_mp = [make_merchant(n, b, 0.05) for n, b in zip(MERCHANT_NAMES[:5], MERCHANT_BASES[:5])]

# ---------------------------------------------------------------------------
# Assemble full JSON
# ---------------------------------------------------------------------------

NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

payload = {
    "meta": {
        "generatedAt": NOW,
        "source": "growth_raw_ds_v4",
        "reportDate": "2026-04-09",
        "reportDayLabel": "Thursday · Apr 9",
        "prevDate": "2026-04-02",
        "prevDayLabel": "Thursday · Apr 2",
        "weekLabel": "Apr 6–Apr 9",
        "weekNumber": 15,
    },
    "gtv": {
        "current":  current,
        "vs1d":     vs1d,
        "vs7d":     vs7d,
        "wtd":      wtd,
        "target":   {"Total": 1509722, "App": 1364613, "Web": 114814, "MP": 30295},
        "daily": {
            "Total": daily_total,
            "App":   daily_app,
            "Web":   daily_web,
            "MP":    daily_mp,
        },
        "future":   [False, False, False, False, True, True, True],
        "days":     ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "dates":    ["Apr 6", "Apr 7", "Apr 8", "Apr 9", "Apr 10", "Apr 11", "Apr 12"],
        "wtdLabel": "Apr 6–Apr 9",
        "conv":      conv,
        "convMock":  {"Latest": False, "1D": False, "7D": False, "WTD": False},
        "merchants": {
            "Total": merchants_total,
            "App":   merchants_app,
            "Web":   merchants_web,
            "MP":    merchants_mp,
        },
        "merchantMock": {"Total": False, "MP": False, "Web": False, "App": False},
        "atv":      atv,
        "atvMock":  False,
    },
}

json_str = json.dumps(payload, indent=2)

# ---------------------------------------------------------------------------
# Inject into template
# ---------------------------------------------------------------------------

if not TEMPLATE_PATH.exists():
    raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

template_html = TEMPLATE_PATH.read_text(encoding="utf-8")

pattern = r'(<script\s+id="report-data"\s+type="application/json">)(.*?)(</script>)'
injected_block = f"\n{json_str}\n  "

def replacer(m):
    return m.group(1) + injected_block + m.group(3)

new_html, count = re.subn(pattern, replacer, template_html, flags=re.DOTALL)

if count == 0:
    raise ValueError("Could not find <script id=\"report-data\"> tag in template.")

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(new_html, encoding="utf-8")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"Sample report written to: {OUTPUT_PATH}")
print(f"  REPORT_DATE : 2026-04-09 (Thursday, Week 15)")
print(f"  Current GTV : Total=₱{current['Total']:,.0f}  App=₱{current['App']:,.0f}  Web=₱{current['Web']:,.0f}  MP=₱{current['MP']:,.0f}")
print(f"  WTD GTV     : Total=₱{wtd['Total']:,.0f}")
print(f"  Merchants   : {len(merchants_total)} Total, {len(merchants_app)} App, {len(merchants_web)} Web, {len(merchants_mp)} MP")
print(f"  Conv Latest : App={conv['App']['Latest']}%  Web={conv['Web']['Latest']}%  MP={conv['MP']['Latest']}%")
print(f"  ATV Latest  : App=₱{atv['App']['Latest']:,.0f}  Web=₱{atv['Web']['Latest']:,.0f}  MP=₱{atv['MP']['Latest']:,.0f}")
print("Done.")
