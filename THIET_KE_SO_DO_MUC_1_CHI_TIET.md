# THIẾT KẾ SƠ ĐỒ MỨC 1 — CHI TIẾT ĐẶC TẢ (Detailed Specifications)
# HỆ THỐNG BI DASHBOARD — Contoso Retail Intelligence System v5.0

> Tài liệu bổ sung chi tiết cho file `THIET_KE_SO_DO_MUC_1.md`.  
> Bao gồm: Đặc tả Use Case đầy đủ (Full UC Specification), Sequence Diagram chi tiết từng bước với dữ liệu thực, DFD chi tiết đến cấp trường dữ liệu.

---

## MỤC LỤC

- [PHẦN A — ĐẶC TẢ USE CASE CHI TIẾT](#phần-a--đặc-tả-use-case-chi-tiết)
  - [A.1 UC1.1 – Đăng nhập hệ thống](#a1-uc11--đăng-nhập-hệ-thống)
  - [A.2 UC2.1 – Xem Dashboard Bán hàng & Lợi nhuận](#a2-uc21--xem-dashboard-bán-hàng--lợi-nhuận)
  - [A.3 UC3.2 – Phân tích phân khúc khách hàng RFM](#a3-uc32--phân-tích-phân-khúc-khách-hàng-rfm)
  - [A.4 UC4.1 – Xem Dashboard Hiệu suất Nhân viên](#a4-uc41--xem-dashboard-hiệu-suất-nhân-viên)
  - [A.5 UC5.4 – Xem chi tiết dự báo sản phẩm (Deep Dive)](#a5-uc54--xem-chi-tiết-dự-báo-sản-phẩm-deep-dive)
  - [A.6 UC6.2 – Chạy ETL Pipeline](#a6-uc62--chạy-etl-pipeline)
  - [A.7 UC6.4 – Upload CSV vào Data Warehouse](#a7-uc64--upload-csv-vào-data-warehouse)
  - [A.8 UC7.1 – Nhận dữ liệu Realtime qua SSE](#a8-uc71--nhận-dữ-liệu-realtime-qua-sse)
- [PHẦN B — SEQUENCE DIAGRAM CHI TIẾT](#phần-b--sequence-diagram-chi-tiết)
- [PHẦN C — DFD MỨC 1 CHI TIẾT](#phần-c--dfd-mức-1-chi-tiết)

---

# PHẦN A — ĐẶC TẢ USE CASE CHI TIẾT

> Mỗi Use Case được đặc tả theo chuẩn Cockburn Template gồm:  
> **ID, Tên, Actor, Mô tả, Điều kiện tiên quyết (Precondition), Luồng chính (Main Flow), Luồng thay thế (Alternative Flow), Luồng ngoại lệ (Exception Flow), Điều kiện kết thúc (Postcondition), Dữ liệu trao đổi, Quy tắc nghiệp vụ.**

---

## A.1 UC1.1 – Đăng nhập hệ thống

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC1.1 |
| **Tên Use Case** | Đăng nhập hệ thống |
| **Actor chính** | Admin, Executive, Regional Manager, Store Manager |
| **Actor phụ** | MySQL Database (hệ thống), Hệ thống JWT (nội bộ) |
| **Mô tả tổng quan** | Người dùng nhập thông tin đăng nhập (username/password), hệ thống xác thực và cấp JWT token để truy cập các chức năng được phân quyền. |
| **Trigger (Kích hoạt)** | Người dùng truy cập URL `/login` hoặc bị chuyển hướng từ AuthGuard |
| **Mức độ** | User Goal |
| **Tần suất** | Mỗi phiên làm việc (token hết hạn sau 24 giờ) |

### Điều kiện tiên quyết (Preconditions)
1. Hệ thống Backend (FastAPI) đang chạy tại `http://localhost:8000`
2. Hệ thống Frontend (Next.js) đang chạy tại `http://localhost:3000`
3. Database MySQL `retails_dataset` đang hoạt động
4. Bảng `bi_users` đã được khởi tạo (có ít nhất 7 tài khoản demo)
5. Người dùng chưa đăng nhập (không có token hợp lệ trong `localStorage`)

### Luồng chính (Main Flow / Basic Flow)

| Bước | Actor | Hệ thống | Dữ liệu |
|------|-------|----------|---------|
| 1 | Người dùng mở trình duyệt, truy cập `http://localhost:3000` | | |
| 2 | | `AuthGuard` component kiểm tra `localStorage`: không có `bi_token` → redirect đến `/login` | Kiểm tra: `localStorage.getItem("bi_token")` |
| 3 | | Frontend render trang Login gồm: form đăng nhập + 6 nút tài khoản demo | |
| 4 | Người dùng nhập `username` vào ô "Tên đăng nhập" | | username: string, maxlength=100 |
| 5 | Người dùng nhập `password` vào ô "Mật khẩu" | | password: string (ẩn bởi `type="password"`) |
| 6 | Người dùng nhấn nút **"Đăng nhập"** | | |
| 7 | | Frontend gọi Zustand action `login(username, password)` | |
| 8 | | Zustand store gửi `POST /auth/login` với body: `{"username": "<value>", "password": "<value>"}`, header: `Content-Type: application/json` | Request Body: `LoginRequest {username: str, password: str}` |
| 9 | | Backend `auth_api.py → login()` nhận request, gọi `authenticate_user(engine, body.username, body.password)` | |
| 10 | | `auth.py → authenticate_user()` truy vấn: `SELECT * FROM bi_users WHERE username = :u AND is_active = 1` | Query param: `{u: username}` |
| 11 | | MySQL trả về bản ghi user (hoặc None) | Row: `{id, username, password_hash, role, region, store_key, employee_key, display_name, is_active}` |
| 12 | | `verify_password(plain, stored)`: Tách `salt` và `hash` từ `password_hash` (format: `salt$hash`). Tính `SHA-256(salt:plain)`, dùng `hmac.compare_digest()` so sánh. Trả `True` nếu khớp. | |
| 13 | | `create_access_token(user)`: Tạo JWT payload: `{sub: username, uid: id, role: role, region: region, store_key: store_key, display_name: display_name, iat: now, exp: now + 24*3600}`. Ký bằng `HS256` với `JWT_SECRET`. | JWT Token string |
| 14 | | Backend trả response `200 OK`: `{"access_token": "<jwt>", "token_type": "bearer", "user": {"id": 1, "username": "admin", "role": "admin", "region": null, "store_key": null, "display_name": "System Administrator"}}` | `LoginResponse` |
| 15 | | Zustand store lưu: `localStorage.setItem("bi_token", data.access_token)` + `localStorage.setItem("bi_user", JSON.stringify(data.user))` + cập nhật state `{token, user}` | |
| 16 | | `router.replace("/dashboard")` — chuyển hướng đến Dashboard | |
| 17 | Người dùng thấy trang Dashboard | | |

### Luồng thay thế (Alternative Flows)

**AF1: Đăng nhập nhanh (Demo Login)**

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 4a | Người dùng nhấn 1 trong 6 nút demo (ví dụ: "CEO") | |
| 4b | | Frontend gọi `quickLogin("ceo", "demo123")`: tự động set `username="ceo"`, `password="demo123"` rồi gọi `login("ceo", "demo123")` |
| 4c | | Tiếp tục từ bước 8 của luồng chính |

**AF2: Người dùng đã đăng nhập**

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 2a | | `AuthGuard` kiểm tra `localStorage`: có `bi_token` hợp lệ → redirect đến `/dashboard` |
| 2b | | Login page component: `useEffect(() => { if (token) router.replace("/dashboard"); })` |

**AF3: Toggle hiển thị mật khẩu**

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 5a | Người dùng nhấn icon mắt (Eye/EyeOff) | Frontend toggle `showPw` state, input `type` chuyển giữa `"password"` ↔ `"text"` |

### Luồng ngoại lệ (Exception Flows)

**EF1: Sai tên đăng nhập hoặc mật khẩu**

| Bước | Hệ thống |
|------|----------|
| 10a | `authenticate_user()` trả về `None` (user không tồn tại hoặc `is_active = 0`) |
| 10b | HOẶC `verify_password()` trả về `False` (mật khẩu sai) |
| 10c | Backend raise `HTTPException(status_code=401, detail="Invalid username or password")` |
| 10d | Frontend Zustand: `set({ loading: false, error: body.detail \|\| "Login failed" })` |
| 10e | Trang Login hiển thị thông báo lỗi màu đỏ: "Invalid username or password" |

**EF2: Lỗi mạng (Network Error)**

| Bước | Hệ thống |
|------|----------|
| 8a | `fetch()` throw Error (server không phản hồi, CORS blocked, timeout) |
| 8b | Zustand catch: `set({ loading: false, error: "Network error" })` |
| 8c | Trang Login hiển thị thông báo lỗi: "Network error" |

**EF3: Token hết hạn (đã đăng nhập trước đó)**

| Bước | Hệ thống |
|------|----------|
| 1a | User truy cập Dashboard, `AuthGuard` gửi `GET /auth/me` với Bearer token |
| 1b | Backend: `jwt_decode()` → `payload["exp"] < time.time()` → raise `ValueError("JWT expired")` |
| 1c | `get_current_user()` raise `HTTPException(status_code=401)` |
| 1d | Frontend nhận 401, redirect về `/login` |

### Điều kiện kết thúc (Postconditions)

**Thành công:**
- `localStorage` chứa `bi_token` (JWT string) và `bi_user` (JSON)
- Zustand state: `token != null`, `user != null`
- Người dùng ở trang `/dashboard`

**Thất bại:**
- `localStorage` không thay đổi
- Zustand state: `token = null`, `error != null`
- Người dùng vẫn ở trang `/login`, thấy thông báo lỗi

### Dữ liệu trao đổi chi tiết

**Request (Frontend → Backend):**
```json
POST /auth/login
Content-Type: application/json

{
  "username": "ceo",
  "password": "demo123"
}
```

**Response thành công (Backend → Frontend):**
```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 2,
    "username": "ceo",
    "role": "executive",
    "region": null,
    "store_key": null,
    "display_name": "CEO / Ban Giám đốc"
  }
}
```

**JWT Payload (decoded):**
```json
{
  "sub": "ceo",
  "uid": 2,
  "role": "executive",
  "region": null,
  "store_key": null,
  "display_name": "CEO / Ban Giám đốc",
  "iat": 1711756800,
  "exp": 1711843200
}
```

**Response thất bại:**
```json
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "detail": "Invalid username or password"
}
```

### Quy tắc nghiệp vụ (Business Rules)

| # | Quy tắc | Mô tả |
|---|---------|-------|
| BR1.1 | Password Hashing | SHA-256 + random salt (16 bytes hex) + `hmac.compare_digest()` chống timing attack |
| BR1.2 | JWT Algorithm | HS256 (HMAC-SHA256), secret key từ biến môi trường `JWT_SECRET` |
| BR1.3 | Token Expiry | 24 giờ (cấu hình bởi `JWT_EXPIRY_HOURS`) |
| BR1.4 | Valid Roles | Chỉ 4 giá trị: `"executive"`, `"regional_manager"`, `"store_manager"`, `"admin"` |
| BR1.5 | Account Active | Chỉ user có `is_active = 1` mới đăng nhập được |
| BR1.6 | Anonymous Fallback | Nếu request không có Bearer token → tạo `UserContext(role="admin", is_anonymous=True)` (backward compatible) |
| BR1.7 | Demo Accounts | 7 tài khoản seed: admin/admin123, ceo/demo123, rm_asia/demo123, rm_europe/demo123, rm_na/demo123, sm_store4/demo123, sm_store156/demo123 |

---

## A.2 UC2.1 – Xem Dashboard Bán hàng & Lợi nhuận

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC2.1 |
| **Tên Use Case** | Xem Dashboard Bán hàng & Lợi nhuận |
| **Actor chính** | Admin, Executive, Regional Manager, Store Manager |
| **Mô tả** | Hiển thị tổng quan bán hàng: KPI cards (YTD/MTD/Total Sales & Profit), biểu đồ xu hướng, phân bổ cửa hàng. Dữ liệu được lọc theo RLS (Row-Level Security) dựa trên vai trò người dùng. |
| **Trigger** | Người dùng truy cập `/dashboard` hoặc thay đổi bộ lọc thời gian |
| **Mức độ** | User Goal |

### Điều kiện tiên quyết
1. Người dùng đã đăng nhập (có JWT token hợp lệ trong `localStorage`)
2. Bảng `summary_daily_sales` có dữ liệu (3,449,574 rows)
3. Backend đang chạy và Parquet cache đã khởi tạo

### Luồng chính

| Bước | Actor | Hệ thống | Dữ liệu |
|------|-------|----------|---------|
| 1 | Người dùng truy cập `/dashboard` | | |
| 2 | | `DashboardLayout` render: `Sidebar` (theo role) + `Header` + Page content | Role từ `useAuth()` |
| 3 | | Dashboard page mount. `preset = 'all'` (mặc định). Tính `dateRange = {start: null, end: null}` | |
| 4 | | Gọi `fetchJsonWithTimeout<SalesDashboardResponse>`: `GET /sale-profit/api/dashboard/sales` + Header `Authorization: Bearer <token>` | |
| 5 | | **[Backend]** `sale_profit_dashboard()`: Gọi `get_current_user(request)` → Decode JWT → Tạo `UserContext` | |
| 6 | | **[Backend]** `get_rls_store_keys(engine, user)`: | |
| | | — Nếu `role = "executive"` hoặc `"admin"` → return `None` (truy cập tất cả) | |
| | | — Nếu `role = "store_manager"` → return `[user.store_key]` (VD: `[4]`) | |
| | | — Nếu `role = "regional_manager"` → Query `DimStore JOIN DimGeography WHERE ContinentName = user.region` → return `[list of StoreKeys]` | |
| 7 | | **[Backend]** `get_sales_profit_dashboard(start, end, store_key, rls_store_keys)` | |
| 8 | | **[Backend]** `load_sales_profit_snapshot()`: Kiểm tra Parquet file `sales_profit_daily_snapshot.parquet` | |
| | | — Cache HIT: `pd.read_parquet()` → return DataFrame | |
| | | — Cache MISS: Query SQL phức tạp (xem bên dưới) → build DataFrame → save Parquet | |
| 9 | | **[Backend]** Apply filters lên DataFrame: | |
| | | `if start_date: df = df[df["Date"] >= pd.to_datetime(start_date)]` | |
| | | `if rls_store_keys is not None: df = df[df["StoreKey"].isin(rls_store_keys)]` | |
| 10 | | **[Backend]** Tính toán KPIs: | |
| | | — `ytd = daily[ytd_mask]["total_sales"].sum()` | |
| | | — `mtd = daily[mtd_mask]["total_sales"].sum()` | |
| | | — `total = daily["total_sales"].sum()` | |
| | | — `yoy_growth = ((ytd - prev_ytd) / prev_ytd) * 100` | |
| | | — `mom_growth = ((mtd - prev_mtd) / prev_mtd) * 100` | |
| | | — `avg_profit_margin = total_profit / total` | |
| 11 | | **[Backend]** Tính toán trend (theo tháng): | |
| | | `monthly = df.assign(month=df["Date"].dt.to_period("M")).groupby("month")[["total_sales", "gross_profit"]].sum()` | |
| 12 | | **[Backend]** Tính Store Pie (top 10): | |
| | | `store = df.groupby("StoreName")["total_sales"].sum().sort_values(ascending=False).head(10)` | |
| 13 | | **[Backend]** Return `SalesDashboardResponse` → `serialize_payload()` → JSON | |
| 14 | | Frontend nhận JSON → `setData(response)` → render: | |
| | | — 7 KPI Cards: YTD Sales, MTD Sales, Total Sales, YTD Profit, MTD Profit, Total Profit, Avg Profit Margin | |
| | | — 2 Growth badges: YoY Growth %, MoM Growth % | |
| | | — LineChart: Sales Trend (monthly) | |
| | | — LineChart: Profit Trend (monthly) | |
| | | — PieChart: Top 10 Stores by Sales | |
| 15 | | **[Song song / Parallel]** Nếu `showGlobalCharts = true` (Executive/Admin): | |
| | | Gọi `GET /sale-profit/api/channels` → render Channel Breakdown BarChart | |
| | | Gọi `GET /sale-profit/api/kpi-summary` → render KpiSummaryCards (7 KPI bổ sung) | |
| | | Gọi `GET /sale-profit/api/sales-per-sqft` → render SalesPerSqftChart | |
| | | Gọi `GET /sale-profit/api/budget-vs-actual` → render BudgetVsActualChart | |
| 16 | Người dùng xem Dashboard | | |

### Luồng thay thế

**AF1: Người dùng thay đổi Time Filter**

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 1a | Nhấn nút preset (YTD / 12M / 6M / 3M / 1M) | `setPreset(key)` → `dateRange` recalculate → trigger `useEffect` |
| 1b | | Re-fetch `GET /sale-profit/api/dashboard/sales?start_date=2025-01-01&end_date=2026-03-30` với khoảng thời gian mới |
| 1c | Hoặc nhấn "Tùy chọn" → chọn Custom Start/End | `setCustomStart()`, `setCustomEnd()` |

**AF2: Store Manager — Giới hạn hiển thị**

| Bước | Hệ thống |
|------|----------|
| 14a | `isStoreManager = true` → ẩn PieChart (Store Pie), ẩn Channel Breakdown, ẩn Sales/Sqft, ẩn Budget vs Actual |
| 14b | Chỉ hiển thị: KPI Cards (cho 1 cửa hàng) + Trend Charts |

**AF3: Regional Manager — Đa cửa hàng trong vùng**

| Bước | Hệ thống |
|------|----------|
| 6a | `rls_store_keys = [list 50-100 StoreKeys trong region]` |
| 14a | Hiện PieChart + Trend + Sales/Sqft + Budget. Ẩn Channel. |

### Luồng ngoại lệ

**EF1: Parquet cache trống & DB connection fail**

| Bước | Hệ thống |
|------|----------|
| 8a | `load_sales_profit_snapshot()` trả `pd.DataFrame()` rỗng |
| 8b | Return `{"status": "empty", "message": "No sales/profit data found.", ...}` |
| 8c | Frontend hiển thị skeleton cards với giá trị $0 |

**EF2: JWT Token hết hạn**

| Bước | Hệ thống |
|------|----------|
| 5a | `get_current_user()` → `jwt_decode()` raise `ValueError("JWT expired")` |
| 5b | `HTTPException(status_code=401, detail="JWT expired")` |
| 5c | Frontend nhận 401 → redirect `/login` |

### Dữ liệu trao đổi

**SQL Query chính (Cache MISS — build Parquet snapshot):**
```sql
SELECT
    s.DateKey,
    CAST(s.StoreKey AS SIGNED) AS StoreKey,
    COALESCE(ds.StoreName, CONCAT('Store ', s.StoreKey)) AS StoreName,
    SUM(s.total_sales_amount)
      - COALESCE(SUM(s.total_return_amount), 0)
      - COALESCE(SUM(s.total_discount_amount), 0) AS total_sales,
    SUM(s.total_sales_quantity * p.UnitCost) AS total_cost,
    [... profit, profit_margin ...]
FROM summary_daily_sales s
LEFT JOIN DimStore ds ON ds.StoreKey = s.StoreKey
LEFT JOIN DimProduct p ON p.ProductKey = s.ProductKey
GROUP BY s.DateKey, s.StoreKey, StoreName
ORDER BY s.DateKey
```

**Response JSON (ví dụ CEO/Executive, preset=all):**
```json
{
  "status": "success",
  "ytd": 152340567.89,
  "mtd": 18234567.12,
  "total": 980123456.78,
  "ytd_profit": 45670123.45,
  "mtd_profit": 5467890.12,
  "total_profit": 294036037.03,
  "avg_profit_margin": 0.30,
  "yoy_growth": 12.34,
  "mom_growth": -3.21,
  "trend": {
    "labels": ["2007-01", "2007-02", "...", "2009-12"],
    "data": [8500000, 9200000, "..."]
  },
  "profit_trend": {
    "labels": ["2007-01", "2007-02", "..."],
    "data": [2550000, 2760000, "..."]
  },
  "store_pie": {
    "labels": ["Contoso Catalog Store", "Contoso North America Online", "..."],
    "data": [150000000, 120000000, "..."]
  },
  "last_updated": "2009-12-28"
}
```

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR2.1 | RLS: Executive/Admin xem tất cả stores. Regional Manager xem stores trong `ContinentName = region`. Store Manager chỉ xem `StoreKey = store_key`. |
| BR2.2 | YoY Growth = `(YTD năm hiện tại - YTD năm trước) / YTD năm trước * 100%` |
| BR2.3 | MoM Growth = `(MTD tháng hiện tại - MTD tháng trước) / MTD tháng trước * 100%` |
| BR2.4 | Profit Margin = `total_profit / total_sales` (0 nếu total_sales = 0) |
| BR2.5 | Parquet Cache: Build 1 lần khi startup (background thread), serve từ cache cho tất cả requests |
| BR2.6 | Time Filter Presets: all (no filter), YTD (Jan 1 → today), 12M/6M/3M/1M (rolling windows) |
| BR2.7 | Store Pie: Chỉ hiện Top 10 stores theo tổng doanh thu |

---

## A.3 UC3.2 – Phân tích phân khúc khách hàng RFM

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC3.2 |
| **Tên Use Case** | Phân tích phân khúc khách hàng (RFM Segments) |
| **Actor chính** | Admin, Executive, Regional Manager |
| **Mô tả** | Phân loại khách hàng thành 7 segments dựa trên RFM (Recency, Frequency, Monetary). Hiển thị biểu đồ Doughnut + bảng chi tiết. |
| **Trigger** | Người dùng truy cập `/item-trends` |

### Điều kiện tiên quyết
1. Bảng `agg_customer_rfm` có dữ liệu (21,569 rows)
2. 7 RFM segments đã được tính toán bởi ETL Pipeline

### Luồng chính

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 1 | Truy cập `/item-trends` | |
| 2 | | Browser gọi `GET /data/api/rfm-segments` | 
| 3 | | **[Backend]** `analytics.py → get_rfm_segments()`: Query `SELECT rfm_segment, COUNT(*) as count, AVG(monetary) as avg_monetary, AVG(recency_days) as avg_recency FROM agg_customer_rfm GROUP BY rfm_segment ORDER BY count DESC` |
| 4 | | Return 7 segments: Champion, Loyal, Potential Loyalist, At Risk, Needs Attention, About to Sleep, Lost |
| 5 | | Frontend `RfmSegmentsChart` render: BarChart (count per segment) + DetailCards (avg_monetary, avg_recency) |
| 6 | Người dùng xem phân tích RFM | |

### Dữ liệu trao đổi

**Response JSON:**
```json
{
  "segments": [
    {"segment": "Champion", "count": 3452, "avg_monetary": 15234.56, "avg_recency": 12.3},
    {"segment": "Loyal", "count": 5123, "avg_monetary": 8567.89, "avg_recency": 34.5},
    {"segment": "At Risk", "count": 4567, "avg_monetary": 3456.78, "avg_recency": 178.9},
    "..."
  ]
}
```

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR3.1 | RFM Scoring: Recency (ngày kể từ lần mua cuối), Frequency (số lần mua), Monetary (tổng chi tiêu) |
| BR3.2 | 7 Segments: Champion (R↑F↑M↑), Loyal (F↑M↑), Potential Loyalist (R↑F↓M↓), At Risk (R↓F↑M↑), Needs Attention (R↓F↓M↑), About to Sleep (R↓F↓M↓), Lost (R↓↓F↓M↓) |
| BR3.3 | Dữ liệu pre-computed bởi ETL Pipeline, lưu trong `agg_customer_rfm` |
| BR3.4 | Cache TTL: 15 phút cho analytics endpoints |

---

## A.4 UC4.1 – Xem Dashboard Hiệu suất Nhân viên

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC4.1 |
| **Tên Use Case** | Xem Dashboard Hiệu suất Nhân viên |
| **Actor chính** | Admin, Executive, Regional Manager |
| **Actor phụ** | Store Manager (KHÔNG có quyền truy cập module này) |
| **Mô tả** | Hiển thị KPI hiệu suất quản lý cửa hàng: Net Sales, Profit Margin, Return Rate, Orders. So sánh với trung bình công ty. Kèm Top Performer, Trend, Leaderboard, Scatter. |
| **Trigger** | Người dùng truy cập `/employee-performance` |

### Điều kiện tiên quyết
1. Bảng `summary_daily_sales`, `DimStore`, `DimDate`, `DimEmployee`, `agg_store_monthly_costs` có dữ liệu
2. `DimStore.StoreManager` có giá trị (liên kết đến `DimEmployee.EmployeeKey`)
3. Người dùng có role `admin`, `executive`, hoặc `regional_manager`

### Luồng chính

| Bước | Actor | Hệ thống | Dữ liệu |
|------|-------|----------|---------|
| 1 | Truy cập `/employee-performance` | | |
| 2 | | **Phase 1**: Gọi `GET /employee-performance/filters` (Bearer token) | |
| 3 | | **[Backend]** `get_filters()`: Query 4 bảng: | |
| | | — `DimDate` → distinct `CalendarYear` DESC (VD: [2009, 2008, 2007]) | |
| | | — `DimDate` → distinct `MonthNumber` (1-12) | |
| | | — `DimStore` → distinct `StoreKey, StoreName` | |
| | | — `DimStore JOIN DimEmployee` → distinct `StoreManager, employee_name, title` | |
| | | RLS: Nếu Regional Manager → filter stores theo region | |
| 4 | | Frontend render `FiltersBar`: Year dropdown (default=2009), Month dropdown, Employee dropdown | |
| 5 | | **Phase 2 (Parallel — `Promise.allSettled`)**: | |
| | | (a) `GET /employee-performance/dashboard?year=2009` | |
| | | (b) `GET /employee-performance/trend?year=2009` | |
| | | (c) `GET /employee-performance/leaderboard?year=2009&top_n=10` | |
| | | (d) `GET /employee-performance/scatter?year=2009` | |
| 6 | | **[Backend — Dashboard endpoint]** `get_dashboard(year=2009)`: | |
| | | — `_resolve_year(year)` → return 2009 (hoặc query MAX year nếu None) | |
| | | — `_manager_filters_sql(2009, None, None, None)` → WHERE clause | |
| | | — `_manager_monthly_subquery(where)` → CTE JOIN: `summary_daily_sales ↔ DimStore ↔ DimDate ↔ agg_store_monthly_costs` | |
| | | — KPI SQL: `SUM(net_sales), AVG(profit_margin), AVG(return_rate), SUM(order_count)` | |
| | | — Top Performer SQL: `ORDER BY net_sales DESC LIMIT 1` → JOIN `DimEmployee` lấy tên | |
| | | — Company Avg SQL: Cùng query nhưng KHÔNG filter employee/store → tính trung bình toàn công ty | |
| | | — Delta comparison: `kpi.avg - company.avg` cho mỗi metric | |
| | | — 6 Capabilities: `[manager_productivity ✅, time_trend ✅, radar ❌, absenteeism ❌, enps ❌, nine_box ❌]` | |
| 7 | | **[Backend — Trend endpoint]** `get_trend(year=2009)`: | |
| | | — GROUP BY `year, month` → SUM(net_sales), AVG(profit_margin) | |
| | | — Return 12 monthly data points | |
| 8 | | **[Backend — Leaderboard]** `get_leaderboard(year=2009, top_n=10)`: | |
| | | — GROUP BY `employee_key` → ORDER BY net_sales DESC LIMIT 10 | |
| | | — JOIN `DimEmployee` → Rank, Name, Title, Net Sales, Margin, Return Rate | |
| 9 | | **[Backend — Scatter]** `get_scatter(year=2009)`: | |
| | | — Mỗi row = 1 manager: X=net_sales, Y=profit_margin, size=order_count | |
| 10 | | Frontend render 5 components: | |
| | | — `KpiCards`: 4 KPI + comparison badges (↑/↓ vs company avg) | |
| | | — `TopPerformerCard`: Ảnh + tên + chức danh + 3 metrics | |
| | | — `CapabilityPanel`: 6 items (enabled/disabled + reason) | |
| | | — `TrendChart`: Dual-axis LineChart (Net Sales left, Profit Margin right) | |
| | | — `LeaderboardTable`: Sortable table top 10 | |
| | | — `ScatterChart`: Scatter plot với tooltip | |
| 11 | Người dùng xem Dashboard Employee | | |

### Luồng thay thế

**AF1: Thay đổi Filter**

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 1a | Chọn Year=2008, Month=6 | `setSelectedYear("2008")`, `setSelectedMonth("6")` |
| 1b | | Re-fetch tất cả 4 endpoints với `?year=2008&month=6` |
| 1c | | Dashboard + Leaderboard + Scatter filter theo tháng 6. Trend vẫn hiển thị cả 12 tháng (month filter không ảnh hưởng trend). |

**AF2: Chọn Employee cụ thể**

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 1a | Chọn Employee = "John Smith" (key=123) | `setSelectedEmployeeKey("123")` |
| 1b | | Re-fetch với `&employee_key=123` → Dashboard chỉ show KPI của employee đó vs company avg |

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR4.1 | Net Sales = SUM(total_sales_amount) - total_return_amount |
| BR4.2 | Profit Margin = (total_sales_amount - total_cost) / total_sales_amount × 100% |
| BR4.3 | Return Rate = total_return_quantity / total_sales_quantity × 100% |
| BR4.4 | Comparison Delta = (Employee/Filtered AVG) - (Company AVG) → positive = better, negative = worse |
| BR4.5 | Cache TTL: 10 phút (in-memory dict cache) |
| BR4.6 | RLS: Regional Manager chỉ thấy stores trong region (filter `DimStore JOIN DimGeography`) |
| BR4.7 | Store Manager không thấy module này trên Sidebar |

---

## A.5 UC5.4 – Xem chi tiết dự báo sản phẩm (Deep Dive)

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC5.4 |
| **Tên Use Case** | Xem chi tiết dự báo nhu cầu sản phẩm (Deep Dive Forecast) |
| **Actor chính** | Admin, Executive |
| **Mô tả** | Hiển thị dự báo nhu cầu 14 ngày tiếp theo cho 1 sản phẩm cụ thể. Sử dụng mô hình LightGBM quantile regression (3 models) với recursive multi-step forecasting. Biểu đồ ComposedChart: actual line + predicted line + confidence interval (shaded area). |
| **Trigger** | Người dùng click "Deep Dive" từ Alerts table hoặc Bulk Query table |

### Điều kiện tiên quyết
1. Parquet cache (`daily_sales_snapshot.parquet`, `abc_xyz_snapshot.parquet`) đã build
2. Global Model (`global_demand_model.pkl`) đã load (hoặc chế độ On-Demand)
3. Sản phẩm có đủ dữ liệu lịch sử (tối thiểu 30 ngày)

### Luồng chính

| Bước | Actor | Hệ thống | Dữ liệu |
|------|-------|----------|---------|
| 1 | User click "Deep Dive" trên sản phẩm (VD: ProductKey=374, "Contoso SLR Camera X143 Grey") | | product_id=374, product_name="Contoso SLR Camera X143 Grey" |
| 2 | | Frontend gọi `loadDeepDive(374, "Contoso SLR Camera X143 Grey")` | |
| 3 | | `GET /forecast/forecast/374?days_ahead=14` (timeout 600s) | |
| 4 | | **[Backend]** `ensure_initialized()` → Load global model nếu chưa load | |
| 5 | | **[Backend]** `load_product_time_series_from_parquet(374)`: | |
| | | — Đọc `daily_sales_snapshot.parquet` | |
| | | — Filter `ProductKey == 374` | |
| | | — Return DataFrame: `[DateKey, ProductKey, ProductName, SalesQuantity, SalesAmount, UnitPrice, DiscountAmount]` | |
| 6 | | **[Backend]** `fill_missing_dates(product_ts)`: | |
| | | — Tạo date range liên tục từ min(DateKey) → max(DateKey) | |
| | | — Forward-fill gaps (ngày không có bán → SalesQuantity=0) | |
| 7 | | **[Backend]** `create_all_features(product_ts)`: | |
| | | — **Lag Features**: `SalesQuantity_lag_7`, `SalesQuantity_lag_14`, `SalesQuantity_lag_30` | |
| | | — **Rolling Features**: `SalesQuantity_rolling_mean_7`, `SalesQuantity_rolling_std_7` | |
| | | — **Calendar Features**: `day_of_week` (0-6), `month` (1-12), `quarter` (1-4), `day_of_month`, `week_of_year`, `is_weekend` (0/1) | |
| | | — **Exogenous**: `UnitPrice`, `DiscountAmount` lag/rolling | |
| 8 | | **[Backend]** `model.predict_future(features_df, n_steps=14)`: | |
| | | — **Recursive Multi-step Forecasting** (VÒNG LẶP): | |
| | | | |
| | | **FOR step = 1 TO 14:** | |
| | | (a) Lấy `future_data.tail(90)` (giữ 90 ngày gần nhất) | |
| | | (b) Lấy feature row cuối cùng: `last_row = future_data[feature_columns].iloc[-1:]` | |
| | | (c) **Model Base** (regression): `base_forecast = model_base.predict(last_row)[0]` → Point forecast | |
| | | (d) **Model Lower** (quantile α=0.05): `lower_bound = model_lower.predict(last_row)[0]` → 5th percentile | |
| | | (e) **Model Upper** (quantile α=0.95): `upper_bound = model_upper.predict(last_row)[0]` → 95th percentile | |
| | | (f) Tạo `new_record = {DateKey: last_date + 1day, SalesQuantity: base_forecast, ...}` | |
| | | (g) Append vào `raw_future_data` → gọi lại `create_all_features()` để re-calculate lags/rolling | |
| | | (h) Lưu `{date, predicted, lower_bound, upper_bound}` | |
| | | **END FOR** | |
| 9 | | **[Backend]** Kết hợp actual history (30 ngày cuối) + 14 ngày forecast | |
| 10 | | Return `ForecastResponse`: | |
| | | `{product_id: 374, product_name: "...", forecast_points: [{date, actual, predicted, upper_bound, lower_bound}, ...]}` | |
| 11 | | Frontend render `ComposedChart` (Recharts): | |
| | | — `<Line>` actual (màu xanh, solid line) | |
| | | — `<Line>` predicted (màu cam, dashed line) | |
| | | — `<Area>` confidence interval (lower → upper, shaded) | |
| 12 | Người dùng xem forecast chart | | |

### Luồng ngoại lệ

**EF1: Sản phẩm không đủ dữ liệu**

| Bước | Hệ thống |
|------|----------|
| 5a | `load_product_time_series_from_parquet(374)` → DataFrame rỗng hoặc < 30 rows |
| 5b | Model vẫn cố predict nhưng lag features sẽ toàn NaN → forecast kém chính xác |

**EF2: Parquet cache chưa build**

| Bước | Hệ thống |
|------|----------|
| 4a | `ensure_cache_ready()` → Parquet không tồn tại |
| 4b | Start background build → raise `HTTPException(503, "Parquet cache is initializing")` |
| 4c | Frontend nhận 503 → hiển thị "Đang khởi tạo, vui lòng thử lại" |

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR5.1 | LightGBM 3-model Quantile Regression: base (regression), lower (α=0.05), upper (α=0.95) |
| BR5.2 | Recursive multi-step: Mỗi step dùng forecast step trước làm input → calculate lại features |
| BR5.3 | Chỉ giữ 90 ngày gần nhất khi predict (tránh O(N²) với dataset lớn) |
| BR5.4 | Confidence bounds: `lower ≤ base ≤ upper` (enforce), `lower ≥ 0` (no negative sales) |
| BR5.5 | Feature columns: 13+ features (3 lags + 2 rolling + 6 calendar + 2+ exogenous) |
| BR5.6 | Global model trained trên top 500 SKUs (by revenue) |

---

## A.6 UC6.2 – Chạy ETL Pipeline

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC6.2 |
| **Tên Use Case** | Chạy ETL Pipeline (POS → DW Sync + Aggregate Rebuild) |
| **Actor chính** | Admin |
| **Mô tả** | Kích hoạt đồng bộ dữ liệu từ POS (`pos_system`) sang Data Warehouse (`retails_dataset`), sau đó rebuild tất cả bảng aggregate. |
| **Trigger** | Admin click "Chạy ETL" hoặc System Startup (tự động) |

### Điều kiện tiên quyết
1. Người dùng có role `admin`
2. Database `pos_system` và `retails_dataset` đang hoạt động
3. Bảng `pos_change_log` có dữ liệu (> 0 rows) — nếu không ETL sẽ skip

### Luồng chính

| Bước | Actor | Hệ thống | Dữ liệu |
|------|-------|----------|---------|
| 1 | Admin click "Chạy ETL" | | |
| 2 | | Frontend gọi `POST /data/etl/run` | |
| 3 | | Backend start background thread → trả ngay `{"status": "accepted"}` | |
| 4 | | **[Background — Phase 1: POS → DW Sync]** | |
| | | `pos_etl.sync_pos_to_dw()`: | |
| | | (a) Kiểm tra `pos_change_log` count → nếu 0 → skip | |
| | | (b) Query POS: `SELECT o.*, i.* FROM sales_orders o JOIN sales_order_items i WHERE status IN ('Completed', 'Returned')` | POS: 11,526 orders × 34,662 items |
| | | (c) **Transform** mỗi item: | |
| | | — Channel: `o.channel = "InStore"` → FactSales, `"Online"` → FactOnlineSales | |
| | | — Key Offset: `SalesKey = item_id + 10,000,000` (tránh trùng DW data) | |
| | | — CustomerKey: `customer_id + 100,000` | |
| | | — Tính: `sales_qty`, `return_qty` (status='Returned'), `discount_amt`, `total_cost` | |
| | | (d) **Load**: `REPLACE INTO FactSales (...) VALUES (...)` batch 2000 rows | |
| | | (e) **Load**: `REPLACE INTO FactOnlineSales (...)` batch 2000 rows | |
| | | (f) Ensure `DimDate` cho các ngày mới | |
| | | (g) Refresh `summary_daily_sales` cho POS date range | |
| 5 | | **[Background — Phase 2: Aggregate Rebuild]** | |
| | | `create_aggregate_tables(force=True)`: | |
| | | (a) `agg_inventory_metrics`: `FactInventory JOIN DimProduct → turnover, sell_through_rate, GMROI, days_of_supply` | 600,241 rows |
| | | (b) `agg_product_performance`: `summary_daily_sales → cumsum revenue → ABC classification (A≤80%, B≤95%, C)` | 2,232 rows |
| | | (c) `agg_customer_rfm`: `FactOnlineSales → Recency, Frequency, Monetary → 7 segments` | 21,569 rows |
| | | (d) `agg_kpi_summary`: `9 pre-computed KPIs (total_revenue, total_transactions, avg_basket_size, ...)` | 9 rows |
| | | (e) `agg_store_monthly_costs`: `summary_daily_sales GROUP BY StoreKey, Year, Month → cost/return/quantity` | 11,978 rows |
| | | (f) `agg_channel_summary`: `Offline vs Online → revenue, profit, transactions` | 2 rows |
| 6 | | **[Polling]** Frontend poll `GET /data/etl/status` mỗi 5 giây | |
| 7 | | ETL hoàn tất → Return `{"status": "completed", "duration": "45s", "tables_built": 6}` | |
| 8 | Admin thấy kết quả ETL | | |

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR6.1 | Incremental Check: Nếu `pos_change_log` count = 0 → skip ETL sync (tối ưu hiệu suất) |
| BR6.2 | Key Offset: POS item_id + 10,000,000 = DW SalesKey (tránh collision) |
| BR6.3 | Customer Offset: POS customer_id + 100,000 = DW CustomerKey |
| BR6.4 | REPLACE INTO: Upsert logic — nếu PK trùng thì UPDATE, không thì INSERT |
| BR6.5 | ABC Classification: A ≤ 80% cumulative revenue, B ≤ 95%, C còn lại |
| BR6.6 | RFM Segments: Champion, Loyal, Potential Loyalist, At Risk, Needs Attention, About to Sleep, Lost |

---

## A.7 UC6.4 – Upload CSV vào Data Warehouse

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC6.4 |
| **Tên** | Upload CSV vào Data Warehouse |
| **Actor chính** | Admin |
| **Mô tả** | Upload file CSV/Excel → preview → column mapping → transform & load vào MySQL DW table |

### Luồng chính

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 1 | Admin chọn file CSV/Excel | |
| 2 | | Frontend gửi `POST /data/csv-upload-preview` (FormData: file) |
| 3 | | **[Backend]** Đọc CSV bằng `pd.read_csv()` hoặc `pd.read_excel()` |
| 4 | | `_sanitize_df()`: Replace NaN with None |
| 5 | | Auto-detect target table (match column names với ALLOWED_TABLES) |
| 6 | | Return: `{preview_rows: [...10 rows], suggested_table, column_mapping}` |
| 7 | Admin xác nhận / chỉnh sửa mapping | |
| 8 | Admin click "Transform & Load" | |
| 9 | | Frontend gửi `POST /data/csv-transform-load` (FormData: file + mapping + target_table) |
| 10 | | **[Backend]** `_validate_table_name(table)`: Kiểm tra whitelist `ALLOWED_TABLES` (15 bảng) |
| 11 | | `_fetch_table_columns(table)`: Query `information_schema.columns` lấy schema |
| 12 | | Transform columns theo mapping |
| 13 | | `_bulk_upsert(table, rows, primary_keys)`: `INSERT INTO {table} (...) VALUES (...) ON DUPLICATE KEY UPDATE ...` |
| 14 | | Return `{status: "success", rows_inserted, rows_updated}` |

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR6.8 | ALLOWED_TABLES whitelist: FactSales, FactOnlineSales, FactInventory, DimProduct, DimStore, DimEmployee, DimChannel, DimPromotion, DimCurrency, DimCustomer, DimDate, DimGeography, DimProductCategory, DimProductSubcategory, summary_daily_sales |
| BR6.9 | SQL Injection Prevention: Table name phải nằm trong whitelist (không allow user input trực tiếp) |
| BR6.10 | Upsert: `ON DUPLICATE KEY UPDATE` cho trường hợp PK trùng |
| BR6.11 | Chỉ Admin có quyền (kiểm tra role) |

---

## A.8 UC7.1 – Nhận dữ liệu Realtime qua SSE

| Thuộc tính | Mô tả |
|---|---|
| **Use Case ID** | UC7.1 |
| **Tên** | Nhận dữ liệu Realtime qua Server-Sent Events |
| **Actor chính** | Admin, Executive |
| **Mô tả** | Frontend tự động mở kết nối SSE đến backend, nhận dữ liệu realtime mỗi 3 giây |

### Luồng chính

| Bước | Actor | Hệ thống |
|------|-------|----------|
| 1 | User đăng nhập thành công | |
| 2 | | `RefreshProvider` (React Context) mount → mở `EventSource("http://localhost:8000/realtime/stream")` |
| 3 | | **[Backend]** `StreamingResponse(sse_generator(), media_type="text/event-stream")` |
| 4 | | **SSE Generator (loop vô hạn, yield mỗi 3 giây):** |
| | | (a) `get_realtime_summary()` → query `realtime_daily_metrics WHERE metric_date = CURDATE() AND store_id = 0 AND channel = 'ALL'` |
| | | (b) Kiểm in-memory cache (TTL 10 giây) → cache HIT: return cached |
| | | (c) So sánh `last_updated` với lần push trước |
| | | (d) [Có thay đổi]: `yield f"data: {json.dumps(summary)}\n\n"` |
| | | (e) [Không thay đổi]: `yield ": keepalive\n\n"` |
| | | (f) `await asyncio.sleep(3)` |
| 5 | | Frontend `onmessage` handler: parse JSON → `setRealtimeSummary(data)` |
| 6 | | Dashboard hiển thị Realtime cards: today_revenue, today_cost, today_profit, today_orders + MTD |
| 7 | User xem dữ liệu cập nhật liên tục | |

### Dữ liệu SSE Event

```
data: {"today_revenue": 125678.90, "today_cost": 87654.32, "today_profit": 38024.58, "today_orders": 456, "today_items_sold": 1234, "today_discount": 5678.90, "mtd_revenue": 2345678.90, "mtd_profit": 890123.45, "mtd_orders": 12345, "last_updated": "2026-03-30T14:23:45", "metric_date": "2026-03-30"}
```

### Quy tắc nghiệp vụ

| # | Quy tắc |
|---|---------|
| BR7.1 | SSE push interval: 3 giây |
| BR7.2 | In-memory cache TTL: 10 giây |
| BR7.3 | Chỉ push khi `last_updated` thay đổi (tránh duplicate data) |
| BR7.4 | Keepalive comment (`": keepalive"`) để giữ kết nối |
| BR7.5 | Pre-aggregated table: `realtime_daily_metrics` (O(1) read vs JOIN real-time) |

---

# PHẦN B — SEQUENCE DIAGRAM CHI TIẾT

## B.1. SD-01: Đăng nhập hệ thống — Chi tiết từng bước

### Lifelines (Đối tượng tham gia)

| # | Lifeline | Component thực tế | Vị trí |
|---|----------|--------------------|--------|
| 1 | `:User` | Người dùng (Browser) | Actor |
| 2 | `:LoginPage` | `frontend/app/login/page.tsx` — React Component | Boundary |
| 3 | `:AuthStore` | `frontend/app/store/useAuth.ts` — Zustand Store | Control |
| 4 | `:FastAPI` | `backend/auth_api.py` — Router `/auth` | Control |
| 5 | `:AuthModule` | `backend/auth.py` — authenticate_user(), jwt_sign() | Control |
| 6 | `:MySQL` | Database `retails_dataset`, bảng `bi_users` | Entity |

### Sequence (Chi tiết)

```
:User          :LoginPage       :AuthStore       :FastAPI          :AuthModule       :MySQL
  │                │                │                │                  │                │
  │ 1. Navigate    │                │                │                  │                │
  │ /login         │                │                │                  │                │
  │───────────────>│                │                │                  │                │
  │                │                │                │                  │                │
  │                │ 2. useEffect() │                │                  │                │
  │                │ loadFromStorage()               │                  │                │
  │                │───────────────>│                │                  │                │
  │                │                │ 3. Check       │                  │                │
  │                │                │ localStorage   │                  │                │
  │                │                │ "bi_token"     │                  │                │
  │                │                │──┐             │                  │                │
  │                │                │  │ null        │                  │                │
  │                │                │<─┘             │                  │                │
  │                │ 4. return      │                │                  │                │
  │                │ token=null     │                │                  │                │
  │                │<───────────────│                │                  │                │
  │                │                │                │                  │                │
  │ 5. Render      │                │                │                  │                │
  │ Login Form     │                │                │                  │                │
  │ + 6 Demo Btns  │                │                │                  │                │
  │<───────────────│                │                │                  │                │
  │                │                │                │                  │                │
  │ 6. Type        │                │                │                  │                │
  │ username="ceo" │                │                │                  │                │
  │ password=      │                │                │                  │                │
  │ "demo123"      │                │                │                  │                │
  │───────────────>│                │                │                  │                │
  │                │ 7. onChange    │                │                  │                │
  │                │ setUsername()  │                │                  │                │
  │                │ setPassword() │                │                  │                │
  │                │──┐            │                │                  │                │
  │                │<─┘            │                │                  │                │
  │                │                │                │                  │                │
  │ 8. Click       │                │                │                  │                │
  │ "Đăng nhập"    │                │                │                  │                │
  │───────────────>│                │                │                  │                │
  │                │ 9. handleSubmit(e)              │                  │                │
  │                │ e.preventDefault()              │                  │                │
  │                │                │                │                  │                │
  │                │ 10. login(     │                │                  │                │
  │                │   "ceo",       │                │                  │                │
  │                │   "demo123"    │                │                  │                │
  │                │ )              │                │                  │                │
  │                │───────────────>│                │                  │                │
  │                │                │                │                  │                │
  │                │                │ 11. set({      │                  │                │
  │                │                │   loading:true,│                  │                │
  │                │                │   error:null   │                  │                │
  │                │                │ })             │                  │                │
  │                │                │──┐             │                  │                │
  │                │                │<─┘             │                  │                │
  │                │                │                │                  │                │
  │                │                │ 12. fetch(     │                  │                │
  │                │                │   "http://localhost:8000          │                │
  │                │                │    /auth/login",                  │                │
  │                │                │   {method:"POST",                │                │
  │                │                │    headers:{"Content-Type":      │                │
  │                │                │      "application/json"},        │                │
  │                │                │    body: JSON.stringify(         │                │
  │                │                │      {username:"ceo",            │                │
  │                │                │       password:"demo123"}        │                │
  │                │                │    )}                            │                │
  │                │                │ )             │                  │                │
  │                │                │──────────────>│                  │                │
  │                │                │               │                  │                │
  │                │                │               │ 13. login(body:  │                │
  │                │                │               │   LoginRequest)  │                │
  │                │                │               │                  │                │
  │                │                │               │ 14. authenticate_│                │
  │                │                │               │   user(engine,   │                │
  │                │                │               │   "ceo",         │                │
  │                │                │               │   "demo123")     │                │
  │                │                │               │─────────────────>│                │
  │                │                │               │                  │                │
  │                │                │               │                  │ 15. SELECT *   │
  │                │                │               │                  │ FROM bi_users  │
  │                │                │               │                  │ WHERE username │
  │                │                │               │                  │   = 'ceo'      │
  │                │                │               │                  │ AND is_active=1│
  │                │                │               │                  │───────────────>│
  │                │                │               │                  │                │
  │                │                │               │                  │ 16. Row:       │
  │                │                │               │                  │ {id:2,         │
  │                │                │               │                  │  username:     │
  │                │                │               │                  │  "ceo",        │
  │                │                │               │                  │  password_hash:│
  │                │                │               │                  │  "a1b2c3$...", │
  │                │                │               │                  │  role:         │
  │                │                │               │                  │  "executive",  │
  │                │                │               │                  │  region:null,  │
  │                │                │               │                  │  store_key:    │
  │                │                │               │                  │  null,         │
  │                │                │               │                  │  display_name: │
  │                │                │               │                  │  "CEO / Ban    │
  │                │                │               │                  │   Giám đốc"}   │
  │                │                │               │                  │<───────────────│
  │                │                │               │                  │                │
  │                │                │               │                  │ 17. verify_    │
  │                │                │               │                  │ password(      │
  │                │                │               │                  │  "demo123",    │
  │                │                │               │                  │  "a1b2c3$hash")│
  │                │                │               │                  │                │
  │                │                │               │                  │ salt = "a1b2c3"│
  │                │                │               │                  │ computed =     │
  │                │                │               │                  │  sha256(       │
  │                │                │               │                  │  "a1b2c3:      │
  │                │                │               │                  │   demo123")    │
  │                │                │               │                  │ hmac.compare_  │
  │                │                │               │                  │  digest(       │
  │                │                │               │                  │  computed,hash)│
  │                │                │               │                  │  = True        │
  │                │                │               │                  │──┐             │
  │                │                │               │                  │<─┘             │
  │                │                │               │                  │                │
  │                │                │               │                  │ 18. return     │
  │                │                │               │                  │ user_dict      │
  │                │                │               │                  │ (sans password)│
  │                │                │               │<─────────────────│                │
  │                │                │               │                  │                │
  │                │                │               │ 19. create_access│                │
  │                │                │               │   _token(user)   │                │
  │                │                │               │                  │                │
  │                │                │               │ payload = {      │                │
  │                │                │               │  sub:"ceo",      │                │
  │                │                │               │  uid:2,          │                │
  │                │                │               │  role:"executive"│                │
  │                │                │               │  region:null,    │                │
  │                │                │               │  store_key:null, │                │
  │                │                │               │  display_name:   │                │
  │                │                │               │  "CEO/Ban GĐ",   │                │
  │                │                │               │  iat:1711756800, │                │
  │                │                │               │  exp:1711843200  │                │
  │                │                │               │ }                │                │
  │                │                │               │                  │                │
  │                │                │               │ jwt_sign(payload,│                │
  │                │                │               │  JWT_SECRET)     │                │
  │                │                │               │  → HS256 HMAC   │                │
  │                │                │               │──┐               │                │
  │                │                │               │<─┘               │                │
  │                │                │               │                  │                │
  │                │                │ 20. HTTP 200   │                  │                │
  │                │                │ {access_token: │                  │                │
  │                │                │  "eyJ...",     │                  │                │
  │                │                │  token_type:   │                  │                │
  │                │                │  "bearer",     │                  │                │
  │                │                │  user: {...}}  │                  │                │
  │                │                │<──────────────│                  │                │
  │                │                │               │                  │                │
  │                │                │ 21. localStorage                 │                │
  │                │                │   .setItem(    │                  │                │
  │                │                │   "bi_token",  │                  │                │
  │                │                │   "eyJ...")    │                  │                │
  │                │                │                │                  │                │
  │                │                │ 22. localStorage                 │                │
  │                │                │   .setItem(    │                  │                │
  │                │                │   "bi_user",   │                  │                │
  │                │                │   JSON.stringify                 │                │
  │                │                │   ({id:2,...}))│                  │                │
  │                │                │                │                  │                │
  │                │                │ 23. set({      │                  │                │
  │                │                │   token:"eyJ.",│                  │                │
  │                │                │   user:{...},  │                  │                │
  │                │                │   loading:false│                  │                │
  │                │                │ })             │                  │                │
  │                │                │──┐             │                  │                │
  │                │                │<─┘             │                  │                │
  │                │                │                │                  │                │
  │                │ 24. return true│                │                  │                │
  │                │<───────────────│                │                  │                │
  │                │                │                │                  │                │
  │                │ 25. router.    │                │                  │                │
  │                │ replace(       │                │                  │                │
  │                │ "/dashboard")  │                │                  │                │
  │                │──┐             │                │                  │                │
  │                │<─┘             │                │                  │                │
  │                │                │                │                  │                │
  │ 26. Navigate   │                │                │                  │                │
  │ to /dashboard  │                │                │                  │                │
  │<───────────────│                │                │                  │                │
```

---

## B.2. SD-02: Dashboard Sales — Chi tiết RLS

### Lifelines

| # | Lifeline | Component thực tế |
|---|----------|-------------------|
| 1 | `:User` | Browser |
| 2 | `:DashboardPage` | `frontend/app/dashboard/page.tsx` |
| 3 | `:AuthHeaders` | `frontend/app/lib/api.ts` — `authHeaders()` |
| 4 | `:FastAPI` | `backend/sale_profit/api.py` |
| 5 | `:AuthDep` | `backend/auth.py` — `get_current_user()` + `get_rls_store_keys()` |
| 6 | `:SaleService` | `backend/sale_profit/service.py` |
| 7 | `:ParquetCache` | `backend/sale_profit/cache/sales_profit_daily_snapshot.parquet` |
| 8 | `:MySQL` | `retails_dataset` — `summary_daily_sales`, `DimStore`, `DimProduct` |

### Sequence — RLS Flow cho Regional Manager (rm_asia)

```
:User    :DashboardPage   :AuthHeaders   :FastAPI         :AuthDep            :SaleService   :ParquetCache   :MySQL
  │           │                │             │                │                    │               │             │
  │ Navigate  │                │             │                │                    │               │             │
  │ /dashboard│                │             │                │                    │               │             │
  │──────────>│                │             │                │                    │               │             │
  │           │ fetchJsonWithTimeout(        │                │                    │               │             │
  │           │  "/sale-profit/api/          │                │                    │               │             │
  │           │   dashboard/sales")          │                │                    │               │             │
  │           │                │             │                │                    │               │             │
  │           │ authHeaders()  │             │                │                    │               │             │
  │           │───────────────>│             │                │                    │               │             │
  │           │                │ token =     │                │                    │               │             │
  │           │                │ localStorage│                │                    │               │             │
  │           │                │ .getItem(   │                │                    │               │             │
  │           │                │ "bi_token") │                │                    │               │             │
  │           │ {Authorization:│             │                │                    │               │             │
  │           │  "Bearer eyJ.."}             │                │                    │               │             │
  │           │<───────────────│             │                │                    │               │             │
  │           │                │             │                │                    │               │             │
  │           │ GET /sale-profit/api/dashboard/sales          │                    │               │             │
  │           │ Authorization: Bearer eyJ..  │                │                    │               │             │
  │           │─────────────────────────────>│                │                    │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │ get_current_user(request)           │               │             │
  │           │                │             │───────────────>│                    │               │             │
  │           │                │             │                │ auth_header =      │               │             │
  │           │                │             │                │ "Bearer eyJ..."    │               │             │
  │           │                │             │                │ token = "eyJ..."   │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │ jwt_decode(token,  │               │             │
  │           │                │             │                │  JWT_SECRET)       │               │             │
  │           │                │             │                │ payload = {        │               │             │
  │           │                │             │                │  sub:"rm_asia",    │               │             │
  │           │                │             │                │  role:"regional_   │               │             │
  │           │                │             │                │   manager",        │               │             │
  │           │                │             │                │  region:"Asia"     │               │             │
  │           │                │             │                │ }                  │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │ UserContext(    │                    │               │             │
  │           │                │             │  username=     │                    │               │             │
  │           │                │             │  "rm_asia",    │                    │               │             │
  │           │                │             │  role=         │                    │               │             │
  │           │                │             │  "regional_    │                    │               │             │
  │           │                │             │   manager",    │                    │               │             │
  │           │                │             │  region="Asia")│                    │               │             │
  │           │                │             │<───────────────│                    │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │ get_rls_store_keys(engine, user)    │               │             │
  │           │                │             │───────────────>│                    │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │ role="regional_    │               │             │
  │           │                │             │                │  manager",         │               │             │
  │           │                │             │                │ region="Asia"      │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │ SELECT ds.StoreKey │               │             │
  │           │                │             │                │ FROM DimStore ds   │               │             │
  │           │                │             │                │ JOIN DimGeography  │               │             │
  │           │                │             │                │  dg ON ds.Geo..Key │               │             │
  │           │                │             │                │  = dg.Geo..Key     │               │             │
  │           │                │             │                │ WHERE dg.Continent │               │             │
  │           │                │             │                │  Name = 'Asia'     │               │             │
  │           │                │             │                │─────────────────────────────────────────────────>│
  │           │                │             │                │                    │               │             │
  │           │                │             │                │ [23, 45, 67, 89,   │               │             │
  │           │                │             │                │  112, 134, ...]    │               │             │
  │           │                │             │                │ (≈50 Asian stores) │               │             │
  │           │                │             │                │<─────────────────────────────────────────────────│
  │           │                │             │                │                    │               │             │
  │           │                │             │ rls_keys =     │                    │               │             │
  │           │                │             │ [23,45,67,89..]│                    │               │             │
  │           │                │             │<───────────────│                    │               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │ get_sales_profit_dashboard(         │               │             │
  │           │                │             │  start=None,   │                    │               │             │
  │           │                │             │  end=None,     │                    │               │             │
  │           │                │             │  store_key=None,                    │               │             │
  │           │                │             │  rls_store_keys=[23,45,...])        │               │             │
  │           │                │             │───────────────────────────────────>│               │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │                    │ load_sales_   │             │
  │           │                │             │                │                    │ profit_       │             │
  │           │                │             │                │                    │ snapshot()    │             │
  │           │                │             │                │                    │──────────────>│             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │                    │ Cache HIT:    │             │
  │           │                │             │                │                    │ pd.read_      │             │
  │           │                │             │                │                    │ parquet()     │             │
  │           │                │             │                │                    │ → DataFrame   │             │
  │           │                │             │                │                    │ (300K+ rows)  │             │
  │           │                │             │                │                    │<──────────────│             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │                    │ *** RLS ***   │             │
  │           │                │             │                │                    │ df = df[df[   │             │
  │           │                │             │                │                    │  "StoreKey"]  │             │
  │           │                │             │                │                    │  .isin(       │             │
  │           │                │             │                │                    │  [23,45,..])] │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │                    │ → Filtered    │             │
  │           │                │             │                │                    │ DataFrame     │             │
  │           │                │             │                │                    │ (≈50K rows    │             │
  │           │                │             │                │                    │  Asia only)   │             │
  │           │                │             │                │                    │──┐            │             │
  │           │                │             │                │                    │<─┘            │             │
  │           │                │             │                │                    │               │             │
  │           │                │             │                │                    │ Calculate:    │             │
  │           │                │             │                │                    │ ytd, mtd,     │             │
  │           │                │             │                │                    │ total, profit,│             │
  │           │                │             │                │                    │ yoy, mom,     │             │
  │           │                │             │                │                    │ trend,        │             │
  │           │                │             │                │                    │ store_pie     │             │
  │           │                │             │                │                    │ (Asia stores  │             │
  │           │                │             │                │                    │  only)        │             │
  │           │                │             │                │                    │──┐            │             │
  │           │                │             │                │                    │<─┘            │             │
  │           │                │             │                │                    │               │             │
  │           │ 200 OK: SalesDashboardResponse (Asia data only)                   │               │             │
  │           │<──────────────────────────────────────────────────────────────────│               │             │
  │           │                │             │                │                    │               │             │
  │ Render:   │                │             │                │                    │               │             │
  │ KPI Cards │                │             │                │                    │               │             │
  │ (Asia     │                │             │                │                    │               │             │
  │  stores   │                │             │                │                    │               │             │
  │  only)    │                │             │                │                    │               │             │
  │<──────────│                │             │                │                    │               │             │
```

---

## B.3. SD-05: ETL Pipeline — Chi tiết Transform

### Sequence — Key Transform Logic

```
:Admin   :Browser   :FastAPI         :ETL_Service        :POS_DB              :DW_DB
  │         │          │                │                    │                    │
  │ Click   │          │                │                    │                    │
  │ "ETL"   │          │                │                    │                    │
  │────────>│          │                │                    │                    │
  │         │ POST     │                │                    │                    │
  │         │ /data/   │                │                    │                    │
  │         │ etl/run  │                │                    │                    │
  │         │─────────>│                │                    │                    │
  │         │          │ Background     │                    │                    │
  │         │          │ Thread start   │                    │                    │
  │         │ 202      │                │                    │                    │
  │         │ Accepted │                │                    │                    │
  │         │<─────────│                │                    │                    │
  │         │          │                │                    │                    │
  │         │          │ sync_pos_     │                    │                    │
  │         │          │  to_dw()       │                    │                    │
  │         │          │───────────────>│                    │                    │
  │         │          │                │                    │                    │
  │         │          │                │ SELECT COUNT(*)    │                    │
  │         │          │                │ FROM pos_change_log│                    │
  │         │          │                │───────────────────>│                    │
  │         │          │                │                    │                    │
  │         │          │                │ count = 11,670     │                    │
  │         │          │                │<───────────────────│                    │
  │         │          │                │                    │                    │
  │         │          │                │ count > 0 → proceed                    │
  │         │          │                │                    │                    │
  │         │          │                │ SELECT o.order_id, │                    │
  │         │          │                │  o.channel,        │                    │
  │         │          │                │  i.item_id,        │                    │
  │         │          │                │  i.product_id,     │                    │
  │         │          │                │  i.quantity, ...   │                    │
  │         │          │                │ FROM sales_orders o│                    │
  │         │          │                │ JOIN sales_order_  │                    │
  │         │          │                │  items i ON ...    │                    │
  │         │          │                │ WHERE o.status IN  │                    │
  │         │          │                │ ('Completed',      │                    │
  │         │          │                │  'Returned')       │                    │
  │         │          │                │───────────────────>│                    │
  │         │          │                │                    │                    │
  │         │          │                │ ≈ 34,662 rows      │                    │
  │         │          │                │<───────────────────│                    │
  │         │          │                │                    │                    │
  │         │          │                │ *** TRANSFORM ***  │                    │
  │         │          │                │                    │                    │
  │         │          │                │ FOR each order_item:                   │
  │         │          │                │                    │                    │
  │         │          │                │ IF channel="InStore":                  │
  │         │          │                │   SalesKey =       │                    │
  │         │          │                │    item_id +       │                    │
  │         │          │                │    10,000,000      │                    │
  │         │          │                │   → FactSales row  │                    │
  │         │          │                │                    │                    │
  │         │          │                │ IF channel="Online":                   │
  │         │          │                │   OnlineSalesKey = │                    │
  │         │          │                │    item_id +       │                    │
  │         │          │                │    10,000,000      │                    │
  │         │          │                │   CustomerKey =    │                    │
  │         │          │                │    customer_id +   │                    │
  │         │          │                │    100,000         │                    │
  │         │          │                │   → FactOnlineSales│                    │
  │         │          │                │    row             │                    │
  │         │          │                │                    │                    │
  │         │          │                │ IF status=         │                    │
  │         │          │                │  "Returned":       │                    │
  │         │          │                │   return_qty =     │                    │
  │         │          │                │    quantity         │                    │
  │         │          │                │   sales_qty = 0    │                    │
  │         │          │                │ ELSE:              │                    │
  │         │          │                │   sales_qty =      │                    │
  │         │          │                │    quantity         │                    │
  │         │          │                │   return_qty = 0   │                    │
  │         │          │                │                    │                    │
  │         │          │                │ *** LOAD ***       │                    │
  │         │          │                │ REPLACE INTO       │                    │
  │         │          │                │  FactSales (...)   │                    │
  │         │          │                │  VALUES (...)      │                    │
  │         │          │                │  [batch 2000]      │                    │
  │         │          │                │────────────────────────────────────────>│
  │         │          │                │                    │                    │
  │         │          │                │ REPLACE INTO       │                    │
  │         │          │                │  FactOnlineSales   │                    │
  │         │          │                │  [batch 2000]      │                    │
  │         │          │                │────────────────────────────────────────>│
  │         │          │                │                    │                    │
  │         │          │                │ *** AGGREGATES *** │                    │
  │         │          │                │ CREATE TABLE       │                    │
  │         │          │                │  agg_product_      │                    │
  │         │          │                │  performance AS    │                    │
  │         │          │                │  SELECT ...        │                    │
  │         │          │                │  cumsum → ABC      │                    │
  │         │          │                │────────────────────────────────────────>│
  │         │          │                │                    │                    │
  │         │          │                │ [... 5 more aggregate tables ...]      │
  │         │          │                │                    │                    │
  │         │          │ ETL Done       │                    │                    │
  │         │          │<───────────────│                    │                    │
  │         │          │                │                    │                    │
  │         │ Poll:    │                │                    │                    │
  │         │ GET /data│                │                    │                    │
  │         │ /etl/    │                │                    │                    │
  │         │ status   │                │                    │                    │
  │         │─────────>│                │                    │                    │
  │         │          │                │                    │                    │
  │         │ {status: │                │                    │                    │
  │         │ "completed",              │                    │                    │
  │         │ duration:│                │                    │                    │
  │         │ "45s",   │                │                    │                    │
  │         │ tables:6}│                │                    │                    │
  │         │<─────────│                │                    │                    │
  │         │          │                │                    │                    │
  │ ETL     │          │                │                    │                    │
  │ Result  │          │                │                    │                    │
  │<────────│          │                │                    │                    │
```

---

# PHẦN C — DFD MỨC 1 CHI TIẾT

## C.1. Chi tiết luồng dữ liệu cấp trường (Field-Level Data Flows)

### P1 — Xác thực & Phân quyền: Chi tiết trường

```
┌──────────────┐                         ┌──────────────┐
│ E1..E4       │   DF1.1: Credentials    │     P1       │
│ Người dùng   │ ───────────────────────>│  Xác thực    │
│              │   {username: VARCHAR,    │  & Phân      │
│              │    password: VARCHAR}    │  quyền       │
│              │                          │              │
│              │   DF1.2: Auth Result     │              │
│              │ <───────────────────────│              │
│              │   {access_token: JWT,    │              │
│              │    token_type: "bearer", │              │
│              │    user: {               │              │
│              │      id: INT,            │              │
│              │      username: VARCHAR,  │              │
│              │      role: ENUM(         │              │
│              │        executive,        │              │
│              │        regional_manager, │              │
│              │        store_manager,    │              │
│              │        admin),           │              │
│              │      region: VARCHAR|null│              │
│              │      store_key: INT|null,│              │
│              │      display_name: VARCHAR              │
│              │    }}                    │              │
└──────────────┘                          └──────┬───────┘
                                                 │
                                    DF1.3: User Query
                                    {username: VARCHAR}
                                                 │
                                                 ▼
                                          ══ D1 ══════════
                                          bi_users
                                          ────────────────
                                          id: INT PK AUTO
                                          username: VARCHAR(100) UNIQUE
                                          password_hash: VARCHAR(200)
                                          role: VARCHAR(50) DEFAULT 'store_manager'
                                          region: VARCHAR(100) NULL
                                          store_key: INT NULL
                                          employee_key: BIGINT NULL
                                          display_name: VARCHAR(200)
                                          is_active: TINYINT(1) DEFAULT 1
                                          created_at: TIMESTAMP
                                          updated_at: TIMESTAMP
                                          ══════════════════

                    DF1.4: UserContext (internal, to P2..P8)
                    {username, uid, role, region, store_key, display_name, is_anonymous}

                    DF1.5: RLS Store Keys (internal, to P2..P4)
                    {store_keys: List[INT] | None}
                    Calculated by:
                      IF role IN (executive, admin) → None (all stores)
                      IF role = store_manager → [store_key]
                      IF role = regional_manager → SELECT StoreKey FROM DimStore JOIN DimGeography WHERE ContinentName = region
```

### P2 — Phân tích Bán hàng & Lợi nhuận: Chi tiết trường

```
DF2.1: Input từ Users
{
  start_date: DATE|null,        ← preset hoặc custom
  end_date: DATE|null,
  store_key: INT|null           ← optional override
}

DF2.2: Input từ D4 (summary_daily_sales)
{
  DateKey: DATE,
  StoreKey: INT,
  ProductKey: INT,
  total_sales_amount: DECIMAL(18,4),
  total_return_amount: DECIMAL(18,4),
  total_discount_amount: DECIMAL(18,4),
  total_sales_quantity: INT,
  total_return_quantity: INT
}

DF2.3: Input từ D6 (DimStore)
{
  StoreKey: INT PK,
  StoreName: VARCHAR(100),
  StoreType: VARCHAR(50),
  SellingAreaSize: INT,           ← Dùng cho Sales per Sqft
  GeographyKey: INT               ← FK → DimGeography
}

DF2.4: Input từ D5 (DimProduct)
{
  ProductKey: INT PK,
  ProductName: VARCHAR(200),
  UnitCost: DECIMAL(18,4),        ← Dùng cho cost calculation
  UnitPrice: DECIMAL(18,4)
}

DF2.5: Input từ D12 (FactSalesQuota)
{
  StoreKey: INT,
  CalendarYear: INT,
  SalesAmountQuota: DECIMAL(18,4) ← Budget target
}

DF2.6: Output tới Users — SalesDashboardResponse
{
  status: "success"|"empty",
  ytd: FLOAT,                     ← Year-to-date total sales (net)
  mtd: FLOAT,                     ← Month-to-date total sales (net)
  total: FLOAT,                   ← All-time total sales (net)
  ytd_profit: FLOAT,              ← Year-to-date gross profit
  mtd_profit: FLOAT,
  total_profit: FLOAT,
  avg_profit_margin: FLOAT,       ← total_profit / total_sales
  yoy_growth: FLOAT,              ← (YTD_this_year - YTD_prev_year) / YTD_prev_year × 100
  mom_growth: FLOAT,              ← (MTD_this_month - MTD_prev_month) / MTD_prev_month × 100
  trend: {
    labels: [STRING],             ← Monthly labels: "2009-01", "2009-02", ...
    data: [FLOAT]                 ← Monthly total_sales
  },
  profit_trend: {
    labels: [STRING],
    data: [FLOAT]                 ← Monthly gross_profit
  },
  store_pie: {
    labels: [STRING],             ← Top 10 store names
    data: [FLOAT]                 ← Tổng sales mỗi store
  },
  last_updated: DATE_STRING       ← Max date in data
}

DF2.7: Output — ChannelResponse
{
  channels: [{
    channel: "Offline"|"Online",
    revenue: FLOAT,
    profit: FLOAT,
    transactions: INT,
    share_pct: FLOAT              ← revenue / total_revenue × 100
  }],
  total_revenue: FLOAT
}

DF2.8: Output — KpiSummaryResponse
{
  kpis: {
    total_revenue: FLOAT,
    total_transactions: INT,
    avg_transaction_value: FLOAT,
    avg_basket_size: FLOAT,
    gross_margin_pct: FLOAT,
    active_customers: INT,
    active_products: INT,
    active_stores: INT,
    total_profit: FLOAT
  }
}

DF2.9: Parquet Cache ↔ D17
{
  DateKey, StoreKey, StoreName, total_sales, total_cost, gross_profit, profit_margin, Date
}
→ Saved as: backend/sale_profit/cache/sales_profit_daily_snapshot.parquet
→ ≈300K+ rows
```

### P5 — Dự báo Nhu cầu AI: Chi tiết Feature Engineering

```
DF5.1: Input features (13+ columns)
{
  ─── LAG FEATURES ───
  SalesQuantity_lag_7: FLOAT,     ← Sales 7 ngày trước
  SalesQuantity_lag_14: FLOAT,    ← Sales 14 ngày trước
  SalesQuantity_lag_30: FLOAT,    ← Sales 30 ngày trước

  ─── ROLLING FEATURES ───
  SalesQuantity_rolling_mean_7: FLOAT,  ← Trung bình 7 ngày gần nhất
  SalesQuantity_rolling_std_7: FLOAT,   ← Độ lệch chuẩn 7 ngày gần nhất

  ─── CALENDAR FEATURES ───
  day_of_week: INT (0-6),        ← 0=Monday, 6=Sunday
  month: INT (1-12),
  quarter: INT (1-4),
  day_of_month: INT (1-31),
  week_of_year: INT (1-52),
  is_weekend: INT (0|1),         ← Saturday/Sunday = 1

  ─── EXOGENOUS ───
  UnitPrice: FLOAT,
  DiscountAmount: FLOAT
}

DF5.2: Model Output (3 models × 14 steps)
{
  model_base (regression) → predicted: FLOAT,       ← Point forecast
  model_lower (α=0.05)   → lower_bound: FLOAT,     ← 5th percentile CI
  model_upper (α=0.95)   → upper_bound: FLOAT      ← 95th percentile CI
}

DF5.3: ABC/XYZ Classification
{
  ABC Class:
    A: ≤ 80% cumulative revenue            ← High value products
    B: > 80% AND ≤ 95% cumulative revenue  ← Medium value
    C: > 95% cumulative revenue             ← Low value

  XYZ Class:
    X: CV < 0.5     ← Stable demand (low variability)
    Y: 0.5 ≤ CV < 1 ← Variable demand
    Z: CV ≥ 1       ← Highly variable demand

  CV = Coefficient of Variation = std(SalesQuantity) / mean(SalesQuantity)
}
```

### P7 — ETL Pipeline: Chi tiết Transform Rules

```
DF7.1: POS Transaction → DW Fact Table Transform Rules

┌──────────────────────────────┬──────────────────────────────────┐
│ POS Field                    │ DW Field + Transform             │
├──────────────────────────────┼──────────────────────────────────┤
│ i.item_id                    │ SalesKey = item_id + 10,000,000  │
│ o.order_date                 │ DateKey = DATE(order_date)       │
│ o.channel                    │ IF "InStore" → FactSales         │
│                              │ IF "Online" → FactOnlineSales    │
│ o.store_id                   │ StoreKey = store_id (1:1)        │
│ o.employee_id                │ EmployeeKey = employee_id (1:1)  │
│ o.customer_id                │ CustomerKey = customer_id+100,000│
│ i.product_id                 │ ProductKey = product_id (1:1)    │
│ i.quantity (Completed)       │ SalesQuantity = quantity          │
│ i.quantity (Returned)        │ ReturnQuantity = quantity         │
│ i.unit_price                 │ UnitPrice = unit_price            │
│ i.unit_cost                  │ UnitCost = unit_cost              │
│ i.line_total                 │ SalesAmount = line_total          │
│ i.discount_pct × line_total  │ DiscountAmount                   │
│ i.quantity × i.unit_cost     │ TotalCost                        │
│ 1 (DimPromotion default)     │ PromotionKey = 1 (No Promotion)  │
│ 11 (DimCurrency default)     │ CurrencyKey = 11 (USD)           │
└──────────────────────────────┴──────────────────────────────────┘

DF7.2: Aggregate Table Build Rules

agg_product_performance:
  SOURCE: summary_daily_sales GROUP BY ProductKey
  COMPUTE: total_revenue, total_quantity, total_orders
  RANK: ROW_NUMBER() OVER (ORDER BY total_revenue DESC)
  ABC: CASE WHEN cumulative_pct <= 0.80 THEN 'A'
            WHEN cumulative_pct <= 0.95 THEN 'B'
            ELSE 'C' END

agg_customer_rfm:
  SOURCE: FactOnlineSales GROUP BY CustomerKey
  COMPUTE:
    Recency = DATEDIFF(MAX_DATE, MAX(DateKey))
    Frequency = COUNT(DISTINCT SalesOrderNumber)
    Monetary = SUM(SalesAmount)
  SEGMENT: CASE logic based on R/F/M percentile scores

agg_inventory_metrics:
  SOURCE: FactInventory JOIN DimProduct GROUP BY ProductKey, StoreKey
  COMPUTE:
    inventory_turnover = COGS / AVG(OnHandQuantity × UnitCost)
    sell_through_rate = SalesQuantity / (SalesQuantity + OnHandQuantity) × 100
    GMROI = GrossProfit / AVG(OnHandQuantity × UnitCost)
    days_of_supply = OnHandQuantity / (SalesQuantity / days_in_period)
```

---

## C.2. DFD Mức 1 — Sơ đồ tổng hợp (bản vẽ cuối cùng)

### Hướng dẫn vẽ trên draw.io / Lucidchart / Visual Paradigm

**Bước 1: Vẽ 5 External Entities (hình chữ nhật)**
- **E1**: Admin — vị trí: trái trên
- **E2**: Executive — vị trí: trái giữa
- **E3**: Regional Manager — vị trí: trái dưới
- **E4**: Store Manager — vị trí: trái dưới cùng
- **E5**: Hệ thống POS — vị trí: phải dưới

**Bước 2: Vẽ 8 Processes (hình tròn, đánh số)**
- **P1** (Xác thực): trung tâm trên
- **P2** (Sales & Profit): hàng 2, trái
- **P3** (Item Trends): hàng 2, giữa
- **P4** (Employee Perf.): hàng 2, phải
- **P5** (AI Forecast): hàng 3, trái
- **P6** (Data Mgmt): hàng 3, giữa
- **P7** (ETL): hàng 3, phải
- **P8** (Realtime): hàng 4, phải

**Bước 3: Vẽ Data Stores (2 đường ngang) — nhóm theo vùng**

Nhóm DW Core (giữa):
- D1 bi_users
- D2 FactSales + FactOnlineSales
- D4 summary_daily_sales
- D7 DimDate

Nhóm Dimension (phải trên):
- D5 DimProduct + Category
- D6 DimStore + Geography
- D8 DimCustomer
- D9 DimEmployee
- D10 DimPromotion

Nhóm Aggregate (phải giữa):
- D13 agg_kpi_summary + agg_channel_summary
- D14 agg_product_performance + agg_inventory_metrics
- D15 agg_customer_rfm + customer_segments
- D16 agg_store_monthly_costs

Nhóm Cache/Model (dưới):
- D17 Parquet Cache files
- D18 AI Model .pkl

Nhóm POS (phải dưới):
- D19 sales_orders + sales_order_items
- D20 realtime_daily_metrics + current_inventory
- D21 products + stores + employees + promotions

**Bước 4: Vẽ Data Flows (mũi tên có nhãn)**

| Từ | Đến | Nhãn luồng dữ liệu |
|----|-----|---------------------|
| E1..E4 | P1 | Username + Password |
| P1 | E1..E4 | JWT Token + User Info |
| P1 | D1 | Query user by username |
| D1 | P1 | User record (role, region, store_key) |
| P1 | P2..P8 | UserContext + RLS Store Keys |
| E1..E4 | P2 | Date filters (start, end, preset) |
| D4 | P2 | Daily sales aggregates |
| D5 | P2 | Product info (UnitCost) |
| D6 | P2 | Store info (StoreName, SellingAreaSize) |
| D12 | P2 | Sales quota (Budget) |
| D13 | P2 | Pre-computed KPIs + Channel data |
| D17 | P2 | Parquet snapshot (read) |
| P2 | D17 | Parquet snapshot (write/update) |
| P2 | E1..E4 | Dashboard data (KPIs, trends, charts) |
| E1..E3 | P3 | Year filter, date range |
| D4 | P3 | Sales data (revenue, quantity) |
| D5 | P3 | Product + Category hierarchy |
| D8 | P3 | Customer data |
| D10 | P3 | Promotion data |
| D6 | P3 | Geography data |
| D14 | P3 | ABC classification + Inventory metrics |
| D15 | P3 | RFM segments + Customer segments |
| P3 | E1..E3 | Analytics charts + segment data |
| E1..E3 | P4 | Year, month, employee_key filters |
| D4 | P4 | Daily sales by store |
| D6 | P4 | StoreManager assignment |
| D7 | P4 | CalendarYear, MonthNumber |
| D9 | P4 | Employee names + titles |
| D16 | P4 | Monthly store costs |
| P4 | E1..E3 | KPIs + Leaderboard + Trend + Scatter |
| E1..E2 | P5 | Product ID, horizon_days, ABC/XYZ filter |
| D4 | P5 | Historical daily sales |
| D5 | P5 | Product names |
| D7 | P5 | IsHoliday flag |
| D17 | P5 | Parquet snapshots (read) |
| D18 | P5 | LightGBM model weights (read) |
| P5 | D17 | Updated Parquet cache (write) |
| P5 | D18 | Retrained model (write) |
| P5 | E1..E2 | Forecasts + Alerts + ABC/XYZ |
| E1 | P6 | CSV/Excel files, schema changes, purge requests |
| D1..D16 | P6 | Table metadata (information_schema) |
| P6 | D1..D16 | Inserted/Updated rows |
| P6 | E1 | DW health report + upload results |
| E1 | P7 | ETL trigger command |
| E5 | P7 | POS transactions (via D19) |
| D19 | P7 | sales_orders + items (read) |
| P7 | D2 | FactSales + FactOnlineSales (write) |
| P7 | D4 | summary_daily_sales (refresh) |
| P7 | D7 | DimDate (ensure new dates) |
| P7 | D13..D16 | All aggregate tables (rebuild) |
| P7 | E1 | ETL status (running/completed/error) |
| D20 | P8 | realtime_daily_metrics (read) |
| D21 | P8 | POS master data (read) |
| P8 | E1..E2 | SSE stream + REST summary data |
| E5 | D19 | New POS transactions (external write) |
| E5 | D20 | Incremental metrics update |

---

*Tài liệu đặc tả chi tiết này bổ sung cho file tổng quan `THIET_KE_SO_DO_MUC_1.md`. Sử dụng cùng lúc cả 2 file để có đầy đủ thông tin thiết kế và vẽ sơ đồ.*
