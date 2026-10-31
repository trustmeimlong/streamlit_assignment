from dataclasses import dataclass
from datetime import date

ALL_STATUSES = "Tất cả"
STATUS_OPTIONS = [ALL_STATUSES, "Active", "Upgraded", "Churned"]
TICKET_THRESHOLD = 3
MIN_SEGMENT_CUSTOMERS = 5
RECENT_MONTHS = 3

LATEST_STATUS_CTE = """latest_status AS (
    SELECT customer_id, status, churn_reason, updated_at AS status_date,
           ROW_NUMBER() OVER (PARTITION BY customer_id
                              ORDER BY updated_at DESC, subscription_id DESC) AS rn
    FROM Subscriptions
)"""

BASE_JOINS = """FROM Customers c
JOIN Plans p         ON p.plan_id = c.plan_id
JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
JOIN UsageLogs u     ON u.customer_id = c.customer_id"""

CHURNED_IN_MONTH = ("s.status = 'Churned' AND s.status_date >= u.usage_month "
                    "AND s.status_date < u.usage_month + INTERVAL 1 MONTH")
CHURNED_IN_PERIOD = "s.status = 'Churned' AND s.status_date >= :start_month AND s.status_date < :end_next"


def add_months(d, n):
    total = d.year * 12 + d.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def indent(text, spaces=4):
    return text.replace("\n", "\n" + " " * spaces)


@dataclass(frozen=True)
class Filters:
    start_month: date
    end_month: date
    sizes: tuple
    status: str

    @property
    def end_next(self):
        return add_months(self.end_month, 1)

    @property
    def recent_start(self):
        return max(self.start_month, add_months(self.end_month, 1 - RECENT_MONTHS))


def build_where(f, date_filter="usage"):
    sql = "WHERE 1=1"
    params = {"start_month": f.start_month}
    if date_filter == "usage":
        sql += "\n  AND u.usage_month BETWEEN :start_month AND :end_month"
        params["end_month"] = f.end_month
    else:
        sql += "\n  AND s.status_date >= :start_month AND s.status_date < :end_next"
        params["end_next"] = f.end_next
    if f.sizes:
        keys = [f"size_{i}" for i in range(len(f.sizes))]
        sql += f"\n  AND c.company_size IN ({', '.join(':' + k for k in keys)})"
        params.update(zip(keys, f.sizes))
    if f.status != ALL_STATUSES:
        sql += "\n  AND s.status = :status"
        params["status"] = f.status
    return sql, params


def detail_query(f):
    where, params = build_where(f)
    sql = f"""WITH {LATEST_STATUS_CTE}
SELECT c.customer_id, c.customer_name, c.company_size, p.plan_name, p.monthly_price, p.ai_token_limit,
       s.status, s.churn_reason, s.status_date, u.usage_month, u.tokens_consumed, u.ai_api_cost,
       u.support_tickets_opened,
       ROUND(u.tokens_consumed * 100 / p.ai_token_limit, 1) AS token_usage_pct,
       u.tokens_consumed > p.ai_token_limit AS over_limit,
       p.monthly_price - u.ai_api_cost AS ai_profit
{BASE_JOINS}
{where}
ORDER BY u.usage_month, c.customer_id"""
    return sql, params


def monthly_query(f):
    where, params = build_where(f)
    sql = f"""WITH {LATEST_STATUS_CTE}
SELECT u.usage_month,
       COUNT(DISTINCT c.customer_id) AS active_customers,
       COUNT(DISTINCT CASE WHEN {CHURNED_IN_MONTH} THEN c.customer_id END) AS churned_customers,
       COUNT(DISTINCT CASE WHEN c.signup_date < u.usage_month THEN c.customer_id END) AS start_customers,
       COUNT(DISTINCT CASE WHEN c.signup_date < u.usage_month AND {CHURNED_IN_MONTH}
                           THEN c.customer_id END) AS churned_from_start,
       SUM(p.monthly_price) AS revenue,
       SUM(CASE WHEN {CHURNED_IN_MONTH} THEN 0 ELSE p.monthly_price END) AS mrr,
       SUM(u.ai_api_cost) AS ai_cost,
       SUM(u.tokens_consumed) AS tokens,
       AVG(u.support_tickets_opened) AS avg_tickets,
       SUM(u.tokens_consumed > p.ai_token_limit) AS over_limit_customers
{BASE_JOINS}
{where}
GROUP BY u.usage_month
ORDER BY u.usage_month"""
    return sql, params


def churn_reason_query(f):
    where, params = build_where(f, date_filter="churn")
    sql = f"""WITH {LATEST_STATUS_CTE}
SELECT s.churn_reason, COUNT(*) AS churned_customers
FROM Customers c
JOIN latest_status s ON s.customer_id = c.customer_id AND s.rn = 1
{where}
  AND s.status = 'Churned'
GROUP BY s.churn_reason
ORDER BY churned_customers DESC, s.churn_reason"""
    return sql, params


