import numpy as np
import pandas as pd
import plotly.express as px

from metrics import MONTHLY_COLUMNS, average_monthly_churn, is_cost_reason, to_vietnamese

PLAN_ORDER = ["Starter", "Pro", "Business", "Scale"]
SIZE_ORDER = ["Startup", "SMB", "Enterprise"]
BAND_ORDER = ["< 80%", "80-100%", "> 100%"]
BAND_TEXT = {"< 80%": "dưới 80%", "80-100%": "80% đến 100%", "> 100%": "trên 100%"}
MRR_LABEL = "MRR (USD)"
CHURN_LABEL = "Tỉ lệ rời bỏ tháng (%)"
COST_GROUP = "Chi phí AI / giá gói"
OTHER_GROUP = "Lý do khác"

PALETTE = {
    "light": {"Starter": "#1baf7a", "Pro": "#2a78d6", "Business": "#008300", "Scale": "#e87ba4",
              "series": "#2a78d6", "critical": "#d03b3b", "neutral": "#898781", "axis": "#c3c2b7"},
    "dark": {"Starter": "#199e70", "Pro": "#3987e5", "Business": "#008300", "Scale": "#d55181",
             "series": "#3987e5", "critical": "#d03b3b", "neutral": "#898781", "axis": "#383835"},
}
HEAT_SCALE = ["#fdf0ef", "#f7c9c6", "#ee9894", "#e06663", "#c43c3c", "#8f2525"]


def _style(fig, mode, height):
    p = PALETTE[mode]
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36, b=8), legend_title_text="",
                      hoverlabel=dict(font_size=13), font=dict(family="system-ui, -apple-system, sans-serif"))
    fig.update_xaxes(showgrid=False, linecolor=p["axis"], ticks="")
    fig.update_yaxes(showgrid=False, zeroline=False, linecolor=p["axis"])
    return fig


def _clean_facet_titles(fig):
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    return fig


def _pct(value):
    return "-" if pd.isna(value) else f"{value:.1f}%"


def trend_chart(monthly, mode):
    p = PALETTE[mode]
    long = pd.concat([
        monthly.assign(metric=MRR_LABEL, value=monthly["mrr"]),
        monthly.assign(metric=CHURN_LABEL, value=monthly["churn_rate"]),
    ])
    fig = px.line(
        long, x="usage_month", y="value", color="metric", facet_row="metric", markers=True,
        category_orders={"metric": [MRR_LABEL, CHURN_LABEL]},
        color_discrete_map={MRR_LABEL: p["series"], CHURN_LABEL: p["critical"]},
        custom_data=["active_customers", "churned_customers", "start_customers", "churned_from_start"],
        labels={"usage_month": "Tháng", "value": ""},
    )
    fig.update_yaxes(matches=None)
    for trace in fig.data:
        axis = fig.layout["yaxis" + trace.yaxis[1:]]
        top = pd.to_numeric(pd.Series(trace.y), errors="coerce").max()
        top = top if top > 0 else 1
        axis.update(range=[-0.06 * top, 1.08 * top])
        if trace.name == MRR_LABEL:
            axis.update(tickprefix="$", tickformat=",.0f")
            trace.hovertemplate = ("MRR: $%{y:,.0f}<br>Khách đang dùng: %{customdata[0]}"
                                   "<br>Khách rời bỏ trong tháng: %{customdata[1]}<extra></extra>")
        else:
            axis.update(ticksuffix="%", tickformat=".1f")
            trace.hovertemplate = ("Tỉ lệ rời bỏ: %{y:.1f}%<br>Khách có từ đầu tháng: %{customdata[2]}"
                                   "<br>Số khách đó rời bỏ: %{customdata[3]}<extra></extra>")
    fig.update_traces(line_width=2, marker_size=8)
    fig.update_xaxes(dtick="M1", tickformat="%m/%Y", hoverformat="%m/%Y")
    fig.update_layout(showlegend=False, hovermode="x unified")
    _clean_facet_titles(fig)
    first, last = monthly["mrr"].iloc[0], monthly["mrr"].iloc[-1]
    change = (last - first) / first * 100 if first else 0
    if len(monthly) > 1:
        direction, word = ("tăng", "lên") if change >= 0 else ("giảm", "xuống")
        title = (f"MRR {direction} {abs(change):.0f}% (từ ${first:,.0f} {word} ${last:,.0f}); "
                 f"tỉ lệ rời bỏ tháng gần nhất {_pct(monthly['churn_rate'].iloc[-1])}, "
                 f"trung bình {_pct(average_monthly_churn(monthly))} mỗi tháng")
    else:
        title = f"MRR ${last:,.0f}, tỉ lệ rời bỏ {_pct(monthly['churn_rate'].iloc[-1])} trong tháng đã chọn"
    caption = ("MRR: Tổng tiền gói mà các khách đang dùng trả trong tháng. Tỉ lệ rời bỏ tháng: Trong số khách có "
               "từ đầu tháng, bao nhiêu phần trăm rời bỏ trong tháng đó.")
    return title, caption, _style(fig, mode, 460), to_vietnamese(monthly, MONTHLY_COLUMNS)


