#!/usr/bin/env python3
"""
Weekly Spending Report Generator
Fetches data from Notion, generates HTML report, sends via Gmail.
Run every Monday at 9am via launchd.
"""

import os
import smtplib
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import defaultdict
import statistics

import requests

# load .env if present
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

GMAIL_SENDER = os.environ["GMAIL_SENDER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENTS = os.environ["RECIPIENTS"].split(",")

# Notion field names — adjust if yours differ
FIELD_DATE = "Date"
FIELD_AMOUNT = "Amount"
FIELD_TYPE = "Type"
FIELD_DESCRIPTION = "Description"

# Category colors (matching your Notion palette)
CATEGORY_COLORS = {
    "Grocery":       "#FFB3B3",
    "DineIn":        "#E8C4E8",
    "Shopping":      "#C4B8E8",
    "Entertainment": "#F0DFA0",
    "Health":        "#B8D4F0",
    "Education":     "#A8D8C8",
    "Housing":       "#D4C4A8",
    "Transportation":"#FFD4B8",
    "Others":        "#E0E0E0",
}

CATEGORY_EMOJI = {
    "Grocery":       "🛒",
    "DineIn":        "🍽️",
    "Shopping":      "🛍️",
    "Entertainment": "🎬",
    "Health":        "💊",
    "Education":     "📚",
    "Housing":       "🏠",
    "Transportation":"🚗",
    "Others":        "📦",
}

# ─────────────────────────────────────────────
# DATE HELPERS
# ─────────────────────────────────────────────

def get_last_week_range():
    """Returns (monday, sunday) of last week as date objects."""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday

def get_weeks_ago_range(weeks_ago):
    """Returns (monday, sunday) for N weeks ago."""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    start = last_monday - timedelta(weeks=weeks_ago - 1)
    end = start + timedelta(days=6)
    return start, end

# ─────────────────────────────────────────────
# NOTION API
# ─────────────────────────────────────────────

def fetch_all_transactions():
    """Fetch all transactions from Notion database."""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    
    all_results = []
    payload = {"page_size": 100}
    
    while True:
        response = requests.post(url, headers=headers, json=payload)
        if not response.ok:
            print("Notion error:", response.json())
        response.raise_for_status()
        data = response.json()
        all_results.extend(data["results"])
        
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    
    return all_results

def parse_transaction(page):
    """Parse a Notion page into a transaction dict."""
    props = page["properties"]
    
    try:
        # Date
        date_val = props[FIELD_DATE]["date"]["start"]
        txn_date = datetime.strptime(date_val, "%Y-%m-%d").date()
        
        # Amount — strip $ and commas
        amount_raw = props[FIELD_AMOUNT]["number"]
        if amount_raw is None:
            return None
        amount = float(amount_raw)
        
        # Type (select)
        type_obj = props[FIELD_TYPE]["select"]
        category = type_obj["name"] if type_obj else "Others"
        
        # Description
        desc_list = props[FIELD_DESCRIPTION]["title"]
        description = desc_list[0]["plain_text"] if desc_list else ""
        
        return {
            "date": txn_date,
            "amount": amount,
            "category": category,
            "description": description,
        }
    except (KeyError, TypeError, ValueError):
        return None

def get_weekly_totals(transactions, start_date, end_date):
    """Sum transactions by category for a given week."""
    totals = defaultdict(float)
    for txn in transactions:
        if start_date <= txn["date"] <= end_date:
            totals[txn["category"]] += txn["amount"]
    return dict(totals)

# ─────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────

def compute_historical_averages(transactions, exclude_start, exclude_end, num_weeks=24):
    """
    Compute per-category weekly averages over the past num_weeks,
    excluding the current report week.
    """
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    
    weekly_data = defaultdict(list)  # category -> list of weekly totals
    
    for w in range(1, num_weeks + 1):
        week_start = last_monday - timedelta(weeks=w)
        week_end = week_start + timedelta(days=6)
        if week_end < (today - timedelta(weeks=num_weeks + 1)):
            break
        totals = get_weekly_totals(transactions, week_start, week_end)
        # Only include weeks that had any spending
        if sum(totals.values()) > 0:
            for cat in CATEGORY_COLORS:
                weekly_data[cat].append(totals.get(cat, 0.0))
    
    averages = {}
    for cat, vals in weekly_data.items():
        if vals:
            averages[cat] = statistics.mean(vals)
    return averages

def compute_trend_data(transactions, num_weeks=6):
    """Get per-category totals for the last N weeks (for trend chart)."""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    
    weeks = []
    for w in range(num_weeks - 1, -1, -1):
        week_start = last_monday - timedelta(weeks=w)
        week_end = week_start + timedelta(days=6)
        label = f"{week_start.strftime('%m/%d')}"
        totals = get_weekly_totals(transactions, week_start, week_end)
        weeks.append({"label": label, "totals": totals, "start": week_start})
    
    return weeks

# ─────────────────────────────────────────────
# HTML/CSS CHART BUILDERS
# ─────────────────────────────────────────────

def build_spending_breakdown_html(weekly_totals):
    """Build HTML/CSS spending breakdown: stacked bar + category rows."""
    total = sum(v for v in weekly_totals.values() if v > 0)
    if total == 0:
        return '<p style="color:#aaa;text-align:center;padding:20px 0;">No spending this week</p>'

    sorted_cats = sorted(
        [(cat, amt) for cat, amt in weekly_totals.items() if amt > 0],
        key=lambda x: -x[1],
    )

    # Stacked proportional bar
    stacked_cells = ""
    for cat, amt in sorted_cats:
        pct = (amt / total) * 100
        color = CATEGORY_COLORS.get(cat, "#ccc")
        stacked_cells += f'<td style="background:{color};width:{pct:.2f}%;height:16px;padding:0;" title="{cat}: ${amt:.2f}"></td>'

    # Individual category rows with bar + amount + %
    max_amt = sorted_cats[0][1]
    rows = ""
    for cat, amt in sorted_cats:
        pct_total = (amt / total) * 100
        bar_pct = (amt / max_amt) * 100
        empty_pct = 100 - bar_pct
        color = CATEGORY_COLORS.get(cat, "#ccc")
        emoji = CATEGORY_EMOJI.get(cat, "")
        rows += f"""
        <tr>
          <td style="padding:7px 14px 7px 0;font-size:13px;white-space:nowrap;color:#4a4540;width:140px;vertical-align:middle;">{emoji} {cat}</td>
          <td style="padding:7px 0;vertical-align:middle;">
            <table style="width:100%;border-collapse:collapse;"><tr>
              <td style="background:{color};width:{bar_pct:.2f}%;height:12px;padding:0;border-radius:6px 0 0 6px;"></td>
              <td style="background:#f0ede6;width:{empty_pct:.2f}%;height:12px;padding:0;border-radius:0 6px 6px 0;"></td>
            </tr></table>
          </td>
          <td style="padding:7px 0 7px 14px;font-size:14px;font-weight:600;text-align:right;white-space:nowrap;color:#2c2a26;width:80px;">${amt:,.2f}</td>
          <td style="padding:7px 0 7px 8px;font-size:11px;color:#888;text-align:right;white-space:nowrap;width:40px;">{pct_total:.1f}%</td>
        </tr>"""

    return f"""
    <table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;margin-bottom:16px;"><tr>{stacked_cells}</tr></table>
    <table style="width:100%;border-collapse:collapse;">{rows}</table>"""


def build_trend_chart_html(trend_data):
    """Build HTML/CSS 6-week total spend bar chart (Housing excluded)."""
    weeks = []
    for w in trend_data:
        total = sum(v for cat, v in w["totals"].items() if cat != "Housing")
        weeks.append({"label": w["label"], "total": total})

    max_total = max((w["total"] for w in weeks), default=1) or 1
    chart_height = 100  # px, max bar height

    bar_cells = ""
    date_cells = ""
    for i, w in enumerate(weeks):
        bar_h = max(int((w["total"] / max_total) * chart_height), 2)
        is_latest = (i == len(weeks) - 1)
        bar_color = "#9B8EC4" if is_latest else "#C4B8E8"
        bar_cells += f"""
        <td style="text-align:center;vertical-align:bottom;padding:0 5px;height:{chart_height + 24}px;">
          <div style="font-size:11px;color:#777;margin-bottom:4px;">${w["total"]:,.0f}</div>
          <div style="background:{bar_color};height:{bar_h}px;border-radius:4px 4px 0 0;margin:0 auto;width:36px;"></div>
        </td>"""
        date_cells += f'<td style="text-align:center;padding:5px 5px 0;font-size:11px;color:#888;">{w["label"]}</td>'

    return f"""
    <table style="width:100%;border-collapse:collapse;border-bottom:2px solid #e0ddd6;">
      <tr>{bar_cells}</tr>
    </table>
    <table style="width:100%;border-collapse:collapse;">
      <tr>{date_cells}</tr>
    </table>"""

# ─────────────────────────────────────────────
# EMAIL HTML BUILDER
# ─────────────────────────────────────────────

def build_html_email(week_start, week_end, weekly_totals, historical_avg, trend_data):
    week_label = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
    total_spend = sum(weekly_totals.values())
    
    # Compute insights
    insights = []
    for cat, amt in sorted(weekly_totals.items(), key=lambda x: -x[1]):
        avg = historical_avg.get(cat, 0)
        if avg > 0 and amt > 0:
            pct = ((amt - avg) / avg) * 100
            if abs(pct) >= 20:
                direction = "高于" if pct > 0 else "低于"
                insights.append(f"{CATEGORY_EMOJI.get(cat, '')} <b>{cat}</b> 本周支出{direction}历史均值 <b>{abs(pct):.0f}%</b>")
    
    zero_cats = [cat for cat in CATEGORY_COLORS if weekly_totals.get(cat, 0) == 0]
    if zero_cats:
        insights.append(f"💤 本周无支出分类：{', '.join(zero_cats)}")
    insights = insights[:4]
    
    # Build overview rows
    all_categories = list(CATEGORY_COLORS.keys())
    overview_rows = ""
    for cat in all_categories:
        amt = weekly_totals.get(cat, 0)
        avg = historical_avg.get(cat, 0)
        emoji = CATEGORY_EMOJI.get(cat, "")
        color = CATEGORY_COLORS.get(cat, "#eee")
        
        if avg > 0 and amt > 0:
            pct = ((amt - avg) / avg) * 100
            if pct > 5:
                arrow = '<span style="color:#e05c5c;font-size:16px;">↑</span>'
                pct_str = f'<span style="color:#e05c5c;font-size:11px;">+{pct:.0f}%</span>'
            elif pct < -5:
                arrow = '<span style="color:#4caf7d;font-size:16px;">↓</span>'
                pct_str = f'<span style="color:#4caf7d;font-size:11px;">{pct:.0f}%</span>'
            else:
                arrow = '<span style="color:#aaa;font-size:14px;">—</span>'
                pct_str = '<span style="color:#aaa;font-size:11px;">正常</span>'
        elif amt == 0:
            arrow = '<span style="color:#ccc;font-size:14px;">·</span>'
            pct_str = '<span style="color:#ccc;font-size:11px;">无支出</span>'
        else:
            arrow = '<span style="color:#aaa;font-size:14px;">—</span>'
            pct_str = '<span style="color:#aaa;font-size:11px;">新类别</span>'
        
        row_style = "background:#fafaf8;" if all_categories.index(cat) % 2 == 0 else "background:#f4f3f0;"
        overview_rows += f"""
        <tr style="{row_style}">
          <td style="padding:11px 18px;font-size:14px;">
            <span style="display:inline-block;background:{color};border-radius:12px;padding:2px 10px;font-size:12px;font-weight:600;">{emoji} {cat}</span>
          </td>
          <td style="padding:11px 18px;font-size:15px;font-weight:600;text-align:right;">${amt:,.2f}</td>
          <td style="padding:11px 18px;font-size:14px;color:#888;text-align:right;">${avg:,.2f}</td>
          <td style="padding:11px 18px;text-align:center;">{arrow} {pct_str}</td>
        </tr>
        """
    
    insight_html = ""
    for ins in insights:
        insight_html += f'<li style="margin:8px 0;line-height:1.6;">{ins}</li>'
    
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#f0ede6;font-family:'DM Sans',sans-serif;">

<div style="max-width:680px;margin:32px auto;background:#fdfcf9;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- HEADER -->
  <div style="background:#2c2a26;padding:36px 40px;text-align:center;">
    <div style="font-size:11px;letter-spacing:3px;color:#a89880;text-transform:uppercase;margin-bottom:8px;">Weekly Spending Report</div>
    <div style="font-size:28px;color:#f5f0e8;font-weight:normal;letter-spacing:0.5px;">{week_label}</div>
    <div style="margin-top:20px;display:inline-block;background:#3a3730;border-radius:12px;padding:12px 32px;">
      <span style="font-size:13px;color:#a89880;">Total Spending</span><br>
      <span style="font-size:36px;color:#f5f0e8;letter-spacing:-1px;">${total_spend:,.2f}</span>
    </div>
  </div>

  <!-- HIGHLIGHTS -->
  <div style="padding:28px 40px;border-bottom:1px solid #ece9e2;">
    <div style="font-size:10px;letter-spacing:3px;color:#b0a898;text-transform:uppercase;margin-bottom:16px;">💡 Highlights</div>
    <ul style="margin:0;padding-left:18px;color:#4a4540;">
      {insight_html if insight_html else '<li style="color:#aaa;">本周支出均在正常范围内</li>'}
    </ul>
  </div>

  <!-- OVERVIEW TABLE -->
  <div style="padding:28px 40px 0;">
    <div style="font-size:10px;letter-spacing:3px;color:#b0a898;text-transform:uppercase;margin-bottom:16px;">📊 Category Overview</div>
    <table style="width:100%;border-collapse:collapse;border-radius:10px;overflow:hidden;">
      <thead>
        <tr style="background:#2c2a26;color:#a89880;font-size:11px;letter-spacing:1px;text-transform:uppercase;">
          <th style="padding:10px 18px;text-align:left;font-weight:500;">Category</th>
          <th style="padding:10px 18px;text-align:right;font-weight:500;">This Week</th>
          <th style="padding:10px 18px;text-align:right;font-weight:500;">6W Avg</th>
          <th style="padding:10px 18px;text-align:center;font-weight:500;">vs Avg</th>
        </tr>
      </thead>
      <tbody>
        {overview_rows}
      </tbody>
    </table>
  </div>

  <!-- SPENDING BREAKDOWN -->
  <div style="padding:32px 40px 0;">
    <div style="font-size:10px;letter-spacing:3px;color:#b0a898;text-transform:uppercase;margin-bottom:16px;">🥧 Spending Breakdown</div>
    {build_spending_breakdown_html(weekly_totals)}
  </div>

  <!-- TREND CHART -->
  <div style="padding:24px 40px 0;">
    <div style="font-size:10px;letter-spacing:3px;color:#b0a898;text-transform:uppercase;margin-bottom:16px;">📈 6-Week Trend <span style="font-size:9px;color:#ccc;">(Housing excluded)</span></div>
    {build_trend_chart_html(trend_data)}
  </div>

  <!-- FOOTER -->
  <div style="padding:28px 40px;text-align:center;color:#b0a898;font-size:11px;border-top:1px solid #ece9e2;margin-top:32px;">
    Generated automatically every Monday · Data from Notion<br>
    <span style="color:#d4c8b8;">Haochen & Joyce · {datetime.now().strftime('%Y')}</span>
  </div>

</div>
</body>
</html>"""
    
    return html

# ─────────────────────────────────────────────
# EMAIL SENDER
# ─────────────────────────────────────────────

def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, RECIPIENTS, msg.as_string())

    print(f"✅ Report sent to {RECIPIENTS}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("📡 Fetching Notion data...")
    raw_pages = fetch_all_transactions()
    transactions = [t for p in raw_pages if (t := parse_transaction(p)) is not None]
    print(f"   {len(transactions)} transactions loaded")
    
    week_start, week_end = get_last_week_range()
    print(f"📅 Report week: {week_start} → {week_end}")
    
    weekly_totals = get_weekly_totals(transactions, week_start, week_end)
    historical_avg = compute_historical_averages(transactions, week_start, week_end)
    trend_data = compute_trend_data(transactions, num_weeks=6)
    
    html = build_html_email(week_start, week_end, weekly_totals, historical_avg, trend_data)

    subject = f"💰 Weekly Spending · {week_start.strftime('%b %d')}–{week_end.strftime('%b %d')}"

    print("📧 Sending email...")
    send_email(subject, html)

if __name__ == "__main__":
    main()
