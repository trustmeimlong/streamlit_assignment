import math
import sys
import tomllib
from decimal import ROUND_HALF_UP, Decimal
from math import comb
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import metrics
import queries as q

COMPARISON_COLUMNS = {"comparison", "exposed", "events", "total"}
STRATIFIED_COLUMNS = {"stratum", "exposed", "events", "total"}
BACKTEST_SECTION = "Insight 5: Kiểm chứng quy tắc rủi ro theo nửa kỳ và theo nhóm gói"
NAN = float("nan")


def get_engine():
    with (ROOT / ".streamlit" / "secrets.toml").open("rb") as f:
        cfg = tomllib.load(f)["mysql"]
    url = URL.create("mysql+mysqlconnector", username=cfg["username"], password=cfg["password"],
                     host=cfg["host"], port=int(cfg["port"]), database=cfg["database"])
    return create_engine(url)


def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def fisher_two_sided(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    total = comb(n1 + n2, k)

    def prob(x):
        return comb(n1, x) * comb(n2, k - x) / total

    observed = prob(a)
    candidates = range(max(0, k - n2), min(k, n1) + 1)
    return min(1.0, sum(prob(x) for x in candidates if prob(x) <= observed * (1 + 1e-9)))


def risk_ratio(k1, n1, k0, n0):
    if k0 == 0:
        return NAN, (NAN, NAN)
    rr = (k1 / n1) / (k0 / n0)
    if k1 == 0:
        return rr, (NAN, NAN)
    se = math.sqrt(1 / k1 - 1 / n1 + 1 / k0 - 1 / n0)
    return rr, (math.exp(math.log(rr) - 1.96 * se), math.exp(math.log(rr) + 1.96 * se))


def mantel_haenszel(strata):
    num = sum(k1 * n0 / (n1 + n0) for k1, n1, k0, n0 in strata)
    den = sum(k0 * n1 / (n1 + n0) for k1, n1, k0, n0 in strata)
    if num == 0 or den == 0:
        return NAN, (NAN, NAN)
    var = sum((n1 * n0 * (k1 + k0) - k1 * k0 * (n1 + n0)) / (n1 + n0) ** 2
              for k1, n1, k0, n0 in strata) / (num * den)
    rr, half = num / den, 1.96 * math.sqrt(var)
    return rr, (math.exp(math.log(rr) - half), math.exp(math.log(rr) + half))


def pct(k, n):
    return (Decimal(k * 100) / n).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def describe(label, k1, n1, k0, n0):
    k1, n1, k0, n0 = int(k1), int(n1), int(k0), int(n0)
    lo1, hi1 = wilson(k1, n1)
    lo0, hi0 = wilson(k0, n0)
    rr, (rr_lo, rr_hi) = risk_ratio(k1, n1, k0, n0)
    p = fisher_two_sided(k1, n1 - k1, k0, n0 - k0)
    print(f"  {label}")
    print(f"    có dấu hiệu  {k1}/{n1} = {pct(k1, n1)}% (95% CI {lo1 * 100:.1f}% đến {hi1 * 100:.1f}%)")
    print(f"    không có     {k0}/{n0} = {pct(k0, n0)}% (95% CI {lo0 * 100:.1f}% đến {hi0 * 100:.1f}%)")
    print(f"    risk ratio {rr:.2f} (95% CI {rr_lo:.2f} đến {rr_hi:.2f}), Fisher exact p = {p:.2g}")


def run_sql_file(con):
    sql = (ROOT / "sql" / "insight_queries.sql").read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";\n") if s.strip() and not s.strip().upper().startswith("USE ")]
    results = {}
    for statement in statements:
        df = pd.read_sql(text(statement), con)
        section = df["section"].iloc[0] if len(df) else "không có dữ liệu"
        results[section] = df
        print(f"\n=== {section}")
        if COMPARISON_COLUMNS <= set(df.columns):
            for name, group in df.groupby("comparison", sort=False):
                rows = group.set_index("exposed")
                if {0, 1} <= set(rows.index):
                    describe(name, int(rows.at[1, "events"]), int(rows.at[1, "total"]),
                             int(rows.at[0, "events"]), int(rows.at[0, "total"]))
        elif STRATIFIED_COLUMNS <= set(df.columns):
            strata = []
            for name, group in df.groupby("stratum", sort=False):
                rows = group.set_index("exposed")
                if {0, 1} <= set(rows.index):
                    counts = [int(rows.at[e, c]) for e in (1, 0) for c in ("events", "total")]
                    describe(name, *counts)
                    strata.append(counts)
            rr, (lo, hi) = mantel_haenszel(strata)
            print(f"  Gộp các nhóm (Mantel-Haenszel): risk ratio {rr:.2f} (95% CI {lo:.2f} đến {hi:.2f})")
        else:
            print(df.drop(columns="section").to_string(index=False))
    return results