def usage_cost_chart(detail, mode):
    p = PALETTE[mode]
    plans = [x for x in PLAN_ORDER if x in set(detail["plan_name"])]
    d = detail.assign(
        tokens_m=detail["tokens_consumed"] / 1_000_000,
        usage_state=np.where(detail["over_limit"], "Vượt giới hạn", "Trong giới hạn"),
    )
    fig = px.scatter(
        d, x="tokens_m", y="ai_api_cost", color="plan_name", symbol="usage_state", facet_col="plan_name",
        category_orders={"plan_name": plans, "usage_state": ["Trong giới hạn", "Vượt giới hạn"]},
        color_discrete_map={k: p[k] for k in PLAN_ORDER},
        symbol_map={"Trong giới hạn": "circle", "Vượt giới hạn": "x"},
        hover_name="customer_name", custom_data=["usage_month", "token_usage_pct", "usage_state", "monthly_price"],
        labels={"tokens_m": "Token (triệu)", "ai_api_cost": "Chi phí AI (USD)", "plan_name": "Gói"},
        opacity=0.75, facet_col_spacing=0.06,
    )
    fig.update_xaxes(matches=None, rangemode="tozero")
    fig.update_yaxes(matches=None, rangemode="tozero", tickprefix="$", showticklabels=True)
    fig.update_traces(marker=dict(size=8, line=dict(width=1, color="rgba(255,255,255,0.6)")),
                      hovertemplate="<b>%{hovertext}</b><br>Tháng: %{customdata[0]|%m/%Y}"
                                    "<br>Token: %{x:.2f} triệu<br>Chi phí AI: $%{y:,.2f}<br>Giá gói: $%{customdata[3]:,.0f}"
                                    "<br>Mức dùng: %{customdata[1]:.0f}% giới hạn<br>%{customdata[2]}<extra></extra>")
    for i, plan in enumerate(plans, start=1):
        rows = d[d["plan_name"] == plan]
        limit = rows["ai_token_limit"].iloc[0] / 1_000_000
        side = "top right" if limit < 0.6 * max(rows["tokens_m"].max(), limit) else "top left"
        fig.add_vline(x=limit, col=i, line_dash="dot", line_width=1.5, line_color=p["critical"],
                      annotation_text=f"Giới hạn {limit:g} triệu", annotation_position=side,
                      annotation_font_color=p["critical"], annotation_font_size=11)
    fig.update_layout(showlegend=False)
    _clean_facet_titles(fig)
    rate = d["ai_api_cost"].sum() / d["tokens_consumed"].sum() * 1_000_000
    over = d["over_limit"]
    over_cost_share = d.loc[over, "ai_api_cost"].sum() / d["ai_api_cost"].sum() * 100
    title = f"Chi phí AI tăng đều theo lượng token, khoảng ${rate:.1f} mỗi triệu token; "
    if over.any():
        title += (f"{over.mean() * 100:.0f}% số tháng khách dùng vượt giới hạn, các tháng này chiếm "
                  f"{over_cost_share:.0f}% chi phí AI")
    else:
        title += "không có tháng nào khách dùng vượt giới hạn"
    caption = ("Token là đơn vị đo lượng AI khách dùng. Mỗi điểm là 1 khách hàng trong 1 tháng, mỗi ô là 1 gói. "
               "Chấm tròn: Trong giới hạn. Dấu x: Vượt giới hạn. Đường chấm đỏ: Giới hạn token của gói.")
    summary = (d.groupby("plan_name", observed=True)
                 .agg(customer_months=("customer_id", "size"), over_months=("over_limit", "sum"),
                      tokens=("tokens_consumed", "sum"), revenue=("monthly_price", "sum"),
                      ai_cost=("ai_api_cost", "sum"))
                 .reindex(plans).reset_index())
    summary["over_pct"] = (summary["over_months"] / summary["customer_months"] * 100).round(1)
    summary["margin_pct"] = ((summary["revenue"] - summary["ai_cost"]) / summary["revenue"] * 100).round(1)
    table = summary.rename(columns={
        "plan_name": "Gói", "customer_months": "Số tháng sử dụng", "over_months": "Số tháng vượt",
        "over_pct": "% vượt giới hạn", "tokens": "Tổng token", "revenue": "Doanh thu (USD)",
        "ai_cost": "Chi phí AI (USD)", "margin_pct": "Biên lợi nhuận (%)"})
    return title, caption, _style(fig, mode, 420), table


