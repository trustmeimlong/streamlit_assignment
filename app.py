from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import charts
import metrics
import queries as q
from db import run_query
from exports import XLSX_MIME, to_csv_bytes, to_excel_bytes

st.set_page_config(page_title="Khách hàng & Chi phí AI", page_icon="📊", layout="wide")

REPORT_PATH = Path(__file__).parent / "REPORT.md"
DB_HINT = ("Kiểm tra: (1) MySQL đang chạy, (2) đã chạy `python scripts/setup_database.py`, "
           "(3) thông tin kết nối trong `.streamlit/secrets.toml` đúng.")


def month_start(d):
    return date(d.year, d.month, 1)


def month_end(d):
    return q.add_months(month_start(d), 1) - timedelta(days=1)


def stop_with_db_error(error):
    st.error(f"Không thể truy vấn CSDL MySQL. {DB_HINT}")
    with st.expander("Chi tiết lỗi kỹ thuật"):
        st.code(f"{type(error).__name__}: {error}")
    st.stop()


def table_config(df):
    config = {}
    for col in df.columns:
        if col.startswith("Tháng"):
            config[col] = st.column_config.DateColumn(col, format="MM/YYYY")
        elif not pd.api.types.is_numeric_dtype(df[col]):
            continue
        elif col == "Mức dùng token cao nhất (%)":
            config[col] = st.column_config.ProgressColumn(col, format="%.0f%%", min_value=0, max_value=200)
        elif col.endswith("(USD)"):
            config[col] = st.column_config.NumberColumn(col, format="dollar")
        elif col.endswith("(%)") or col.startswith("%"):
            config[col] = st.column_config.NumberColumn(col, format="%.1f%%")
        elif col.startswith("Ticket trung bình"):
            config[col] = st.column_config.NumberColumn(col, format="%.2f")
        elif "token" in col.lower():
            config[col] = st.column_config.NumberColumn(col, format="localized")
    return config


def escape_dollars(text):
    return text.replace("$", "\\$")


def chart_block(title, caption, fig, table):
    st.markdown(f"##### {escape_dollars(title)}")
    if caption:
        st.caption(escape_dollars(caption))
    st.plotly_chart(fig, config={"displaylogo": False})
    with st.expander("📋 Bảng số liệu"):
        st.dataframe(table, hide_index=True, column_config=table_config(table), height=35 * (len(table) + 1) + 3)


try:
    options = run_query(q.OPTIONS_SQL)
except Exception as error:
    stop_with_db_error(error)

first_month, last_month = options.at[0, "first_month"], options.at[0, "last_month"]
if pd.isna(first_month):
    st.warning("CSDL chưa có dữ liệu. Hãy chạy `python scripts/setup_database.py` để tạo dữ liệu mẫu.")
    st.stop()
all_sizes = options.at[0, "sizes"].split(",")

with st.sidebar:
    st.title("📊 Bộ lọc dữ liệu")
    start_date = st.date_input("📅 Từ ngày", value=first_month, min_value=first_month,
                               max_value=month_end(last_month), format="DD/MM/YYYY",
                               help="Số liệu tính theo tháng: Chọn ngày nào trong tháng cũng tính cả tháng đó.")
    end_date = st.date_input("📅 Đến ngày", value=month_end(last_month), min_value=first_month,
                             max_value=month_end(last_month), format="DD/MM/YYYY")
    sizes = st.multiselect("🏢 Quy mô công ty", all_sizes, default=all_sizes,
                           help="Startup: Công ty khởi nghiệp. SMB: Doanh nghiệp vừa và nhỏ. Enterprise: Doanh nghiệp lớn.")
    status = st.selectbox("🔖 Trạng thái dịch vụ", q.STATUS_OPTIONS,
                          help="Trạng thái hiện tại của khách: Active là đang dùng, Upgraded là đã nâng cấp gói, "
                               "Churned là đã rời bỏ.")
    if st.button("🔄 Làm mới dữ liệu"):
        st.cache_data.clear()
        st.rerun()

start_month, end_month = month_start(start_date), month_start(end_date)

st.title("📊 Khách Hàng Rời Bỏ & Chi Phí AI")
st.caption(f"Kỳ: {start_month:%m/%Y} - {end_month:%m/%Y} | Quy mô: {', '.join(sizes) or 'Chưa chọn'} | "
           f"Trạng thái: {status}")

