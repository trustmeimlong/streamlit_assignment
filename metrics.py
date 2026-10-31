import numpy as np
import pandas as pd

from queries import TICKET_THRESHOLD

COST_REASON_KEYWORDS = ("chi phí", "giá gói")
HIGH_RISK = "🔴 Cao"
WATCH_RISK = "🟡 Theo dõi"

DETAIL_COLUMNS = {
    "usage_month": "Tháng",
    "customer_id": "Mã KH",
    "customer_name": "Khách hàng",
    "company_size": "Quy mô",
    "plan_name": "Gói",
    "status": "Trạng thái",
    "churn_reason": "Lý do rời bỏ",
    "monthly_price": "Giá gói (USD)",
    "ai_token_limit": "Giới hạn token",
    "tokens_consumed": "Token tiêu thụ",
    "token_usage_pct": "Mức dùng token (%)",
    "ai_api_cost": "Chi phí AI (USD)",
    "ai_profit": "Lợi nhuận sau AI (USD)",
    "support_tickets_opened": "Ticket hỗ trợ",
}

RISK_COLUMNS = {
    "risk_level": "Mức rủi ro",
    "customer_name": "Khách hàng",
    "company_size": "Quy mô",
    "plan_name": "Gói",
    "status": "Trạng thái",
    "signals": "Dấu hiệu (3 tháng gần nhất)",
    "max_usage_pct": "Mức dùng token cao nhất (%)",
    "months_over_limit": "Số tháng vượt token",
    "max_tickets": "Ticket cao nhất/tháng",
    "monthly_price": "Giá gói/tháng (USD)",
    "revenue": "Doanh thu cả kỳ (USD)",
    "ai_cost": "Chi phí AI cả kỳ (USD)",
    "ai_profit": "Lợi nhuận sau AI cả kỳ (USD)",
    "last_active_month": "Tháng gần nhất",
}

MONTHLY_COLUMNS = {
    "usage_month": "Tháng",
    "mrr": "MRR (USD)",
    "revenue": "Doanh thu (USD)",
    "ai_cost": "Chi phí AI (USD)",
    "ai_profit": "Lợi nhuận sau AI (USD)",
    "margin_pct": "Biên lợi nhuận (%)",
    "active_customers": "Khách đang dùng",
    "start_customers": "Khách đầu tháng",
    "churned_customers": "Khách rời bỏ",
    "churned_from_start": "Khách đầu tháng rời bỏ",
    "churn_rate": "Tỉ lệ rời bỏ (%)",
    "avg_tickets": "Ticket trung bình/khách",
}


def prepare_detail(detail):
    d = detail.copy()
    d["usage_month"] = pd.to_datetime(d["usage_month"])
    d["status_date"] = pd.to_datetime(d["status_date"])
    d["over_limit"] = d["over_limit"].astype(bool)
    d["churn_reason"] = d["churn_reason"].fillna("")
    return d


def prepare_monthly(monthly):
    m = monthly.copy()
    m["usage_month"] = pd.to_datetime(m["usage_month"])
    base = m["start_customers"].where(m["start_customers"] > 0)
    m["churn_rate"] = (m["churned_from_start"] / base * 100).round(1)
    m["ai_profit"] = m["revenue"] - m["ai_cost"]
    m["margin_pct"] = (m["ai_profit"] / m["revenue"].where(m["revenue"] > 0) * 100).astype(float).round(1)
    m["avg_tickets"] = m["avg_tickets"].astype(float).round(2)
    m["over_limit_customers"] = m["over_limit_customers"].astype(int)
    return m


def average_monthly_churn(monthly):
    base = monthly["start_customers"].sum()
    return monthly["churned_from_start"].sum() / base * 100 if base else float("nan")


def prepare_risk(risk):
    r = risk.copy()
    r["last_active_month"] = pd.to_datetime(r["last_active_month"])
    r["months_over_limit"] = r["months_over_limit"].astype(int)
    r["max_tickets"] = r["max_tickets"].astype(int)
    over = r["months_over_limit"] > 0
    tickets = r["max_tickets"] > TICKET_THRESHOLD
    r["risk_level"] = np.where(over, HIGH_RISK, WATCH_RISK)
    over_text = np.where(over, "Vượt token " + r["months_over_limit"].astype(str) + "/"
                         + r["recent_months"].astype(int).astype(str) + " tháng", "")
    ticket_text = np.where(tickets, "Tối đa " + r["max_tickets"].astype(str) + " ticket/tháng", "")
    r["signals"] = ["; ".join(p for p in pair if p) for pair in zip(over_text, ticket_text)]
    r["level_order"] = np.where(over, 0, 1)
    return r.sort_values(["level_order", "months_over_limit", "max_tickets"], ascending=[True, False, False])


def summarize_backtest(backtest):
    counts = (backtest.set_index("risk_level")[["evaluations", "churned_next_month"]]
              .reindex(["high", "watch", "none"]).fillna(0))

    def rate(levels):
        n = counts.loc[levels, "evaluations"].sum()
        return counts.loc[levels, "churned_next_month"].sum() / n * 100 if n else float("nan")

    return {
        "evaluations": int(counts["evaluations"].sum()),
        "events": int(counts["churned_next_month"].sum()),
        "n_high": int(counts.loc["high", "evaluations"]),
        "high": rate(["high"]),
        "watch": rate(["watch"]),
        "none": rate(["none"]),
        "rest": rate(["watch", "none"]),
    }


def is_cost_reason(reasons):
    lowered = reasons.str.lower()
    return np.logical_or.reduce([lowered.str.contains(k, regex=False) for k in COST_REASON_KEYWORDS])


def compute_kpis(monthly, detail):
    revenue = monthly["revenue"].sum()
    profit = revenue - monthly["ai_cost"].sum()
    customers = detail["customer_id"].nunique()
    churned = int(monthly["churned_customers"].sum())
    last = monthly.iloc[-1]
    prev = monthly.iloc[-2] if len(monthly) > 1 else None
    return {
        "last_month": last["usage_month"],
        "mrr": last["mrr"],
        "mrr_delta": last["mrr"] - prev["mrr"] if prev is not None else None,
        "customers": customers,
        "churned": churned,
        "churn_rate": churned / customers * 100 if customers else 0.0,
        "churn_monthly": average_monthly_churn(monthly),
        "revenue": revenue,
        "profit": profit,
        "margin": profit / revenue * 100 if revenue else 0.0,
        "avg_tickets": detail["support_tickets_opened"].mean(),
        "tickets_delta": round(last["avg_tickets"] - prev["avg_tickets"], 2) if prev is not None else None,
    }


def to_vietnamese(df, columns):
    out = df[list(columns)].rename(columns=columns)
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.date
    return out