def churn_reason_chart(reasons, mode):
    p = PALETTE[mode]
    total = reasons["churned_customers"].sum()
    r = reasons.assign(
        group=np.where(is_cost_reason(reasons["churn_reason"]), COST_GROUP, OTHER_GROUP),
        share=(reasons["churned_customers"] / total * 100).round(1),
    )
    fig = px.bar(
        r, x="churned_customers", y="churn_reason", orientation="h", color="group", text="churned_customers",
        color_discrete_map={COST_GROUP: p["critical"], OTHER_GROUP: p["neutral"]},
        category_orders={"group": [COST_GROUP, OTHER_GROUP]}, custom_data=["share"],
        labels={"churned_customers": "Số khách rời bỏ", "churn_reason": ""},
    )
    fig.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0,
                      hovertemplate="%{y}<br>Số khách: %{x} (%{customdata[0]:.1f}%)<extra></extra>")
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_xaxes(showticklabels=False, title="", range=[0, r["churned_customers"].max() * 1.2])
    fig.update_layout(barcornerradius=4, bargap=0.35,
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0))
    cost_share = r.loc[r["group"] == COST_GROUP, "churned_customers"].sum() / total * 100
    top = r.sort_values(["churned_customers", "churn_reason"], ascending=[False, True]).iloc[0]
    if total < 5:
        title = f"Chỉ có {total} khách rời bỏ, quá ít để so sánh các lý do"
    else:
        title = (f"{cost_share:.0f}% khách rời bỏ nêu lý do chi phí; lý do được nêu nhiều nhất: "
                 f"\"{top['churn_reason']}\" ({top['share']:.0f}%)")
    caption = f"{total} khách rời bỏ trong kỳ."
    table = r.sort_values("churned_customers", ascending=False)[["churn_reason", "churned_customers", "share"]]
    table = table.rename(columns={"churn_reason": "Lý do", "churned_customers": "Số khách", "share": "% khách rời bỏ"})
    return title, caption, _style(fig, mode, 380), table


def risk_heatmap(segments, customers, mode):
    sizes = [s for s in SIZE_ORDER if s in set(segments["company_size"])]
    rate = segments.pivot(index="company_size", columns="usage_band", values="churn_rate").reindex(
        index=sizes, columns=BAND_ORDER)
    counts = segments.pivot(index="company_size", columns="usage_band", values="customers").reindex(
        index=sizes, columns=BAND_ORDER)
    fig = px.imshow(
        rate, color_continuous_scale=HEAT_SCALE, zmin=0, zmax=max(float(np.nanmax(rate.values)), 10.0),
        aspect="auto", labels=dict(x="Mức dùng token cao nhất trong kỳ<br>(% giới hạn của gói)", y="",
                                   color="Rời bỏ (%)"),
    )
    labels = rate.apply(lambda col: col.map(lambda v: "" if pd.isna(v) else f"{v:.0f}%"))
    fig.update_traces(
        customdata=counts.fillna(0).astype(int).values, xgap=3, ygap=3,
        text=labels.values, texttemplate="%{text}", textfont=dict(size=15),
        hovertemplate="Quy mô: %{y}<br>Mức dùng: %{x}<br>Tỉ lệ rời bỏ: %{z:.1f}%<br>Số khách: %{customdata}"
                      "<extra></extra>",
    )
    fig.update_xaxes(side="bottom")
    fig.update_coloraxes(colorbar=dict(ticksuffix="%", thickness=12))
    worst = segments.sort_values("churn_rate", ascending=False).iloc[0]
    others = segments.drop(worst.name)
    if segments["churn_rate"].max() - segments["churn_rate"].min() < 1:
        title = f"Các nhóm có tỉ lệ rời bỏ như nhau: {worst['churn_rate']:.0f}% ở mọi ô"
    elif worst["churned_customers"] < 3:
        title = f"Quá ít khách rời bỏ để so sánh các nhóm ({int(segments['churned_customers'].sum())} khách rời bỏ)"
    else:
        low, high = f"{others['churn_rate'].min():.0f}%", f"{others['churn_rate'].max():.0f}%"
        title = (f"{worst['company_size']} dùng {BAND_TEXT[worst['usage_band']]} giới hạn token rời bỏ nhiều nhất: "
                 f"{worst['churn_rate']:.0f}%, trong khi các nhóm khác chỉ "
                 + (low if low == high else f"từ {low} đến {high}"))
    caption = f"{customers} khách hàng trong kỳ."
    if rate.isna().to_numpy().any():
        caption += " Ô trống: Nhóm có dưới 5 khách hàng, không đủ để tính tỉ lệ."
    table = segments.rename(columns={"company_size": "Quy mô", "usage_band": "Mức dùng token",
                                     "customers": "Số khách", "churned_customers": "Số khách rời bỏ",
                                     "churn_rate": "Tỉ lệ rời bỏ (%)"})
    return title, caption, _style(fig, mode, 380), table