if start_date > end_date:
    st.warning("Ngày bắt đầu không được sau ngày kết thúc.")
    st.stop()
if not sizes:
    st.warning("Hãy chọn ít nhất một quy mô công ty.")
    st.stop()

filters = q.Filters(start_month, end_month, tuple(sizes), status)
built = {name: build(filters) for name, build in q.QUERY_BUILDERS.items()}
try:
    raw = {name: run_query(sql, params) for name, (sql, params) in built.items()}
except Exception as error:
    stop_with_db_error(error)

if raw["detail"].empty:
    st.warning("Không tìm thấy dữ liệu phù hợp với bộ lọc hiện tại.")
    st.stop()

detail = metrics.prepare_detail(raw["detail"])
monthly = metrics.prepare_monthly(raw["monthly"])
risk = metrics.prepare_risk(raw["risk_customers"])
kpi = metrics.compute_kpis(monthly, detail)
mode = "dark" if getattr(st.context.theme, "type", None) == "dark" else "light"

if status != q.ALL_STATUSES:
    st.info(f"Đang lọc trạng thái **{status}**: Các chỉ số chỉ tính trên nhóm khách hàng này.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Doanh thu tháng", f"${kpi['mrr']:,.0f}",
          delta=None if kpi["mrr_delta"] is None else f"{kpi['mrr_delta']:,.0f}",
          delta_description="so tháng trước", chart_data=monthly["mrr"], chart_type="area", border=True,
          help=f"MRR: Tổng tiền gói mà các khách đang dùng trả trong tháng {kpi['last_month']:%m/%Y}. Dòng dưới: "
               "Thay đổi so với tháng trước.")
c2.metric("📉 Tỉ lệ rời bỏ",
          "-" if pd.isna(kpi["churn_monthly"]) else f"{kpi['churn_monthly']:.1f}%",
          delta=f"{kpi['churned']}/{kpi['customers']} ({kpi['churn_rate']:.1f}%)", delta_color="red",
          delta_arrow="off", delta_description="cả kỳ", chart_data=monthly["churn_rate"].dropna(),
          border=True,
          help="Churn Rate: Số lớn là trung bình mỗi tháng có bao nhiêu phần trăm khách rời bỏ. Dòng dưới: Số khách "
               "đã rời bỏ trên tổng số khách trong cả kỳ.")
c3.metric("🤖 Lợi nhuận sau AI", f"${kpi['profit']:,.0f}",
          delta=f"{kpi['margin']:.1f}%", delta_arrow="off", delta_description="biên lợi nhuận",
          chart_data=monthly["ai_profit"], border=True,
          help="Net AI Profitability: Tiền thu từ gói trừ chi phí AI trong kỳ. Dòng dưới: Biên lợi nhuận của cả kỳ, "
               "tức phần trăm doanh thu còn lại sau khi trả chi phí AI.")
c4.metric("🎫 Ticket trung bình", f"{kpi['avg_tickets']:.2f}",
          delta=kpi["tickets_delta"], delta_color="inverse", delta_description="so tháng trước",
          chart_data=monthly["avg_tickets"], chart_type="bar", border=True,
          help="Avg Support Tickets: Số yêu cầu hỗ trợ trung bình mỗi khách gửi trong một tháng. Dòng dưới: Tháng "
               "gần nhất so với tháng trước.")

tab_overview, tab_risk, tab_data, tab_report = st.tabs(
    ["📈 Tổng quan", f"⚠️ Khách hàng rủi ro ({len(risk)})", "📥 Dữ liệu & Xuất file", "📝 Báo cáo"])

with tab_overview:
    chart_block(*charts.trend_chart(monthly, mode))
    st.divider()
    chart_block(*charts.usage_cost_chart(detail, mode))
    st.divider()
    left, right = st.columns(2, gap="large")
    with left:
        if raw["churn_reason"].empty:
            st.markdown("##### Lý do rời bỏ dịch vụ")
            st.info("Không có khách hàng rời bỏ trong bộ lọc hiện tại.")
        else:
            chart_block(*charts.churn_reason_chart(raw["churn_reason"], mode))
    with right:
        if raw["risk_segment"].empty:
            st.markdown("##### Rủi ro rời bỏ theo quy mô công ty")
            st.info(f"Mọi nhóm đều có dưới {q.MIN_SEGMENT_CUSTOMERS} khách hàng, chưa đủ để tính tỉ lệ.")
        else:
            chart_block(*charts.risk_heatmap(raw["risk_segment"], kpi["customers"], mode))

