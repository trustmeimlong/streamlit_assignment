# Unified SaaS & AI Cost Analytics Dashboard

Dashboard Streamlit + MySQL phân tích tỉ lệ khách hàng rời bỏ (churn) và chi phí tích hợp AI của một dịch vụ
SaaS theo gói thuê bao. Báo cáo insight nằm trong [REPORT.md](REPORT.md) và trong tab "Báo cáo" của ứng dụng.

**Video demo:** [LINK_VIDEO_DEMO](https://drive.google.com/file/d/1byyL0QtcS4wTeGknu2upqpCYQl_PMXg9/view?usp=share_link)

## Cấu trúc thư mục

| File | Nội dung |
| --- | --- |
| `app.py` | Giao diện: Sidebar, KPI, tab, biểu đồ, bảng, xuất file, trình duyệt SQL |
| `db.py` | Kết nối MySQL (`@st.cache_resource`) và chạy truy vấn (`@st.cache_data`) |
| `queries.py` | Toàn bộ câu SQL và bộ dựng điều kiện động `WHERE 1=1` có tham số |
| `metrics.py` | Tính KPI, chuẩn hóa dữ liệu, tên cột tiếng Việt |
| `charts.py` | 4 biểu đồ Plotly Express với tiêu đề hành động |
| `exports.py` | Xuất CSV (UTF-8 BOM) và Excel nhiều sheet |
| `sql/schema.sql` | Tạo CSDL `SaaS_AI_DB`: 4 bảng, khóa chính, khóa ngoại, ràng buộc |
| `sql/seed_data.sql` | Dữ liệu mẫu, sinh bởi `scripts/generate_data.py` |
| `sql/insight_queries.sql` | Các truy vấn dùng cho `REPORT.md` |
| `scripts/generate_data.py` | Sinh dữ liệu mẫu với seed cố định để kết quả lặp lại được |
| `scripts/setup_database.py` | Chạy `schema.sql` và `seed_data.sql` vào MySQL |
| `scripts/insight_stats.py` | Tái lập mọi con số trong `REPORT.md`: Chạy các truy vấn, tính khoảng tin cậy 95% và kiểm định Fisher |
| `.streamlit/secrets.toml.example` | Mẫu file cấu hình kết nối |

## Cài đặt & chạy

Yêu cầu: Python 3.12 trở lên và MySQL 8.0 trở lên. Trên Windows, dùng `python` thay cho `python3` và
`.venv\Scripts\` thay cho `.venv/bin/`.

1. Tạo môi trường ảo và cài thư viện:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Tạo file kết nối từ mẫu, rồi điền mật khẩu MySQL:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
3. Tạo CSDL và nạp dữ liệu mẫu. Lưu ý: Script này **xóa và tạo lại** `SaaS_AI_DB`.
   ```bash
   .venv/bin/python scripts/setup_database.py
   ```
   Hoặc dùng MySQL CLI: `mysql -u root -p < sql/schema.sql` rồi `mysql -u root -p < sql/seed_data.sql`.
4. Chạy ứng dụng:
   ```bash
   .venv/bin/streamlit run app.py
   ```
5. Tái lập số liệu của báo cáo (tùy chọn):
   ```bash
   .venv/bin/python scripts/insight_stats.py
   ```

## Chức năng theo yêu cầu đề bài

| Yêu cầu | Cách thực hiện |
| --- | --- |
| Bộ lọc Date range, Multiselect, Dropdown | 2 ô `st.date_input` từ ngày và đến ngày (làm tròn theo tháng), `st.multiselect` quy mô công ty, `st.selectbox` trạng thái kèm "Tất cả" |
| Bộ lọc liên kết với SQL | `queries.build_where()` dựng `WHERE 1=1` và chỉ thêm `AND ...` cho bộ lọc được chọn; giá trị truyền bằng tham số `:tên` |
| `JOIN`, `GROUP BY`, `HAVING` | 6 truy vấn dùng chung CTE `latest_status` (`ROW_NUMBER()` lấy trạng thái mới nhất); `HAVING` lọc khách rủi ro và ẩn nhóm dưới 5 khách; hàm cửa sổ `MAX() OVER`, `LEAD()` để kiểm chứng quy tắc rủi ro |
| KPI: MRR, Churn Rate, Net AI Profitability, Avg Support Tickets | 4 thẻ `st.metric` kèm biểu đồ nhỏ theo tháng, nhãn tiếng Việt và tên KPI gốc trong chú thích; thẻ Tỉ lệ rời bỏ hiển thị tỉ lệ trung bình tháng và tỉ lệ theo công thức đề bài |
| 4 biểu đồ Plotly Express | Line (MRR và churn theo tháng), Scatter (token và chi phí AI theo gói), Bar (lý do churn), Heatmap (churn theo quy mô công ty và mức dùng token) |
| Bảng khách hàng rủi ro | Vượt giới hạn token hoặc hơn 3 ticket/tháng trong 3 tháng gần nhất; sắp xếp, tìm kiếm; mức Cao/Theo dõi kèm kết quả kiểm chứng trên dữ liệu quá khứ |
| Xuất dữ liệu | CSV và Excel (3 sheet) theo đúng bộ lọc đang chọn |
| Trình duyệt SQL | `st.expander` hiển thị câu SQL và tham số của từng truy vấn |
| Caching & xử lý lỗi | `@st.cache_resource` cho engine, `@st.cache_data(ttl=600)` cho kết quả; lỗi kết nối hiện hướng dẫn thay vì traceback |