def risk_segment_query(f):
    where, params = build_where(f)
    params["end_next"] = f.end_next
    params["min_customers"] = MIN_SEGMENT_CUSTOMERS
    sql = f"""WITH {LATEST_STATUS_CTE},
customer_usage AS (
    SELECT c.customer_id, c.company_size,
           MAX(u.tokens_consumed * 100 / p.ai_token_limit) AS max_usage_pct,
           MAX(CASE WHEN {CHURNED_IN_PERIOD} THEN 1 ELSE 0 END) AS churned
    {indent(BASE_JOINS)}
    {indent(where)}
    GROUP BY c.customer_id, c.company_size
)
SELECT company_size,
       CASE WHEN max_usage_pct > 100 THEN '> 100%'
            WHEN max_usage_pct >= 80 THEN '80-100%'
            ELSE '< 80%' END AS usage_band,
       COUNT(*) AS customers,
       SUM(churned) AS churned_customers,
       ROUND(SUM(churned) * 100 / COUNT(*), 1) AS churn_rate
FROM customer_usage
GROUP BY company_size, usage_band
HAVING COUNT(*) >= :min_customers
ORDER BY FIELD(company_size, 'Startup', 'SMB', 'Enterprise'), FIELD(usage_band, '< 80%', '80-100%', '> 100%')"""
    return sql, params


def risk_customers_query(f):
    where, params = build_where(f)
    params["recent_start"] = f.recent_start
    params["ticket_threshold"] = TICKET_THRESHOLD
    recent = "u.usage_month >= :recent_start"
    sql = f"""WITH {LATEST_STATUS_CTE}
SELECT c.customer_id, c.customer_name, c.company_size, p.plan_name, p.monthly_price, s.status,
       SUM({recent}) AS recent_months,
       SUM({recent} AND u.tokens_consumed > p.ai_token_limit) AS months_over_limit,
       ROUND(MAX(CASE WHEN {recent} THEN u.tokens_consumed * 100 / p.ai_token_limit END), 1) AS max_usage_pct,
       MAX(CASE WHEN {recent} THEN u.support_tickets_opened END) AS max_tickets,
       SUM(p.monthly_price) AS revenue,
       SUM(u.ai_api_cost) AS ai_cost,
       SUM(p.monthly_price - u.ai_api_cost) AS ai_profit,
       MAX(u.usage_month) AS last_active_month
{BASE_JOINS}
{where}
  AND s.status <> 'Churned'
GROUP BY c.customer_id, c.customer_name, c.company_size, p.plan_name, p.monthly_price, s.status
HAVING MAX(CASE WHEN {recent} THEN u.tokens_consumed - p.ai_token_limit END) > 0
    OR MAX(CASE WHEN {recent} THEN u.support_tickets_opened END) > :ticket_threshold
ORDER BY months_over_limit DESC, max_tickets DESC, ai_profit"""
    return sql, params


def risk_backtest_query(f):
    where, params = build_where(f)
    params["ticket_threshold"] = TICKET_THRESHOLD
    sql = f"""WITH {LATEST_STATUS_CTE},
customer_months AS (
    SELECT c.customer_id, u.usage_month,
           u.tokens_consumed > p.ai_token_limit AS over_limit,
           u.support_tickets_opened > :ticket_threshold AS many_tickets,
           CASE WHEN {CHURNED_IN_MONTH} THEN 1 ELSE 0 END AS churned
    {indent(BASE_JOINS)}
    {indent(where)}
),
signals AS (
    SELECT churned,
           MAX(over_limit) OVER recent AS recent_over,
           MAX(many_tickets) OVER recent AS recent_tickets,
           LEAD(churned) OVER by_month AS churned_next_month
    FROM customer_months
    WINDOW by_month AS (PARTITION BY customer_id ORDER BY usage_month),
           recent AS (by_month ROWS BETWEEN {RECENT_MONTHS - 1} PRECEDING AND CURRENT ROW)
)
SELECT CASE WHEN recent_over = 1 THEN 'high'
            WHEN recent_tickets = 1 THEN 'watch'
            ELSE 'none' END AS risk_level,
       COUNT(*) AS evaluations,
       SUM(churned_next_month) AS churned_next_month
FROM signals
WHERE churned = 0 AND churned_next_month IS NOT NULL
GROUP BY risk_level
ORDER BY FIELD(risk_level, 'high', 'watch', 'none')"""
    return sql, params


OPTIONS_SQL = """SELECT MIN(usage_month) AS first_month, MAX(usage_month) AS last_month,
       (SELECT GROUP_CONCAT(DISTINCT company_size ORDER BY FIELD(company_size, 'Startup', 'SMB', 'Enterprise'))
        FROM Customers) AS sizes
FROM UsageLogs"""

QUERY_LABELS = {
    "detail": "Dữ liệu chi tiết",
    "monthly": "Xu hướng theo tháng",
    "churn_reason": "Lý do rời bỏ",
    "risk_segment": "Rủi ro theo quy mô công ty",
    "risk_customers": "Khách hàng rủi ro",
    "risk_backtest": "Kiểm chứng quy tắc rủi ro",
}

QUERY_BUILDERS = {
    "detail": detail_query,
    "monthly": monthly_query,
    "churn_reason": churn_reason_query,
    "risk_segment": risk_segment_query,
    "risk_customers": risk_customers_query,
    "risk_backtest": risk_backtest_query,
}