def run_dashboard_checks(con, results):
    options = pd.read_sql(text(q.OPTIONS_SQL), con)
    f = q.Filters(options.at[0, "first_month"], options.at[0, "last_month"],
                  tuple(options.at[0, "sizes"].split(",")), q.ALL_STATUSES)
    bt = pd.read_sql(text(q.risk_backtest_query(f)[0]), con, params=q.risk_backtest_query(f)[1]).set_index("risk_level")
    rest = bt.loc[["watch", "none"]]
    print("\n=== Insight 5: Kiểm chứng quy tắc rủi ro (cùng truy vấn với dashboard)")
    describe("Mức Cao, rời bỏ ngay tháng sau",
             int(bt.at["high", "churned_next_month"]), int(bt.at["high", "evaluations"]),
             int(rest["churned_next_month"].sum()), int(rest["evaluations"].sum()))
    describe("Chỉ có nhiều ticket so với không có dấu hiệu, rời bỏ ngay tháng sau",
             int(bt.at["watch", "churned_next_month"]), int(bt.at["watch", "evaluations"]),
             int(bt.at["none", "churned_next_month"]), int(bt.at["none", "evaluations"]))
    share_eval = bt.at["high", "evaluations"] / bt["evaluations"].sum() * 100
    share_churn = bt.at["high", "churned_next_month"] / bt["churned_next_month"].sum() * 100
    print(f"  mức Cao chiếm {share_eval:.1f}% trong {int(bt['evaluations'].sum()):,} lượt đánh giá và bắt được "
          f"{share_churn:.1f}% số khách rời bỏ tháng sau")

    sql, params = q.risk_customers_query(f)
    risk = metrics.prepare_risk(pd.read_sql(text(sql), con, params=params))
    sql, params = q.monthly_query(f)
    monthly = metrics.prepare_monthly(pd.read_sql(text(sql), con, params=params))
    high = risk[risk["risk_level"] == metrics.HIGH_RISK].copy()
    mrr_high, current_mrr = high["monthly_price"].sum(), monthly["mrr"].iloc[-1]
    print(f"  hiện tại: {len(high)} khách mức Cao, MRR ${mrr_high:,.0f} ({mrr_high / current_mrr * 100:.1f}% MRR), "
          f"{len(risk) - len(high)} khách theo dõi")
    rates = results[BACKTEST_SECTION].set_index(["comparison", "exposed"])
    high["plan_group"] = high["plan_name"].isin(["Business", "Scale"]).map(
        {True: "Gói Business và Scale", False: "Gói Starter và Pro"})
    loss = baseline = 0.0
    for name, part in high.groupby("plan_group"):
        p_high = float(rates.at[(name, 1), "events"]) / float(rates.at[(name, 1), "total"])
        p_rest = float(rates.at[(name, 0), "events"]) / float(rates.at[(name, 0), "total"])
        mrr = part["monthly_price"].sum()
        group_loss = mrr * (1 - (1 - p_high) ** 3)
        loss += group_loss
        baseline += mrr * (1 - (1 - p_rest) ** 3)
        print(f"  {name}: {len(part)} khách, MRR ${mrr:,.0f}, dự kiến mất ${group_loss:,.0f} trong 3 tháng "
              f"(${group_loss / len(part):,.0f} mỗi khách)")
    print(f"  MRR dự kiến mất trong 3 tháng nếu không can thiệp: ${loss:,.0f}; "
          f"theo mức thông thường của từng nhóm gói: ${baseline:,.0f}; phần vượt: ${loss - baseline:,.0f}")


if __name__ == "__main__":
    with get_engine().connect() as connection:
        run_dashboard_checks(connection, run_sql_file(connection))
