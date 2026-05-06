#!/usr/bin/env python3
"""
Test preview — generates the weekly report HTML with mock data and opens it in
the browser. No Notion API calls, no email sending.

Usage:
  python test_preview.py          # open in browser only
  python test_preview.py --send   # also send to RECIPIENTS
"""

import random
import webbrowser
import tempfile
import os
import sys
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

# Monkey-patch only Notion vars — Gmail vars must come from .env
for _k in ("NOTION_TOKEN", "NOTION_DATABASE_ID"):
    os.environ.setdefault(_k, "test")

from spending_report import (
    CATEGORY_COLORS,
    get_weekly_totals, compute_historical_averages, compute_trend_data,
    build_html_email, send_email,
)


# ── Mock data ────────────────────────────────────────────────────────────────

def make_mock_transactions(num_weeks: int = 26, seed: int = 42) -> list:
    """
    Generate realistic fake transactions across num_weeks of history.
    The most recent full week is last_week (Mon–Sun relative to today).
    """
    rng = random.Random(seed)
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)

    # Typical weekly spend per category (mean, std_dev), 0 = skip most weeks
    profiles = {
        "Grocery":        (165, 30,  1.0),   # every week
        "DineIn":         (95,  25,  0.85),
        "Shopping":       (80,  60,  0.55),
        "Entertainment":  (45,  25,  0.60),
        "Health":         (35,  20,  0.40),
        "Education":      (25,  15,  0.25),
        "Housing":        (0,    0,  0.0),   # handled separately (monthly)
        "Transportation": (65,  20,  0.90),
        "Others":         (30,  20,  0.45),
    }

    transactions = []
    cat_names = list(CATEGORY_COLORS.keys())

    for w in range(num_weeks):
        week_start = last_monday - timedelta(weeks=w)
        for cat, (mean, std, prob) in profiles.items():
            if cat == "Housing":
                continue
            if rng.random() > prob:
                continue
            amt = max(5.0, rng.gauss(mean, std))
            # 1-3 transactions per category per week
            n = rng.randint(1, 3)
            for _ in range(n):
                day_offset = rng.randint(0, 6)
                transactions.append({
                    "date": week_start + timedelta(days=day_offset),
                    "amount": round(amt / n, 2),
                    "category": cat,
                    "description": f"Sample {cat} expense",
                })

    # Housing: one payment per month (~$1850)
    for m in range(num_weeks // 4 + 1):
        pay_date = last_monday - timedelta(weeks=m * 4)
        transactions.append({
            "date": pay_date,
            "amount": round(rng.gauss(1850, 50), 2),
            "category": "Housing",
            "description": "Rent / Housing",
        })

    # Make last week a bit more interesting for highlights
    interesting = [
        ("Grocery", 220.00, "Costco run"),
        ("DineIn",  12.50,  "Coffee & bagel"),
        ("Shopping",148.00, "Amazon order"),
        ("Entertainment", 65.00, "Concert tickets"),
        ("Transportation", 55.00, "Uber rides"),
    ]
    for cat, amt, desc in interesting:
        day_offset = random.randint(0, 6)
        transactions.append({
            "date": last_monday + timedelta(days=day_offset),
            "amount": amt,
            "category": cat,
            "description": desc,
        })

    return transactions


# ── Preview runner ───────────────────────────────────────────────────────────

def main():
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    week_start = last_monday
    week_end   = last_monday + timedelta(days=6)

    print("🧪 Generating mock transactions…")
    transactions = make_mock_transactions(num_weeks=26)
    print(f"   {len(transactions)} mock transactions created")

    weekly_totals   = get_weekly_totals(transactions, week_start, week_end)
    historical_avg  = compute_historical_averages(transactions, week_start, week_end)
    trend_data      = compute_trend_data(transactions, num_weeks=6)

    print("📄 Building HTML…")
    html = build_html_email(week_start, week_end, weekly_totals, historical_avg, trend_data)

    # Save to a temp HTML file and open in browser
    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", delete=False,
        prefix="weekly_report_preview_",
        dir=tempfile.gettempdir(),
    )
    tmp.write(html.encode("utf-8"))
    tmp.close()

    print(f"🌐 Opening preview: {tmp.name}")
    webbrowser.open(f"file://{tmp.name}")

    if "--send" in sys.argv:
        subject = f"💰 Weekly Spending · {week_start.strftime('%b %d')}–{week_end.strftime('%b %d')}"
        print("📧 Sending preview email…")
        send_email(subject, html)
    else:
        print("✅ Done — run with --send to also send the email.")


if __name__ == "__main__":
    main()