with tab_risk:
    st.markdown("##### Khách hàng đang dùng có dấu hiệu rủi ro rời bỏ")
    window = (end_month.year - filters.recent_start.year) * 12 + end_month.month - filters.recent_start.month + 1
    window_text = (f"Xét tháng {end_month:%m/%Y}." if window == 1 else
                   f"Xét {window} tháng gần nhất ({filters.recent_start:%m/%Y} - {end_month:%m/%Y}).")
    st.caption(f"{window_text} Mức Cao: Đã dùng vượt lượng token của gói. Mức Theo dõi: Gửi hơn "
               f"{q.TICKET_THRESHOLD} ticket trong 1 tháng.")
    backtest = metrics.summarize_backtest(raw["risk_backtest"])
    if backtest["n_high"] >= 20 and backtest["events"] >= 5 and backtest["rest"] > 0:
        st.caption(f"Trước đây, khách rủi ro Cao rời bỏ ngay tháng sau {backtest['high']:.1f}%, so với "
                   f"{backtest['rest']:.1f}% ở khách còn lại.")
    if risk.empty:
        st.success("Không có khách hàng nào có dấu hiệu rủi ro trong bộ lọc hiện tại.")
    else:
        is_high = risk["risk_level"] == metrics.HIGH_RISK
        mrr_high = risk.loc[is_high, "monthly_price"].sum()
        summary = []
        if is_high.any():
            summary.append(f"**{int(is_high.sum())} khách rủi ro Cao** đang trả **${mrr_high:,.0f} mỗi tháng** "
                           f"({mrr_high / kpi['mrr'] * 100 if kpi['mrr'] else 0:.0f}% MRR).")
        if (~is_high).any():
            summary.append(f"{int((~is_high).sum())} khách cần theo dõi.")
        st.warning(escape_dollars(" ".join(summary)))
        search = st.text_input("🔎 Tìm khách hàng", placeholder="Nhập tên công ty")
        view = risk[risk["customer_name"].str.contains(search, case=False, regex=False)] if search else risk
        if view.empty:
            st.info("Không tìm thấy khách hàng phù hợp.")
        else:
            risk_table = metrics.to_vietnamese(view, metrics.RISK_COLUMNS)
            st.dataframe(risk_table, hide_index=True, column_config=table_config(risk_table))

with tab_data:
    detail_table = metrics.to_vietnamese(detail, metrics.DETAIL_COLUMNS)
    st.markdown("##### Dữ liệu đã lọc")
    st.dataframe(detail_table, hide_index=True, column_config=table_config(detail_table), height=420)
    stamp = f"{start_month:%Y%m}_{end_month:%Y%m}"
    with st.container(horizontal=True, gap="small"):
        st.download_button("📄 Tải CSV", to_csv_bytes(detail_table), f"saas_ai_chi_tiet_{stamp}.csv", "text/csv")
        st.download_button("📊 Tải Excel", to_excel_bytes({
            "Chi tiết": detail_table,
            "Khách hàng rủi ro": metrics.to_vietnamese(risk, metrics.RISK_COLUMNS),
            "Theo tháng": metrics.to_vietnamese(monthly, metrics.MONTHLY_COLUMNS),
        }), f"saas_ai_bao_cao_{stamp}.xlsx", XLSX_MIME)

with tab_report:
    st.caption("Số liệu trong báo cáo tính trên toàn bộ dữ liệu và không thay đổi theo bộ lọc.")
    if REPORT_PATH.exists():
        st.markdown(REPORT_PATH.read_text(encoding="utf-8"))
    else:
        st.info("Chưa có file REPORT.md.")

st.divider()
with st.expander("🔎 Trình duyệt SQL: Câu lệnh dùng để lấy dữ liệu trên trang"):
    for tab, name in zip(st.tabs(list(q.QUERY_LABELS.values())), q.QUERY_LABELS):
        sql, params = built[name]
        with tab:
            st.code(sql, language="sql")
            st.json({k: str(v) for k, v in params.items()})
