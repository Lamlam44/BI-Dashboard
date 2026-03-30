# THIẾT KẾ SƠ ĐỒ MỨC 1 — HỆ THỐNG BI DASHBOARD (Contoso Retail)

> **Dự án:** BI Dashboard Intelligence System v5.0 — Enterprise Edition  
> **Cơ sở dữ liệu:** `retails_dataset` (Star Schema DW) + `pos_system` (POS Operational)  
> **Kiến trúc:** FastAPI (Python) + Next.js 14 (React/TypeScript)

---

## MỤC LỤC

- [PHẦN A — SƠ ĐỒ USE CASE MỨC 1](#phần-a--sơ-đồ-use-case-mức-1)
- [PHẦN B — SƠ ĐỒ TUẦN TỰ (SEQUENCE DIAGRAM) MỨC 1](#phần-b--sơ-đồ-tuần-tự-sequence-diagram-mức-1)
- [PHẦN C — SƠ ĐỒ LUỒNG DỮ LIỆU (DFD) MỨC 1](#phần-c--sơ-đồ-luồng-dữ-liệu-dfd-mức-1)

---

# PHẦN A — SƠ ĐỒ USE CASE MỨC 1

## A.1. Tổng quan về Sơ đồ Use Case

### A.1.1. Mục đích
Sơ đồ Use Case mức 1 phân rã hệ thống BI Dashboard thành **các module chức năng nghiệp vụ cụ thể**, xác định rõ:
- Ai (Actor nào) tương tác với chức năng nào
- Các quan hệ `<<include>>` (bắt buộc) và `<<extend>>` (tùy chọn) giữa các Use Case
- Phạm vi của từng module nghiệp vụ trong hệ thống

### A.1.2. Các Actor của hệ thống

| # | Actor | Mô tả | Vai trò (Role) trong hệ thống |
|---|-------|-------|-------------------------------|
| 1 | **Admin** (Quản trị viên) | Người quản trị toàn bộ hệ thống, quản lý dữ liệu, tài khoản, ETL pipeline | `admin` |
| 2 | **Executive** (Ban Giám đốc / CEO) | Lãnh đạo cấp cao, xem toàn bộ dữ liệu công ty, dự báo nhu cầu AI | `executive` |
| 3 | **Regional Manager** (Quản lý vùng) | Quản lý khu vực (Asia, Europe, North America), xem dữ liệu stores trong vùng | `regional_manager` |
| 4 | **Store Manager** (Quản lý cửa hàng) | Quản lý 1 cửa hàng cụ thể, chỉ xem dữ liệu của store mình quản lý | `store_manager` |
| 5 | **Hệ thống POS** (External System) | Hệ thống Point-of-Sale ngoại vi, nguồn dữ liệu giao dịch thời gian thực | Hệ thống bên ngoài |
| 6 | **MySQL Database** (External System) | Hệ quản trị CSDL lưu trữ Data Warehouse và POS data | Hệ thống bên ngoài |

### A.1.3. Quy tắc phân quyền RBAC (Row-Level Security)

| Actor | Dashboard (Sales & Profit) | Item Trends | Employee Performance | AI Forecasting | Data Management |
|-------|---------------------------|-------------|---------------------|----------------|-----------------|
| **Admin** | ✅ Toàn bộ + Realtime | ✅ Toàn bộ | ✅ Toàn bộ | ✅ Toàn bộ | ✅ Toàn bộ (ETL, CSV, Schema, Purge) |
| **Executive** | ✅ Toàn bộ + Realtime | ✅ Toàn bộ | ✅ Toàn bộ | ✅ Toàn bộ | ❌ |
| **Regional Manager** | ✅ Đa cửa hàng (không có Channel/Stockout/Realtime) | ✅ Toàn bộ | ✅ Toàn bộ | ❌ | ❌ |
| **Store Manager** | ✅ Chỉ cửa hàng mình (trend only) | ✅ Chỉ Inventory Metrics | ❌ | ❌ | ❌ |

---

## A.2. Use Case Diagram Mức 1 — Phân rã theo Module

### A.2.1. MODULE 1: XÁC THỰC & PHÂN QUYỀN (Authentication & Authorization)

**Ranh giới hệ thống:** Subsystem Authentication

| # | Use Case | Actor(s) | Mô tả chi tiết |
|---|----------|----------|-----------------|
| UC1.1 | **Đăng nhập hệ thống** | Admin, Executive, Regional Manager, Store Manager | Nhập username/password → Hệ thống xác thực → Trả JWT token |

| UC1.4 | **Đăng xuất** | Admin, Executive, Regional Manager, Store Manager | Xóa JWT token + session → Chuyển hướng về trang đăng nhập |
| UC1.6 | **Kiểm tra phân quyền** | Hệ thống (tự động) | Kiểm tra JWT token + RBAC + RLS cho mỗi request |

**Quan hệ:**
- UC1.1 `<<include>>` UC1.6 (Mỗi lần đăng nhập bắt buộc xác thực JWT)

---

### A.2.2. MODULE 2: PHÂN TÍCH BÁN HÀNG & LỢI NHUẬN (Sales & Profit Analytics)

**Ranh giới hệ thống:** Subsystem Sales & Profit

| # | Use Case | Actor(s) | Mô tả chi tiết |
|---|----------|----------|-----------------|
| UC2.1 | **Xem tổng quan KPI bán hàng** | Admin, Executive, Regional Manager, Store Manager | Xem YTD Sales, Total Profit, Profit Margin, YoY Growth, MoM Growth |
| UC2.2 | **Xem KPI tổng hợp nâng cao** | Admin, Executive | Xem 7 KPI bổ sung: Total Revenue, Total Transactions, Avg Transaction Value, Avg Basket Size, Gross Margin, Customers, Products |
| UC2.3 | **Xem biểu đồ xu hướng bán hàng** | Admin, Executive, Regional Manager, Store Manager | Biểu đồ đường Sales + Profit theo thời gian |
| UC2.4 | **Xem phân bổ doanh thu theo cửa hàng** | Admin, Executive, Regional Manager | Biểu đồ tròn Top Stores by Sales (ẩn với Store Manager) |
| UC2.5 | **Xem phân tích kênh bán hàng** | Admin, Executive | Biểu đồ cột Online vs Offline: revenue, profit, transactions |
| UC2.6 | **Xem doanh thu/m² sàn bán hàng** | Admin, Executive, Regional Manager | Biểu đồ cột ngang Sales per Square Foot by Store |
| UC2.7 | **Xem Budget vs Actual** | Admin, Executive, Regional Manager | So sánh Ngân sách vs Thực tế theo cửa hàng |
| UC2.8 | **Lọc dữ liệu theo thời gian** | Admin, Executive, Regional Manager, Store Manager | Chọn preset (YTD/12M/6M/3M/1M) hoặc khoảng thời gian tùy chỉnh |

**Quan hệ:**
- UC2.1, UC2.3, UC2.4, UC2.5, UC2.6, UC2.7 `<<include>>` UC1.6 (Bắt buộc kiểm tra phân quyền)
- UC2.8 `<<extend>>` UC2.1 (Lọc thời gian là tùy chọn, mặc định xem tất cả)
- UC2.2 `<<extend>>` UC2.1 (KPI nâng cao chỉ hiện cho Executive/Admin)
- UC2.9 `<<extend>>` UC2.1 (Realtime chỉ hiện cho Executive/Admin)
- UC2.5 `<<include>>` UC2.1 (Channel phải load sau khi Dashboard load)

---

### A.2.3. MODULE 3: PHÂN TÍCH XU HƯỚNG SẢN PHẨM & KHÁCH HÀNG (Item Trends)

**Ranh giới hệ thống:** Subsystem Item Trends

| # | Use Case | Actor(s) | Mô tả chi tiết |
|---|----------|----------|-----------------|
| UC3.1 | **Xem thống kê tổng quan** | Admin, Executive, Regional Manager | Tổng Doanh Thu, Tổng Khách Hàng, Phân Khúc Chủ Lực |
| UC3.2 | **Phân tích phân khúc khách hàng (RFM)** | Admin, Executive, Regional Manager | Biểu đồ Doughnut phân loại: Champion, Loyal, At Risk, Lost... |
| UC3.3 | **Xem sản phẩm bán chạy** | Admin, Executive, Regional Manager | Top 10 sản phẩm theo số lượng bán |
| UC3.4 | **Phân tích hiệu quả khuyến mãi** | Admin, Executive, Regional Manager | Biểu đồ cột chồng: Tác động khuyến mãi lên doanh số theo danh mục |
| UC3.5 | **Phân tích doanh thu theo địa lý** | Admin, Executive, Regional Manager | Biểu đồ cột nhóm: Doanh thu theo quốc gia theo quý |
| UC3.6 | **Phân tích hiệu suất sản phẩm (ABC)** | Admin, Executive, Regional Manager | Phân loại ABC (A ≤ 80%, B ≤ 95%, C còn lại) + Top 10 sản phẩm revenue/profit |
| UC3.7 | **Phân tích chỉ số tồn kho** | Admin, Executive, Regional Manager, Store Manager | Inventory Turnover, GMROI, Sell-Through Rate, Days of Supply |
| UC3.8 | **Phân tích tỷ lệ hết hàng (Stockout)** | Admin, Executive | Tỷ lệ hết hàng + Top sản phẩm hết hàng |
| UC3.9 | **Phân tích mức an toàn tồn kho** | Admin, Executive | Safety Stock: below/near/adequate |
| UC3.10 | **Lọc theo năm** | Admin, Executive, Regional Manager | Chọn năm (2007/2008/2009/ALL) để lọc dữ liệu trends |
| UC3.11 | **Phân tích RFM chi tiết** | Admin, Executive, Regional Manager | Phân khúc RFM đầy đủ: 7 segments + avg monetary + avg recency |

**Quan hệ:**
- UC3.1 → UC3.9 `<<include>>` UC1.6 (Phân quyền)
- UC3.10 `<<extend>>` UC3.1 (Lọc năm tùy chọn)
- UC3.7 là use case duy nhất Store Manager có quyền truy cập
- UC3.8, UC3.9 chỉ Executive/Admin (không có filter thời gian — snapshot data)

---

### A.2.4. MODULE 4: ĐÁNH GIÁ HIỆU SUẤT NHÂN VIÊN (Employee Performance)

**Ranh giới hệ thống:** Subsystem Employee Performance

| # | Use Case | Actor(s) | Mô tả chi tiết |
|---|----------|----------|-----------------|
| UC4.1 | **Xem KPI hiệu suất nhân viên** | Admin, Executive, Regional Manager | 4 KPIs: Total Net Sales, Avg Profit Margin, Avg Return Rate, Total Orders + so sánh với trung bình công ty |
| UC4.2 | **Xem nhân viên xuất sắc nhất** | Admin, Executive, Regional Manager | Top Performer: tên, chức danh, net sales, profit margin, return rate |
| UC4.3 | **Xem xu hướng hiệu suất theo thời gian** | Admin, Executive, Regional Manager | Biểu đồ đường đa trục: Net Sales + Profit Margin theo tháng |
| UC4.4 | **Xem bảng xếp hạng nhân viên** | Admin, Executive, Regional Manager | Danh sách top N (default 10) quản lý: Rank, Name, Net Sales, Margin, Return Rate |
| UC4.5 | **Xem biểu đồ phân tán hiệu suất** | Admin, Executive, Regional Manager | Scatter plot: Net Sales (X) vs Profit Margin (Y) per manager |
| UC4.6 | **Lọc theo năm/tháng/nhân viên** | Admin, Executive, Regional Manager | Chọn năm, tháng, quản lý cửa hàng cụ thể |
| UC4.7 | **Xem đánh giá năng lực (Capabilities)** | Admin, Executive, Regional Manager | Danh sách capabilities: enabled/not available + lý do |

**Quan hệ:**
- UC4.1 → UC4.5 `<<include>>` UC1.6 (Phân quyền + RLS)
- UC4.6 `<<extend>>` UC4.1 (Filter tùy chọn)
- UC4.7 `<<include>>` UC4.1 (Capabilities load cùng Dashboard)
- RLS: Regional Manager chỉ thấy stores trong vùng, Store Manager không truy cập module này

---

### A.2.5. MODULE 5: DỰ BÁO NHU CẦU BẰNG AI (AI Demand Forecasting)

**Ranh giới hệ thống:** Subsystem Demand Forecasting

| # | Use Case | Actor(s) | Mô tả chi tiết |
|---|----------|----------|-----------------|
| UC5.1 | **Xem tổng quan dự báo** | Admin, Executive | 4 KPI: Forecast Total Demand, SKU Count, Avg Daily Demand, Last Data Date |
| UC5.2 | **Xem cảnh báo sản phẩm nóng** | Admin, Executive | Bảng alerts: SKU, Product, ABC/XYZ Class, Spike Score |
| UC5.3 | **Tìm kiếm & lọc sản phẩm hàng loạt** | Admin, Executive | Lọc theo ABC (A/B/C), XYZ (X/Y/Z), giới hạn số lượng |
| UC5.4 | **Xem chi tiết dự báo sản phẩm (Deep Dive)** | Admin, Executive | Biểu đồ ComposedChart: predicted line + upper/lower confidence bounds |
| UC5.5 | **Tính toán lại dự báo (Recalculate)** | Admin, Executive | Kích hoạt recalculate → poll trạng thái → refresh toàn bộ |
| UC5.6 | **Huấn luyện mô hình AI cho sản phẩm** | Admin, Executive | Train LightGBM model cho 1 product cụ thể |
| UC5.7 | **Huấn luyện mô hình toàn cầu** | Admin, Executive | Train global model trên top 500 sản phẩm |

**Quan hệ:**
- UC5.1, UC5.2, UC5.3 `<<include>>` UC1.6 (Phân quyền)
- UC5.4 `<<extend>>` UC5.2 (Deep Dive mở rộng từ click vào alert)
- UC5.4 `<<extend>>` UC5.3 (Deep Dive mở rộng từ click vào bulk item)
- UC5.5 `<<include>>` UC5.7 (Recalculate kích hoạt huấn luyện lại mô hình)

---

### A.2.6. MODULE 6: QUẢN TRỊ DỮ LIỆU (Data Management)

**Ranh giới hệ thống:** Subsystem Data Management

| # | Use Case | Actor(s) | Mô tả chi tiết |
|---|----------|----------|-----------------|
| UC6.1 | **Xem tổng quan Data Warehouse** | Admin | Xem số bảng Fact/Dim/Agg, row count, last updated |
| UC6.2 | **Chạy ETL Pipeline** | Admin | Trigger ETL: POS → DW sync + rebuild aggregate tables |
| UC6.3 | **Quản lý Data Sources** | Admin | Xem danh sách nguồn dữ liệu, test kết nối |
| UC6.4 | **Upload CSV vào DW** | Admin | Upload file → preview → map columns → transform & load |
| UC6.5 | **Quản lý Schema** | Admin | Xem/chỉnh sửa schema (display_name, columns, mô tả) |
| UC6.6 | **Xóa dữ liệu (Purge)** | Admin | Xóa dữ liệu theo DATE_RANGE hoặc CATEGORY (backup trước) |
| UC6.7 | **Tải template CSV** | Admin | Download template Excel cho bảng cụ thể |
| UC6.8 | **Upload dữ liệu Excel/CSV thông thường** | Admin | Upload & validate → preview → insert/upsert vào MySQL |

**Quan hệ:**
- UC6.1 → UC6.8 `<<include>>` UC1.6 (Phân quyền Admin)
- UC6.4 `<<include>>` UC6.5 (Upload CSV cần schema mapping)
- UC6.6 `<<include>>` Backup dữ liệu (Hệ thống tự động backup trước khi xóa)
- UC6.2 `<<include>>` Đồng bộ POS (Bắt buộc sync POS → DW)

---



## A.3. Hướng dẫn vẽ Use Case Diagram Mức 1

### Cách vẽ:
1. **Vẽ ranh giới hệ thống** (System Boundary): Hình chữ nhật bao quanh tất cả Use Case, ghi tên "BI Dashboard System"
2. **Vẽ các Actor** (hình người que) bên ngoài ranh giới: Admin, Executive, Regional Manager, Store Manager, POS System, MySQL Database
3. **Vẽ các Use Case** (hình oval) bên trong ranh giới, nhóm theo module
4. **Nối Actor → Use Case** bằng đường thẳng (association)
5. **Vẽ quan hệ**: Đường đứt nét mũi tên `<<include>>` và `<<extend>>`

### Mẹo quan trọng:
- **`<<include>>`**: Mũi tên từ Use Case cha → Use Case con (Use Case cha bắt buộc gọi con). Ví dụ: UC2.1 --<<include>>--> UC1.6
- **`<<extend>>`**: Mũi tên từ Use Case mở rộng → Use Case gốc (Con mở rộng cha). Ví dụ: UC2.8 --<<extend>>--> UC2.1
- **Generalization giữa Actors**: Admin, Executive, Regional Manager, Store Manager đều kế thừa từ "Người dùng" (User) chung

---

# PHẦN B — SƠ ĐỒ TUẦN TỰ (SEQUENCE DIAGRAM) MỨC 1

## B.1. Tổng quan về Sơ đồ Tuần tự

### B.1.1. Mục đích
Sơ đồ tuần tự mức 1 mô tả **chi tiết luồng xử lý** của từng Use Case quan trọng, cho thấy:
- Các đối tượng (Lifeline) tham gia: Actor, Frontend (Browser/React), Backend Controller, Service Layer, Database
- Trình tự thông điệp (message) theo chiều thời gian từ trên xuống dưới
- Các phản hồi (return), điều kiện (guard/alt), vòng lặp (loop)

### B.1.2. Các Lifeline chung của hệ thống

| Lifeline | Kiểu | Mô tả |
|----------|------|-------|
| **:User** | Actor | Người dùng (Admin/Executive/Regional Manager/Store Manager) |
| **:Browser** | Boundary | Next.js 14 Frontend (React/TypeScript) |
| **:API Gateway** | Controller | FastAPI Main App (main.py, routing, CORS) |
| **:Auth Module** | Controller | auth.py + auth_api.py (JWT, RBAC) |
| **:Service** | Service | Các service layer (service.py, metrics.py, analytics.py...) |
| **:Cache** | Entity | In-memory cache / Parquet cache |
| **:MySQL DW** | Entity | Database `retails_dataset` (Star Schema) |
| **:MySQL POS** | Entity | Database `pos_system` (Operational) |
| **:AI Model** | Entity | LightGBM Demand Forecasting Model |

---

## B.2. Sequence Diagram cho từng Use Case chính

### B.2.1. SD-01: ĐĂNG NHẬP HỆ THỐNG (UC1.1)

**Actors:** User  
**Lifelines:** User → Browser → API Gateway → Auth Module → MySQL DW

```
┌──────┐     ┌──────────┐     ┌──────────────┐    ┌─────────────┐    ┌───────────┐
│ User │     │ Browser  │     │ API Gateway  │    │ Auth Module │    │ MySQL DW  │
└──┬───┘     └────┬─────┘     └──────┬───────┘    └──────┬──────┘    └─────┬─────┘
   │               │                  │                   │                 │
   │ 1. Nhập username/password        │                   │                 │
   │──────────────>│                  │                   │                 │
   │               │                  │                   │                 │
   │               │ 2. POST /auth/login                  │                 │
   │               │  {username, password}                 │                 │
   │               │─────────────────>│                   │                 │
   │               │                  │                   │                 │
   │               │                  │ 3. authenticate_user(username, pwd) │
   │               │                  │──────────────────>│                 │
   │               │                  │                   │                 │
   │               │                  │                   │ 4. SELECT * FROM bi_users
   │               │                  │                   │  WHERE username = ?
   │               │                  │                   │────────────────>│
   │               │                  │                   │                 │
   │               │                  │                   │ 5. Return user row
   │               │                  │                   │<────────────────│
   │               │                  │                   │                 │
   │               │                  │                   │ 6. verify_password()
   │               │                  │                   │ (SHA-256 + salt + hmac)
   │               │                  │                   │──┐              │
   │               │                  │                   │  │ Self-message │
   │               │                  │                   │<─┘              │
   │               │                  │                   │                 │
   │               │                  │       ┌───────────────────────┐     │
   │               │                  │       │ alt [password valid]  │     │
   │               │                  │       │                       │     │
   │               │                  │ 7a. create_access_token(user)│     │
   │               │                  │<──────│ (JWT HS256, 24h exp)  │     │
   │               │                  │       │                       │     │
   │               │ 8a. 200 OK       │       │                       │     │
   │               │ {access_token,   │       │                       │     │
   │               │  token_type,     │       │                       │     │
   │               │  user: {id, username,    │                       │     │
   │               │    role, region,  │       │                       │     │
   │               │    store_key,     │       │                       │     │
   │               │    display_name}} │       │                       │     │
   │               │<─────────────────│       │                       │     │
   │               │                  │       ├───────────────────────┤     │
   │               │                  │       │ [password invalid]    │     │
   │               │                  │ 7b. Return None              │     │
   │               │                  │<──────│                       │     │
   │               │ 8b. 401 Unauthorized     │                       │     │
   │               │<─────────────────│       │                       │     │
   │               │                  │       └───────────────────────┘     │
   │               │                  │                   │                 │
   │               │ 9. Lưu bi_token + bi_user            │                 │
   │               │    vào localStorage                  │                 │
   │               │──┐               │                   │                 │
   │               │  │               │                   │                 │
   │               │<─┘               │                   │                 │
   │               │                  │                   │                 │
   │ 10. Redirect → /dashboard        │                   │                 │
   │<──────────────│                  │                   │                 │
```

**Mô tả luồng:**
1. User nhập username/password trên giao diện Login
2. Browser gửi `POST /auth/login` với body `{username, password}` đến API Gateway
3. API Gateway chuyển tiếp cho Auth Module gọi `authenticate_user()`
4. Auth Module truy vấn bảng `bi_users` trong MySQL DW
5. MySQL trả về bản ghi user (hoặc NULL nếu không tồn tại)
6. Auth Module gọi `verify_password()` — so sánh SHA-256 hash với salt
7. **Alt fragment:**
   - **[Valid]**: Tạo JWT token (HS256, payload: sub, uid, role, region, store_key, display_name, exp=24h)
   - **[Invalid]**: Trả None
8. API Gateway trả response tương ứng (200 + token hoặc 401)
9. Browser lưu token + user info vào `localStorage`
10. Redirect người dùng đến Dashboard

---

### B.2.2. SD-02: XEM DASHBOARD BÁN HÀNG & LỢI NHUẬN (UC2.1 + UC2.5)

**Actors:** User (Executive/Admin)  
**Lifelines:** User → Browser → API Gateway → Sale-Profit Service → Cache (Parquet) → MySQL DW

```
┌──────┐     ┌──────────┐     ┌──────────────┐    ┌────────────────┐   ┌─────────┐   ┌───────────┐
│ User │     │ Browser  │     │ API Gateway  │    │ SaleProfit Svc│   │ Cache   │   │ MySQL DW  │
└──┬───┘     └────┬─────┘     └──────┬───────┘    └───────┬────────┘   └────┬────┘   └─────┬─────┘
   │               │                  │                    │                 │               │
   │ 1. Truy cập /dashboard           │                    │                 │               │
   │──────────────>│                  │                    │                 │               │
   │               │                  │                    │                 │               │
   │               │ 2. GET /sale-profit/api/dashboard/sales                 │               │
   │               │    ?start_date=&end_date=             │                 │               │
   │               │    [Header: Authorization: Bearer <JWT>]                │               │
   │               │─────────────────>│                    │                 │               │
   │               │                  │                    │                 │               │
   │               │                  │ 3. get_current_user()               │               │
   │               │                  │ (Decode JWT, kiểm tra exp)          │               │
   │               │                  │──┐                 │                 │               │
   │               │                  │  │                 │                 │               │
   │               │                  │<─┘                 │                 │               │
   │               │                  │                    │                 │               │
   │               │                  │ 4. get_rls_store_keys(user)         │               │
   │               │                  │───────────────────>│                 │               │
   │               │                  │                    │                 │               │
   │               │                  │                    │ 5. Kiểm tra role               │
   │               │                  │                    │ [executive/admin → None (all)]  │
   │               │                  │                    │ [store_mgr → [store_key]]       │
   │               │                  │                    │ [regional_mgr → query stores]   │
   │               │                  │                    │                 │               │
   │               │                  │ 6. get_sales_profit_dashboard(start, end, store_keys)│
   │               │                  │───────────────────>│                 │               │
   │               │                  │                    │                 │               │
   │               │                  │                    │ 7. load_sales_profit_snapshot() │
   │               │                  │                    │────────────────>│               │
   │               │                  │                    │                 │               │
   │               │                  │                    │    ┌────────────────────────┐   │
   │               │                  │                    │    │ alt [cache tồn tại]    │   │
   │               │                  │                    │    │                        │   │
   │               │                  │                    │ 8a. Return DataFrame      │   │
   │               │                  │                    │    │  (from Parquet)        │   │
   │               │                  │                    │<───│                        │   │
   │               │                  │                    │    ├────────────────────────┤   │
   │               │                  │                    │    │ [cache hết hạn/trống]  │   │
   │               │                  │                    │ 8b. Query summary_daily_sales  │
   │               │                  │                    │    │  JOIN DimStore          │   │
   │               │                  │                    │    │  JOIN DimProduct        │   │
   │               │                  │                    │────│───────────────────────>│   │
   │               │                  │                    │    │                        │   │
   │               │                  │                    │ 8c. Build & save Parquet  │   │
   │               │                  │                    │<───│────────────────────────│   │
   │               │                  │                    │    └────────────────────────┘   │
   │               │                  │                    │                 │               │
   │               │                  │                    │ 9. Apply RLS filter            │
   │               │                  │                    │ 10. Calculate:                 │
   │               │                  │                    │   - YTD/MTD/Total sales & profit│
   │               │                  │                    │   - YoY/MoM growth              │
   │               │                  │                    │   - Monthly trend               │
   │               │                  │                    │   - Store pie chart             │
   │               │                  │                    │──┐              │               │
   │               │                  │                    │  │              │               │
   │               │                  │                    │<─┘              │               │
   │               │                  │                    │                 │               │
   │               │ 11. Return SalesDashboardResponse     │                 │               │
   │               │ {ytd, mtd, total, ytd_profit, ...     │                 │               │
   │               │  avg_profit_margin, yoy_growth,       │                 │               │
   │               │  mom_growth, trend, profit_trend,     │                 │               │
   │               │  store_pie, last_updated}             │                 │               │
   │               │<─────────────────│                    │                 │               │
   │               │                  │                    │                 │               │
   │ 12. Render Dashboard (KPI cards + charts)             │                 │               │
   │<──────────────│                  │                    │                 │               │
   │               │                  │                    │                 │               │
   │               │   == PARALLEL == (Promise.all)        │                 │               │
   │               │ 13. GET /sale-profit/api/channels     │                 │               │
   │               │─────────────────>│                    │                 │               │
   │               │                  │ 14. get_channel_breakdown()         │               │
   │               │                  │───────────────────>│                 │               │
   │               │                  │                    │ 15. Query agg_channel_summary  │
   │               │                  │                    │───────────────────────────────>│
   │               │                  │                    │ 16. Return channels            │
   │               │                  │                    │<───────────────────────────────│
   │               │ 17. Return ChannelResponse            │                 │               │
   │               │<─────────────────│                    │                 │               │
   │               │                  │                    │                 │               │
   │ 18. Render Channel Breakdown chart                    │                 │               │
   │<──────────────│                  │                    │                 │               │
```

---

### B.2.3. SD-03: PHÂN TÍCH HIỆU SUẤT NHÂN VIÊN (UC4.1 + UC4.3 + UC4.4)

**Actors:** User (Executive/Admin/Regional Manager)  
**Lifelines:** User → Browser → API Gateway → Employee Service → Cache → MySQL DW

```
Luồng chính:
1. User truy cập /employee-performance
2. Browser gọi GET /employee-performance/filters (Bearer JWT)
3. API Gateway → get_current_user() → _resolve_rls() (kiểm tra role)
4. Employee Service → get_filters() → Query DimDate (years, months), DimStore (stores), DimEmployee (employees)
   - Nếu store_manager: filter theo store_key
   - Nếu regional_manager: filter theo region
5. Return FiltersResponse {years[], months[], stores[], employees[]}
6. Browser render FiltersBar

7. Browser gọi GET /employee-performance/dashboard?year=&month=&employee_key= (Bearer JWT)
8. Employee Service → Kiểm cache (TTL 10 phút)
9. [Cache miss]: 
   a. _manager_monthly_subquery: 
      JOIN summary_daily_sales → DimStore → DimDate → agg_store_monthly_costs
      GROUP BY StoreManager, CalendarYear, MonthNumber
   b. Tính KPIs: net_sales, profit_margin, return_rate, order_count, avg_ticket_size
   c. Tìm top_performer (max net_sales)
   d. So sánh vs company average
   e. Đánh giá capabilities (6 items)
10. Return DashboardResponse + lưu cache

11. === PARALLEL (Promise.allSettled) ===
12. Browser gọi GET /employee-performance/trend (Net Sales + Profit Margin theo tháng)
13. Browser gọi GET /employee-performance/leaderboard?top_n=10 (Top 10 managers)
14. Browser gọi GET /employee-performance/scatter (Net Sales vs Profit Margin scatter)
15. Cả 3 queries đều sử dụng cùng JOINs: summary_daily_sales ↔ DimStore ↔ DimDate ↔ agg_store_monthly_costs

16. Return TrendResponse, LeaderboardResponse, ScatterResponse
17. Browser render: KpiCards + TopPerformerCard + CapabilityPanel + TrendChart + LeaderboardTable + ScatterChart
```

---

### B.2.4. SD-04: DỰ BÁO NHU CẦU SẢN PHẨM (UC5.1 + UC5.4)

**Actors:** User (Executive/Admin)  
**Lifelines:** User → Browser → API Gateway → Forecast Service → AI Model → Parquet Cache → MySQL DW

```
Luồng chính:
1. User truy cập /forecasting
2. Browser kiểm tra role (chỉ executive/admin)

=== Layer 1: Overview ===
3. Browser gọi GET /forecast/overview?horizon_days=14
4. Forecast Service → ensure_parquet_cache()
   a. Kiểm tra parquet tồn tại + tuổi < 120 ngày
   b. [Miss]: Query summary_daily_sales → build daily_sales_snapshot.parquet
   c. Build abc_xyz_snapshot.parquet (ABC/XYZ classification)
5. load_overview_from_parquet(horizon_days=14)
   → Đọc parquet → Tính forecast_total_demand, sku_count, avg_daily_demand
6. Return OverviewResponse

=== Layer 2: Alerts ===
7. Browser gọi GET /forecast/alerts?limit=20&abc_class=A
8. load_alerts_from_parquet() → Lọc Class A + sort by spike_score
9. Return AlertsResponse

=== Layer 3: Bulk Query ===
10. Browser gọi GET /forecast/bulk/query?abc_class=&xyz_class=&limit=300
11. query_bulk_from_parquet(filters) → Filter & sort
12. Return BulkResponse

=== Layer 4: Deep Dive (khi User click vào 1 sản phẩm) ===
13. User click "Deep Dive" trên SKU productId
14. Browser gọi GET /forecast/forecast/{productId}?days_ahead=14
15. Forecast Service:
    a. load_product_time_series_from_parquet(productId)
    b. fill_missing_dates(product_ts) → forward-fill gaps
    c. create_all_features(product_ts):
       - Lag features: shift 7, 14, 30 ngày
       - Rolling features: mean + std (window=7)
       - Calendar features: day_of_week, month, quarter, is_weekend, is_holiday
    d. model.predict_future(features_df, n_steps=14):
       ┌─── loop [i = 1 to 14] ────────────────────────┐
       │ 1. Lấy last 90 rows                            │
       │ 2. Predict 1 step với 3 models:                │
       │    - model_base → point forecast               │
       │    - model_lower → 5th percentile (CI)         │
       │    - model_upper → 95th percentile (CI)        │
       │ 3. Append predicted row vào data               │
       │ 4. Recalculate all features                    │
       └────────────────────────────────────────────────┘
16. Return ForecastResponse {product_id, product_name, forecast_points[]}
    Mỗi point: {date, actual, predicted, upper_bound, lower_bound}
17. Browser render ComposedChart (predicted line + confidence area)
```

---

### B.2.5. SD-05: CHẠY ETL PIPELINE (UC6.2)

**Actors:** Admin  
**Lifelines:** Admin → Browser → API Gateway → ETL Service → POS DB → DW DB

```
Luồng chính:
1. Admin truy cập /data-management → Tab "ETL & Data Sources"
2. Admin click "Chạy ETL"
3. Browser gọi POST /data/etl/run
4. API Gateway kiểm tra quyền Admin → Start background thread

=== ETL Pipeline (Background) ===
5. pos_etl.sync_pos_to_dw():
   a. Kiểm tra pos_change_log count (incremental check)
   b. Query POS DB: 
      JOIN sales_orders + sales_order_items 
      WHERE status IN ('Completed', 'Returned')
   c. Transform:
      - Phân loại InStore/Online
      - Tính sales_qty, return_qty, discount_amt, total_cost
      - Key offset: SaleKey = item_id + 10,000,000
   d. Load: REPLACE INTO FactSales / FactOnlineSales (batch 2000)
   e. Ensure DimDate cho ngày mới
   f. Refresh summary_daily_sales cho POS data

6. create_aggregate_tables(force=True):
   a. Build agg_inventory_metrics (turnover, sell-through, GMROI, days_of_supply)
   b. Build agg_product_performance (ABC classification, revenue rank)
   c. Build agg_customer_rfm (RFM scoring → 7 segments)
   d. Build agg_kpi_summary (9 pre-computed KPIs)
   e. Build agg_store_monthly_costs
   f. Build agg_channel_summary

=== Polling ===
7. Browser poll GET /data/etl/status mỗi 5 giây
8. Khi ETL hoàn tất: Return {status: 'completed', duration, tables_built}
9. Browser hiển thị kết quả ETL
```

---

### B.2.6. SD-06: UPLOAD CSV VÀO DATA WAREHOUSE (UC6.4)

**Actors:** Admin  
**Lifelines:** Admin → Browser → API Gateway → Data Management Service → MySQL DW

```
Luồng chính:
1. Admin chọn tab "CSV Upload"
2. Admin chọn file CSV → Upload

3. Browser gọi POST /data/csv-upload-preview (FormData: file)
4. Data Mgmt Service:
   a. Đọc CSV với pandas
   b. _sanitize_df() → Replace NaN with None
   c. Auto-detect target table (match columns)
   d. Suggest column mapping
   e. Preview 10 rows đầu tiên
5. Return {preview_rows, suggested_table, column_mapping}

6. Admin xác nhận/chỉnh sửa mapping → Click "Transform & Load"

7. Browser gọi POST /data/csv-transform-load (FormData: file + mapping + target_table)
8. Data Mgmt Service:
   a. _validate_table_name() → Kiểm tra ALLOWED_TABLES whitelist (chống SQL injection)
   b. _fetch_table_columns(table) → Lấy schema từ information_schema
   c. Transform columns theo mapping
   d. _bulk_upsert(table, rows, primary_keys):
      INSERT INTO {table} (...) VALUES (...) 
      ON DUPLICATE KEY UPDATE ...
      (batch processing)
9. Return {status: 'success', rows_inserted, rows_updated}
10. Browser hiển thị kết quả upload
```

---

### B.2.7. SD-07: XEM XU HƯỚNG SẢN PHẨM & RFM (UC3.2 + UC3.6)

**Actors:** User (Executive/Admin/Regional Manager)  
**Lifelines:** User → Browser → API Gateway → Analytics Service → Cache → MySQL DW

```
Luồng chính:
1. User truy cập /item-trends
2. Browser render 2 sections: "Phân tích theo năm" + "Phân tích tổng hợp"

=== Parallel API calls ===
3a. GET /trends/api/summary-stats?start_date=&end_date=
    → Query summary_daily_sales (SUM revenue) 
    → Query FactOnlineSales (COUNT DISTINCT CustomerKey)
    → Return {total_revenue, total_customers, top_segment}

3b. GET /trends/api/customer-segments?start_date=&end_date=
    → Kiểm cache (TTL 15 phút)
    → [Miss]: Query customer_segments table → GROUP BY Segment
    → Return {segments: [{segment, count, percentage}]}

3c. GET /trends/api/trending-products?start_date=&end_date=
    → Cache check → Query summary_daily_sales JOIN DimProduct
    → GROUP BY ProductName ORDER BY SUM(total_sales_quantity) DESC LIMIT 10
    → Return {products: [{product_name, total_quantity}]}

3d. GET /trends/api/product-performance
    → Cache check → Query agg_product_performance
    → Return {abc_distribution, top_products[], product_table[]}

3e. GET /trends/api/inventory-metrics
    → Cache check → Query agg_inventory_metrics JOIN DimProduct
    → Top 20 ORDER BY inventory_turnover DESC
    → Return {summary, chart_data, table_data}

3f. GET /data/api/rfm-segments
    → Query agg_customer_rfm → GROUP BY rfm_segment
    → Return {segments: [{segment, count, avg_monetary, avg_recency}]}
=== End Parallel ===

4. Browser render:
   - StatsCards (3 KPI cards)
   - CustomerChart (Doughnut)
   - TrendingProductsChart (List)
   - ProductPerformanceChart (PieChart + BarChart + Table)
   - InventoryMetricsChart (Cards + BarChart + Table)
   - RfmSegmentsChart (BarChart + Segment cards)
```

---

### B.2.8. SD-08: NHẬN DỮ LIỆU REALTIME QUA SSE (UC7.1)

**Actors:** User (Executive/Admin)  
**Lifelines:** User → Browser → API Gateway → Realtime Service → Cache → MySQL POS

```
Luồng chính:
1. User đăng nhập thành công
2. RefreshProvider (React Context) tự động mở EventSource:
   GET /realtime/stream (Server-Sent Events)

3. API Gateway → Realtime Service → SSE Generator:
   ┌─── loop [mỗi 3 giây] ──────────────────────────────────┐
   │ 4. get_realtime_summary()                                │
   │    a. Kiểm in-memory cache (TTL 10 giây)                │
   │    b. [Cache miss]:                                      │
   │       Query realtime_daily_metrics FROM POS DB           │
   │       WHERE metric_date = CURDATE()                      │
   │       SUM(revenue, cost, profit, orders)                 │
   │       + Query MTD (month-to-date)                        │
   │    c. Lưu vào cache                                      │
   │                                                          │
   │ 5. So sánh last_updated với lần push trước              │
   │    [Nếu thay đổi]:                                      │
   │       Push SSE event: data: {today_revenue, today_cost,  │
   │       today_profit, today_orders, today_items_sold,       │
   │       today_discount, mtd_revenue, mtd_profit,            │
   │       mtd_orders, last_updated}                           │
   │    [Nếu không đổi]:                                      │
   │       Push keepalive: ": keepalive\n\n"                   │
   └──────────────────────────────────────────────────────────┘

6. Browser (RefreshProvider) nhận SSE event → update realtimeSummary state
7. Dashboard page render: Realtime Today cards (live update)
```

---

## B.3. Hướng dẫn vẽ Sequence Diagram

### Cách vẽ:
1. **Xác định Lifelines**: Vẽ hình chữ nhật (head) bên trên, đường đứt nét thẳng đứng (stem) đi xuống
2. **Thứ tự trái → phải**: Actor → Frontend/Boundary → Controller → Service → Database
3. **Messages**: Mũi tên nét liền (→) cho synchronous call, nhãn ghi tên hàm/API
4. **Return**: Mũi tên nét đứt (←--) cho response  
5. **Activation bar**: Hình chữ nhật mỏng trên stem khi đối tượng đang xử lý
6. **Alt fragment**: Khung hình chữ nhật đứt nét, ghi `alt [condition]`, phân chia bằng đường ngang đứt nét
7. **Loop fragment**: Khung ghi `loop [condition]` cho vòng lặp
8. **Self-message**: Mũi tên hình chữ U quay lại chính lifeline

### Quy ước đặt tên:
- Message synchronous: `tên_hàm()` hoặc `HTTP_METHOD /endpoint`
- Message return: `Return {data}` hoặc `HTTP_STATUS Response`
- Guard condition: `[condition]`

---

# PHẦN C — SƠ ĐỒ LUỒNG DỮ LIỆU (DFD) MỨC 1

## C.1. Tổng quan về DFD

### C.1.1. Mục đích
DFD Mức 1 phân rã hệ thống BI Dashboard thành **các tiến trình con (sub-processes)**, cho thấy:
- Dữ liệu được lấy từ đâu (External Entities, Data Stores)
- Xử lý ở đâu (Processes)
- Kết quả trả về đâu (External Entities, Data Stores)

### C.1.2. Ký hiệu sử dụng (Yourdon-DeMarco)
| Ký hiệu | Hình dạng | Mô tả |
|----------|-----------|-------|
| **External Entity** | Hình chữ nhật | Tác nhân bên ngoài (Actor, hệ thống ngoài) |
| **Process** | Hình tròn (circle) | Tiến trình xử lý dữ liệu |
| **Data Store** | 2 đường ngang song song (mở) | Kho dữ liệu (bảng DB, file) |
| **Data Flow** | Mũi tên | Hướng di chuyển của dữ liệu |

### C.1.3. Nhắc lại DFD Mức 0 (Context Diagram)

```
┌─────────────────┐                                           ┌─────────────────┐
│   Người dùng    │ ─── Yêu cầu & Dữ liệu nhập ──────────> │                 │
│ (Admin/Exec/RM/ │ <── Báo cáo, Dashboard, Dự báo ──────── │  BI DASHBOARD   │
│  Store Manager) │                                           │     SYSTEM      │
└─────────────────┘                                           │   (Process 0)   │
                                                              │                 │
┌─────────────────┐                                           │                 │
│  Hệ thống POS   │ ─── Giao dịch bán hàng ────────────────> │                 │
│ (External)       │ <── Trạng thái đồng bộ ────────────────  │                 │
└─────────────────┘                                           └─────────────────┘
```

---

## C.2. DFD Mức 1 — Phân rã chi tiết

### C.2.1. Danh sách các tiến trình (Processes) Mức 1

| Process ID | Tên tiến trình | Mô tả |
|------------|----------------|-------|
| **P1** | Xác thực & Phân quyền | Xử lý đăng nhập, JWT token, RBAC, RLS |
| **P2** | Phân tích Bán hàng & Lợi nhuận | Dashboard Sales: KPI, trend, channel, store analysis |
| **P3** | Phân tích Xu hướng Sản phẩm & Khách hàng | Item Trends: RFM, ABC, promotion, geography, inventory |
| **P4** | Đánh giá Hiệu suất Nhân viên | Employee Performance: KPI, trend, leaderboard, scatter |
| **P5** | Dự báo Nhu cầu bằng AI | Demand Forecasting: LightGBM, recursive multi-step |
| **P6** | Quản trị Dữ liệu | Data Management: DW health, upload, schema, purge |
| **P7** | ETL Pipeline | Extract-Transform-Load: POS→DW sync, aggregate build |
| **P8** | Giám sát Thời gian thực | Realtime: SSE push, daily metrics, inventory |

### C.2.2. Danh sách các Kho dữ liệu (Data Stores)

| Store ID | Tên kho dữ liệu | Bảng/File thực tế |
|----------|------------------|-------------------|
| **D1** | Bảng người dùng | `bi_users` (MySQL retails_dataset) |
| **D2** | Bảng bán hàng gốc | `FactSales`, `FactOnlineSales` (MySQL retails_dataset) |
| **D3** | View tổng hợp bán hàng | `v_total_sales` (View UNION của D2) |
| **D4** | Bảng tổng hợp hàng ngày | `summary_daily_sales` (MySQL retails_dataset) |
| **D5** | Bảng chiều sản phẩm | `DimProduct`, `DimProductCategory`, `DimProductSubcategory` |
| **D6** | Bảng chiều cửa hàng | `DimStore`, `DimGeography` |
| **D7** | Bảng chiều thời gian | `DimDate` |
| **D8** | Bảng chiều khách hàng | `DimCustomer` |
| **D9** | Bảng chiều nhân viên | `DimEmployee` |
| **D10** | Bảng chiều khuyến mãi | `DimPromotion` |
| **D11** | Bảng tồn kho | `FactInventory` |
| **D12** | Bảng chỉ tiêu | `FactSalesQuota` |
| **D13** | Bảng aggregate KPI | `agg_kpi_summary`, `agg_channel_summary` |
| **D14** | Bảng aggregate sản phẩm | `agg_product_performance`, `agg_inventory_metrics` |
| **D15** | Bảng aggregate khách hàng | `agg_customer_rfm`, `customer_segments` |
| **D16** | Bảng aggregate chi phí | `agg_store_monthly_costs` |
| **D17** | Cache Parquet | `*.parquet` files (sales snapshot, forecast, RFM) |
| **D18** | Mô hình AI đã huấn luyện | `global_demand_model.pkl` |
| **D19** | POS Giao dịch | `sales_orders`, `sales_order_items` (MySQL pos_system) |
| **D20** | POS Metrics thời gian thực | `realtime_daily_metrics`, `current_inventory` (MySQL pos_system) |
| **D21** | POS Master data | `products`, `employees`, `stores`, `promotions` (MySQL pos_system) |

### C.2.3. Danh sách các Tác nhân bên ngoài (External Entities)

| Entity | Mô tả |
|--------|-------|
| **E1** | Admin (Quản trị viên) |
| **E2** | Executive (Ban Giám đốc) |
| **E3** | Regional Manager (Quản lý vùng) |
| **E4** | Store Manager (Quản lý cửa hàng) |
| **E5** | Hệ thống POS |

---

## C.3. Chi tiết luồng dữ liệu cho từng tiến trình

### C.3.1. P1 — Xác thực & Phân quyền

```
┌──────────────┐                                         
│ E1/E2/E3/E4  │                                         
│ (Người dùng) │                                         
└──────┬───────┘                                         
       │                                                  
       │ Username, Password                               
       ▼                                                  
   ┌───────────┐                                         
   │    P1     │                                         
   │ Xác thực  │─── Truy vấn thông tin tài khoản ──────> ══ D1 ══
   │& Phân     │<── Dữ liệu user (role, region, store) ─ ══ bi_users ══
   │ quyền     │                                         
   └───────────┘                                         
       │                                                  
       │ JWT Token + User Context (role, RLS filters)   
       ▼                                                  
   [Đến P2, P3, P4, P5, P6, P7, P8]                    
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1/E2/E3/E4 | Username + Password | Thông tin đăng nhập |
| D1 (bi_users) | User record | id, username, password_hash, role, region, store_key, employee_key |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1/E2/E3/E4 | JWT Token + User Info | access_token (HS256, 24h), user profile |
| P2-P8 | UserContext | username, role, region, store_key (cho RBAC + RLS) |

**Xử lý bên trong:**
1. Nhận username/password → Truy vấn D1 (`SELECT * FROM bi_users WHERE username = ?`)
2. Verify password (SHA-256 + salt + hmac.compare_digest)
3. Tạo JWT token (HS256, payload: sub, uid, role, region, store_key, exp)
4. Với mỗi request tiếp theo: Decode JWT → Tạo UserContext → Kiểm tra RBAC
5. Tính RLS store_keys: Executive/Admin → tất cả | Store Manager → 1 store | Regional Manager → JOIN DimStore+DimGeography

---

### C.3.2. P2 — Phân tích Bán hàng & Lợi nhuận

```
                                                ══ D4 ══ (summary_daily_sales)
                                               ╱
                                              ╱  Doanh thu, chi phí, lợi nhuận theo ngày/cửa hàng
┌──────────────┐                             ╱
│ E1/E2/E3/E4  │    Các tham số lọc        ╱    ══ D6 ══ (DimStore, DimGeography)
│ (Người dùng) │──────────────────────>┌───────────┐
│              │                       │    P2     │──── ══ D12 ══ (FactSalesQuota)
│              │<──────────────────────│ Phân tích │
│              │   Dashboard data      │ Bán hàng  │──── ══ D13 ══ (agg_kpi_summary,
│              │   (KPI, charts,       │& Lợi      │           agg_channel_summary)
│              │    trends)            │ nhuận     │
└──────────────┘                       └───────────┘──── ══ D17 ══ (Parquet cache)
                                              ╲
                                               ╲  ══ D5 ══ (DimProduct)
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1/E2/E3/E4 | start_date, end_date | Khoảng thời gian lọc |
| P1 | UserContext + RLS store_keys | Phân quyền và filter |
| D4 | summary_daily_sales | Dữ liệu bán hàng tổng hợp hàng ngày |
| D6 | DimStore + DimGeography | Thông tin cửa hàng (tên, diện tích, vị trí) |
| D5 | DimProduct | Thông tin sản phẩm |
| D12 | FactSalesQuota | Chỉ tiêu ngân sách theo cửa hàng |
| D13 | agg_kpi_summary, agg_channel_summary | KPI tổng hợp đã pre-compute |
| D17 | sales_profit_daily_snapshot.parquet | Cache Parquet |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1/E2/E3/E4 | SalesDashboardResponse | YTD/MTD/Total sales, profit, margin, growth, trend, store_pie |
| E1/E2/E3/E4 | ChannelResponse | Online vs Offline Revenue/Profit/Transactions |
| E1/E2/E3/E4 | KpiSummaryResponse | 7 KPI tổng hợp |
| E1/E2/E3/E4 | Sales per Sqft | Doanh thu/m² theo cửa hàng |
| E1/E2/E3/E4 | Budget vs Actual | So sánh ngân sách vs thực tế |
| D17 | Parquet snapshot (updated) | Cache cập nhật |

**Xử lý bên trong:**
1. Load DataFrame từ D17 (Parquet cache) hoặc rebuild từ D4+D6+D5
2. Apply RLS filter theo store_keys
3. Tính toán: YTD/MTD/Total + YoY Growth + MoM Growth
4. Group by month → Monthly trend (sales + profit)
5. Group by store → Store pie chart
6. Query D13 cho channel breakdown + KPI summary
7. Query D12 vs D4 cho Budget vs Actual attainment
8. Query D6 (SellingAreaSize) cho Sales per Sqft

---

### C.3.3. P3 — Phân tích Xu hướng Sản phẩm & Khách hàng

```
                                                ══ D4 ══ (summary_daily_sales)
                                               ╱
                                              ╱  ══ D5 ══ (DimProduct + SubCategory)
┌──────────────┐                             ╱
│ E1/E2/E3/E4  │    Năm / khoảng thời gian ╱    ══ D8 ══ (DimCustomer)
│ (Người dùng) │──────────────────────>┌───────────┐
│              │                       │    P3     │──── ══ D10 ══ (DimPromotion)
│              │<──────────────────────│ Phân tích │
│              │   Charts, tables,     │ Xu hướng  │──── ══ D6 ══ (DimStore + Geography)
│              │   segments            │ SP & KH   │
└──────────────┘                       └───────────┘──── ══ D14 ══ (agg_product_perf,
                                              ╲                    agg_inventory_metrics)
                                               ╲
                                                ══ D15 ══ (agg_customer_rfm,
                                                           customer_segments)
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1/E2/E3/E4 | selected_year (2007/2008/2009/ALL) | Năm lọc |
| D4 | summary_daily_sales | Doanh thu, số lượng theo ngày/sản phẩm |
| D5 | DimProduct + DimProductSubcategory + DimProductCategory | Thông tin sản phẩm, danh mục |
| D8 | DimCustomer | Thông tin khách hàng |
| D10 | DimPromotion | Thông tin khuyến mãi |
| D6 | DimStore + DimGeography | Vị trí địa lý |
| D14 | agg_product_performance | Phân loại ABC, revenue rank |
| D14 | agg_inventory_metrics | Turnover, GMROI, sell-through |
| D15 | agg_customer_rfm | RFM scores, segments |
| D15 | customer_segments | Phân khúc khách hàng |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1/E2/E3/E4 | Summary Stats | Tổng doanh thu, khách hàng, segment chủ lực |
| E1/E2/E3/E4 | Customer Segments | Phân khúc khách hàng RFM (biểu đồ) |
| E1/E2/E3/E4 | Trending Products | Top 10 sản phẩm bán chạy |
| E1/E2/E3/E4 | Promotion Impact | Tác động khuyến mãi × danh mục |
| E1/E2/E3/E4 | Sales by Location | Doanh thu theo quốc gia × quý |
| E1/E2/E3/E4 | Product Performance | Phân loại ABC + Top sản phẩm |
| E1/E2/E3/E4 | Inventory Metrics | Turnover, GMROI, Sell-Through |
| E1/E2/E3/E4 | RFM Segments Detail | 7 segments + metrics |
| E1/E2/E3/E4 | Stockout Rate | Tỷ lệ hết hàng + top products |
| E1/E2/E3/E4 | Safety Stock | Below/Near/Adequate |

**Xử lý bên trong (Cache TTL: 15 phút):**
1. Summary Stats: Query D4 (SUM revenue) + D8 (COUNT DISTINCT customers)
2. Customer Segments: Query D15 (customer_segments) → GROUP BY Segment
3. Trending Products: Query D4 JOIN D5 → GROUP BY ProductName → Top 10 by qty
4. Promotion Impact: Query D4 JOIN D10 JOIN D5 → GROUP BY PromotionName × Category
5. Sales by Location: Query D4 JOIN D6 → GROUP BY Country × Quarter → Top 5 countries
6. Product Performance: Query D14 (agg_product_performance) → ABC distribution + top products
7. Inventory Metrics: Query D14 (agg_inventory_metrics) JOIN D5 → Top 20 by turnover
8. RFM Segments: Query D15 (agg_customer_rfm) → GROUP BY rfm_segment → 7 segments
9. Stockout/Safety: Query D14 → WHERE inventory_turnover conditions

---

### C.3.4. P4 — Đánh giá Hiệu suất Nhân viên

```
                                                ══ D4 ══ (summary_daily_sales)
                                               ╱
                                              ╱  ══ D6 ══ (DimStore)
┌──────────────┐                             ╱
│ E1/E2/E3    │     year, month,            ╱    ══ D7 ══ (DimDate)
│ (Executive,  │     employee_key          ╱
│  RM, Admin)  │──────────────────────>┌───────────┐
│              │                       │    P4     │──── ══ D9 ══ (DimEmployee)
│              │<──────────────────────│ Đánh giá  │
│              │   KPIs, charts,       │ Hiệu suất │──── ══ D16 ══ (agg_store_monthly_costs)
│              │   leaderboard         │ Nhân viên │
└──────────────┘                       └───────────┘
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1/E2/E3 | year, month, employee_key, store_key | Bộ lọc |
| P1 | UserContext + RLS | Phân quyền |
| D4 | summary_daily_sales | Doanh thu, số lượng |
| D6 | DimStore | StoreManager, StoreName |
| D7 | DimDate | CalendarYear, MonthNumber |
| D9 | DimEmployee | EmployeeName, Title, Department |
| D16 | agg_store_monthly_costs | Total cost, return_amount per store/month |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1/E2/E3 | Dashboard KPIs | Net Sales, Profit Margin, Return Rate, Orders + comparison |
| E1/E2/E3 | Top Performer | Nhân viên xuất sắc nhất (name, title, metrics) |
| E1/E2/E3 | Trend Data | Monthly: net_sales + profit_margin over time |
| E1/E2/E3 | Leaderboard | Top 10 managers ranked |
| E1/E2/E3 | Scatter Data | Net Sales vs Profit Margin per manager |
| E1/E2/E3 | Capabilities | 6 assessment items (enabled/disabled + reason) |

**Xử lý bên trong (Cache TTL: 10 phút):**
1. Core query: JOIN D4 ↔ D6 ↔ D7 ↔ D16 GROUP BY StoreManager, Year, Month
2. Tính KPIs: net_sales = sales - returns, profit_margin = (sales - cost - returns) / sales, return_rate = returns / sales
3. Top Performer: MAX(net_sales) trong kỳ được lọc
4. Company Comparison: Tính trung bình toàn công ty → so sánh với employee được chọn
5. Trend: Group by month (không ảnh hưởng bởi month filter)
6. Leaderboard: ORDER BY net_sales DESC LIMIT top_n
7. Scatter: Mỗi row = 1 manager, X = net_sales, Y = profit_margin

---

### C.3.5. P5 — Dự báo Nhu cầu bằng AI

```
                                                ══ D4 ══ (summary_daily_sales)
                                               ╱
                                              ╱  ══ D2 ══ (FactSales + FactOnlineSales)
┌──────────────┐                             ╱
│ E1/E2        │    horizon_days,           ╱    ══ D5 ══ (DimProduct)
│ (Executive,  │    product_id,            ╱
│  Admin)      │    ABC/XYZ filters       ╱
│              │──────────────────────>┌───────────┐
│              │                       │    P5     │──── ══ D7 ══ (DimDate — IsHoliday)
│              │<──────────────────────│ Dự báo    │
│              │   Forecasts,          │ Nhu cầu   │──── ══ D17 ══ (Parquet cache)
│              │   alerts, overview    │ AI        │
└──────────────┘                       └───────────┘──── ══ D18 ══ (AI Model .pkl)
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1/E2 | horizon_days, product_id, abc_class, xyz_class | Tham số dự báo |
| D4 | summary_daily_sales | Dữ liệu bán hàng hàng ngày (build parquet) |
| D2 | FactSales + FactOnlineSales | Dữ liệu bán hàng gốc (fallback) |
| D5 | DimProduct | Tên sản phẩm, danh mục |
| D7 | DimDate | IsHoliday flag cho calendar features |
| D17 | daily_sales_snapshot.parquet, abc_xyz_snapshot.parquet | Cache dữ liệu |
| D18 | global_demand_model.pkl | Mô hình LightGBM đã train |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1/E2 | Overview | forecast_total_demand, sku_count, avg_daily_demand |
| E1/E2 | Alerts | SKU, product, ABC/XYZ class, spike_score |
| E1/E2 | Bulk Query | Danh sách sản phẩm theo bộ lọc + metrics |
| E1/E2 | Forecast Points | date, actual, predicted, upper_bound, lower_bound |
| D17 | Updated Parquet | Cache dự báo cập nhật |
| D18 | Updated Model | Mô hình retrain (nếu /recalculate) |

**Xử lý bên trong:**
1. **Cache Layer**: Load/build Parquet từ D4 (daily snapshot + ABC/XYZ classification)
2. **Feature Engineering**: Lag (7/14/30), Rolling (mean+std, window=7), Calendar (weekday/month/quarter/holiday)
3. **Prediction**: 3 LightGBM models (base + lower_CI + upper_CI) → Recursive multi-step
4. **ABC Classification**: A ≤ 80% cumulative revenue, B ≤ 95%, C còn lại
5. **XYZ Classification**: Dựa trên coefficient of variation (CV) của SalesQuantity
6. **Recalculate**: Retrain global model trên top 500 SKUs → Save to D18

---

### C.3.6. P6 — Quản trị Dữ liệu

```
                                                ══ D1-D16 ══ (Tất cả bảng DW)
                                               ╱
┌──────────────┐                              ╱
│ E1           │    File CSV, schema changes ╱    ══ D21 ══ (POS master data)
│ (Admin)      │──────────────────────>┌───────────┐
│              │                       │    P6     │──── ══ information_schema ══
│              │<──────────────────────│ Quản trị  │
│              │   DW health, uploads, │ Dữ liệu  │──── ══ schema_config.json ══
│              │   schema info         │           │
└──────────────┘                       └───────────┘──── ══ data_sources.json ══
                                              ╲
                                               ╲  ══ backups/ ══ (Backup files)
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1 | CSV/Excel files | File dữ liệu upload |
| E1 | Schema changes | Chỉnh sửa display_name, columns, descriptions |
| E1 | Purge requests | Table name, date range hoặc category |
| E1 | Data source configs | Connection info (host, port, user, password) |
| information_schema | Table metadata | Column names, types, row counts |
| schema_config.json | Schema definitions | Table display names, deletion strategies, columns |
| data_sources.json | Data source connections | POS connection info |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1 | DW Health Report | Bảng Fact/Dim/Agg, row counts |
| E1 | Upload Results | Rows inserted/updated, errors |
| E1 | Schema Info | Table schemas, column metadata |
| E1 | CSV Template | Template Excel cho import |
| D1-D16 | Inserted/Updated rows | Dữ liệu mới upload |
| backups/ | Backup data | Dữ liệu trước khi purge |

---

### C.3.7. P7 — ETL Pipeline

```
                                                ══ D19 ══ (POS: sales_orders, sales_order_items)
                                               ╱
┌──────────────┐                              ╱  ══ pos_change_log ══
│ E1 (Admin)   │──── Trigger ETL ─────>┌───────────┐
│              │                       │    P7     │──── ══ D2 ══ (FactSales, FactOnlineSales)
│              │<── ETL Status ────────│   ETL     │
└──────────────┘                       │ Pipeline  │──── ══ D3 ══ (v_total_sales)
                                       └───────────┘
┌──────────────┐                              ╲──── ══ D4 ══ (summary_daily_sales)
│ E5 (POS)     │── Giao dịch mới ─────────────╲
│              │                                ╲── ══ D7 ══ (DimDate — ensure)
└──────────────┘                                 ╲
                                                  ╲── ══ D13, D14, D15, D16 ══ (Tất cả bảng Aggregate)
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| E1 | Trigger command | Admin kích hoạt ETL (hoặc system startup) |
| E5 | Giao dịch POS | sales_orders + sales_order_items mới |
| D19 | POS transactions | Đơn hàng Completed/Returned |
| pos_change_log | Change log | Incremental sync indicator |
| D2 | FactSales + FactOnlineSales | Dữ liệu DW hiện có (cho aggregate) |
| D11 | FactInventory | Dữ liệu tồn kho (cho aggregate) |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| D2 | FactSales, FactOnlineSales | Giao dịch POS đã transform (REPLACE INTO) |
| D4 | summary_daily_sales | Cập nhật tổng hợp hàng ngày |
| D7 | DimDate | Đảm bảo DimDate cho ngày mới |
| D13 | agg_kpi_summary | 9 KPIs pre-computed |
| D13 | agg_channel_summary | Revenue/Profit per channel |
| D14 | agg_product_performance | ABC classification, revenue rank |
| D14 | agg_inventory_metrics | Turnover, GMROI, sell-through |
| D15 | agg_customer_rfm | RFM scoring → 7 segments |
| D16 | agg_store_monthly_costs | Store costs per month |
| E1 | ETL Status | Running, Completed, Error, Duration |

**Xử lý bên trong:**
1. **POS→DW Sync**: Extract (POS JOIN) → Transform (classify channel, calc metrics, key offset 10M) → Load (REPLACE INTO, batch 2000)
2. **Summary Refresh**: UPDATE summary_daily_sales cho POS data range
3. **Aggregate Rebuild**: Tạo lại 6 bảng aggregate từ Fact + Dim tables

---

### C.3.8. P8 — Giám sát Thời gian thực

```
┌──────────────┐                                         
│ E1/E2        │                                         
│ (Admin,      │<── SSE: Realtime data (mỗi 3s) ──┐     
│  Executive)  │                                   │     
└──────────────┘                                   │     
                                                   │     
                                              ┌───────────┐
                                              │    P8     │
                                              │ Giám sát  │
                                              │ Thời gian │
                                              │ thực      │
                                              └───────────┘
                                               ╱         ╲
                                              ╱           ╲
                                 ══ D20 ══                 ══ D21 ══
                          (realtime_daily_metrics,    (products, employees,
                           current_inventory)          stores, promotions)
```

**Luồng dữ liệu vào (Input):**
| Từ | Dữ liệu | Mô tả |
|----|----------|-------|
| D20 | realtime_daily_metrics | Pre-aggregated: revenue, cost, profit, orders per store/channel/day |
| D20 | current_inventory | Stock levels, reorder points |
| D21 | products, employees, stores, promotions | Master data cho enrich |

**Luồng dữ liệu ra (Output):**
| Đến | Dữ liệu | Mô tả |
|-----|----------|-------|
| E1/E2 | SSE Stream | today_revenue, today_cost, today_profit, today_orders, mtd_revenue, mtd_profit (mỗi 3 giây) |
| E1/E2 | Summary | Tổng kết ngày: revenue, cost, profit, orders + MTD |
| E1/E2 | Channels | InStore vs Online hôm nay |
| E1/E2 | Store Ranking | Top 20 stores by revenue hôm nay |
| E1/E2 | Trending Products | Top 10 sản phẩm hôm nay |
| E1/E2 | Employee Leaderboard | Xếp hạng nhân viên hôm nay |
| E1/E2 | Inventory Status | Stock levels + low-stock alerts |
| E1/E2 | 30-Day Trend | Revenue/Profit/Orders 30 ngày gần nhất |

**Xử lý bên trong (In-memory cache TTL: 10 giây):**
1. SSE Generator: Poll `realtime_daily_metrics` mỗi 3 giây
2. So sánh `last_updated` → Push chỉ khi có thay đổi
3. Các endpoint REST: Query POS DB → enrich từ master data → return JSON
4. `increment_metrics_for_order()`: O(1) UPSERT per order vào `realtime_daily_metrics`

---

## C.4. DFD Mức 1 — Sơ đồ tổng hợp

```
┌─────────────┐                                                         ┌─────────────┐
│ E1: Admin   │                                                         │ E5: POS     │
│             │                                                         │ System      │
└──────┬──────┘                                                         └──────┬──────┘
       │                                                                       │
       │ ┌─────── Credentials ─────────────────────── ┐                       │
       │ │                                             │                       │
       │ ▼                                             │                       │
       │  ╭────────╮   JWT + UserContext               │                       │
       ├─>│  P1    │──────────────────────────────────┼───────────────────────┤
       │  │ Xác    │                                   │                       │
       │  │ thực   │<── User data ────── ══ D1 ══     │                       │
       │  ╰────────╯                    (bi_users)     │                       │
       │       │                                       │                       │
       │       │ JWT Token (Bearer)                    │                       │
       │       ▼                                       │                       │
       │  ╭────────╮                                   │                       │
       ├─>│  P2    │<── ══ D4 ══ ── ══ D6 ═══ ── ══ D12 ══ ── ══ D13 ══     │
       │  │ Sales  │                                   │                       │
       │  │& Profit│──> Dashboard data to Users        │                       │
       │  ╰────────╯──> ══ D17 ══ (Parquet cache)     │                       │
       │       │                                       │                       │
       │  ╭────────╮                                   │                       │
       ├─>│  P3    │<── ══ D4 ══ ══ D5 ══ ══ D14 ══ ══ D15 ══               │
       │  │ Item   │                                   │                       │
       │  │ Trends │──> Charts & segments to Users     │                       │
       │  ╰────────╯                                   │                       │
       │       │                                       │                       │
       │  ╭────────╮                                   │                       │
       ├─>│  P4    │<── ══ D4 ══ ══ D6 ══ ══ D7 ══ ══ D9 ══ ══ D16 ══      │
       │  │Employee│                                   │                       │
       │  │ Perf.  │──> KPIs & leaderboard to Users    │                       │
       │  ╰────────╯                                   │                       │
       │       │                                       │                       │
       │  ╭────────╮                                   │                       │
       ├─>│  P5    │<── ══ D4 ══ ══ D5 ══ ══ D7 ══ ══ D17 ══ ══ D18 ══     │
       │  │  AI    │                                   │                       │
       │  │Forecast│──> Forecasts & alerts to Users    │                       │
       │  ╰────────╯──> ══ D17 ══ ══ D18 ══ (updated) │                       │
       │       │                                       │                       │
       │  ╭────────╮                                   │                       │
       ├─>│  P6    │<── ══ D1-D16 ══ ═ information_schema ═                  │
       │  │ Data   │                                   │                       │
       │  │ Mgmt   │──> DW health & upload results     │                       │
       │  ╰────────╯──> ══ D1-D16 ══ (insert/update)  │                       │
       │       │                                       │                       │
       │  ╭────────╮                                   │ POS transactions      │
       ├─>│  P7    │<── ══ D19 ══ ═════════════════════╪═══════════════<──────┤
       │  │  ETL   │                                   │                       │
       │  │Pipeline│──> ══ D2 ══ ══ D4 ══ ══ D13-D16 ══                      │
       │  ╰────────╯                                   │                       │
       │       │                                       │                       │
       │  ╭────────╮                                   │ POS realtime metrics  │
       └─>│  P8    │<── ══ D20 ══ ══ D21 ══ ══════════╪═══════════════<──────┘
          │Realtime│                                   │
          │Monitor │──> SSE stream + REST data to E1/E2│
          ╰────────╯                                   │
                                                       │
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│E2: Executive │  │E3: Regional  │  │E4: Store     │  │
│              │  │   Manager    │  │   Manager    │  │
└──────────────┘  └──────────────┘  └──────────────┘  │
    ▲                   ▲                  ▲           │
    │                   │                  │           │
    └───── Dashboard/Charts/Reports ───────┘           │
          (filtered by RBAC + RLS)                     │
```

---

## C.5. Hướng dẫn vẽ DFD Mức 1

### Cách vẽ:
1. **External Entities** (hình chữ nhật): Đặt ở viền ngoài sơ đồ — E1 (Admin), E2 (Executive), E3 (Regional Manager), E4 (Store Manager), E5 (POS System)
2. **Processes** (hình tròn): 8 tiến trình P1→P8 ở giữa sơ đồ
3. **Data Stores** (2 đường ngang): D1→D21 phân bổ xung quanh các process liên quan
4. **Data Flows** (mũi tên): Ghi nhãn dữ liệu cho mỗi mũi tên

### Mẹo quan trọng:
- Mỗi Process phải có ít nhất 1 input và 1 output
- Mỗi Data Store phải có ít nhất 1 luồng vào và 1 luồng ra
- Dữ liệu không được đi trực tiếp từ External Entity → Data Store (phải qua Process)
- Tên luồng dữ liệu nên ngắn gọn, rõ ràng (ví dụ: "JWT Token", "Doanh thu hàng ngày", "RFM scores")

---

## C.6. Bảng Ma trận Dữ liệu (Process × Data Store)

| | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 | D13 | D14 | D15 | D16 | D17 | D18 | D19 | D20 | D21 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **P1** | R | | | | | R | | | | | | | | | | | | | | | |
| **P2** | | | | R | R | R | | | | | | R | R | | | | RW | | | | |
| **P3** | | | | R | R | R | | R | | R | | | | R | R | | | | | | |
| **P4** | | | | R | | R | R | | R | | | | | | | R | | | | | |
| **P5** | | R | | R | R | | R | | | | | | | | | | RW | RW | | | |
| **P6** | RW | RW | | RW | RW | RW | RW | RW | RW | RW | RW | RW | RW | RW | RW | RW | | | | | |
| **P7** | | W | W | W | | | W | | | | R | | W | W | W | W | | | R | | |
| **P8** | | | | | | | | | | | | | | | | | | | | R | R |

> **R** = Read, **W** = Write, **RW** = Read & Write

---

# PHỤ LỤC

## PHỤ LỤC 1: Thống kê Database

### Database `retails_dataset` (Star Schema — Data Warehouse)

| Bảng | Loại | Số dòng | Mô tả |
|------|------|---------|-------|
| FactSales | Fact | 3,490,468 | Giao dịch bán hàng tại cửa hàng |
| FactOnlineSales | Fact | 12,711,440 | Giao dịch bán hàng online |
| FactInventory | Fact | 8,013,099 | Dữ liệu tồn kho |
| FactSalesQuota | Fact | 7,465,911 | Chỉ tiêu bán hàng |
| FactStrategyPlan | Fact | 2,750,628 | Kế hoạch chiến lược |
| summary_daily_sales | Aggregate | 3,449,574 | Tổng hợp bán hàng hàng ngày |
| agg_inventory_metrics | Aggregate | 600,241 | Chỉ số tồn kho aggregate |
| agg_product_performance | Aggregate | 2,232 | Hiệu suất sản phẩm + ABC |
| agg_customer_rfm | Aggregate | 21,569 | Phân tích RFM khách hàng |
| agg_store_monthly_costs | Aggregate | 11,978 | Chi phí cửa hàng theo tháng |
| agg_kpi_summary | Aggregate | 9 | KPIs pre-computed |
| agg_channel_summary | Aggregate | 2 | Offline vs Online summary |
| DimProduct | Dimension | 2,233 | Sản phẩm |
| DimStore | Dimension | 306 | Cửa hàng |
| DimCustomer | Dimension | 18,869 | Khách hàng |
| DimEmployee | Dimension | 293 | Nhân viên |
| DimDate | Dimension | 3,007 | Lịch (ngày/tháng/năm/quý) |
| DimGeography | Dimension | 674 | Địa lý |
| DimPromotion | Dimension | 28 | Khuyến mãi |
| DimProductCategory | Dimension | 8 | Danh mục sản phẩm |
| DimProductSubcategory | Dimension | 44 | Danh mục con |
| DimChannel | Dimension | 4 | Kênh bán hàng |
| DimCurrency | Dimension | 28 | Đơn vị tiền tệ |
| bi_users | Auth | 7 | Tài khoản người dùng |
| customer_segments | Segment | 18,869 | Phân khúc khách hàng |

### Database `pos_system` (POS Operational)

| Bảng | Số dòng | Mô tả |
|------|---------|-------|
| sales_orders | 11,526 | Đơn hàng POS |
| sales_order_items | 34,662 | Chi tiết đơn hàng POS |
| products | 500 | Sản phẩm POS |
| stores | 306 | Cửa hàng POS |
| employees | 293 | Nhân viên POS |
| customers | 5,000 | Khách hàng POS |
| current_inventory | 25,000 | Tồn kho hiện tại |
| promotions | 8 | Khuyến mãi POS |
| product_categories | 52 | Danh mục POS |
| inventory_movements | 7,000 | Biến động tồn kho |
| pos_change_log | 11,670 | Log thay đổi (incremental ETL) |
| realtime_daily_metrics | 95 | Metrics pre-aggregated hàng ngày |

## PHỤ LỤC 2: Tổng hợp API Endpoints

| # | Method | Endpoint | Module | Auth |
|---|--------|----------|--------|------|
| 1 | GET | `/` | main | No |
| 2 | GET | `/health` | main | No |
| 3 | POST | `/auth/login` | auth | No |
| 4 | GET | `/auth/me` | auth | Bearer |
| 5 | GET | `/auth/users` | auth | Admin |
| 6 | POST | `/auth/users` | auth | Admin |
| 7 | GET | `/sale-profit/api/dashboard/sales` | sale_profit | Bearer |
| 8 | GET | `/sale-profit/api/channels` | sale_profit | Bearer |
| 9 | GET | `/sale-profit/api/kpi-summary` | sale_profit | Bearer |
| 10 | GET | `/sale-profit/api/sales-per-sqft` | sale_profit | Bearer |
| 11 | GET | `/sale-profit/api/budget-vs-actual` | sale_profit | Bearer |
| 12 | POST | `/sale-profit/cache/refresh` | sale_profit | Bearer |
| 13 | GET | `/employee-performance/filters` | employee | Bearer |
| 14 | GET | `/employee-performance/dashboard` | employee | Bearer |
| 15 | GET | `/employee-performance/trend` | employee | Bearer |
| 16 | GET | `/employee-performance/leaderboard` | employee | Bearer |
| 17 | GET | `/employee-performance/scatter` | employee | Bearer |
| 18 | GET | `/trends/api/summary-stats` | analytics | No |
| 19 | GET | `/trends/api/customer-segments` | analytics | No |
| 20 | GET | `/trends/api/trending-products` | analytics | No |
| 21 | GET | `/trends/api/product-performance` | analytics | No |
| 22 | GET | `/trends/api/promotion-impact` | analytics | No |
| 23 | GET | `/trends/api/sales-by-location` | analytics | No |
| 24 | GET | `/trends/api/inventory-metrics` | analytics | No |
| 25 | GET | `/data/api/rfm-segments` | analytics | No |
| 26 | GET | `/data/api/stockout-rate` | analytics | No |
| 27 | GET | `/data/api/safety-stock` | analytics | No |
| 28 | GET | `/data/schema` | data_mgmt | No |
| 29 | POST | `/data/schema` | data_mgmt | No |
| 30 | POST | `/data/upload` | data_mgmt | No |
| 31 | POST | `/data/ingest` | data_mgmt | No |
| 32 | POST | `/data/purge` | data_mgmt | No |
| 33 | GET | `/data/dw-health` | data_mgmt | No |
| 34 | POST | `/data/csv-upload-preview` | data_mgmt | No |
| 35 | POST | `/data/csv-transform-load` | data_mgmt | No |
| 36 | GET | `/forecast/overview` | forecast | No |
| 37 | GET | `/forecast/alerts` | forecast | No |
| 38 | GET | `/forecast/bulk/query` | forecast | No |
| 39 | GET | `/forecast/forecast/{product_id}` | forecast | No |
| 40 | POST | `/forecast/recalculate` | forecast | No |
| 41 | GET | `/realtime/stream` | realtime (SSE) | No |
| 42 | GET | `/realtime/summary` | realtime | No |

---

*Tài liệu này cung cấp đầy đủ nội dung để thiết kế và vẽ 3 loại sơ đồ (Use Case, Sequence, DFD) ở mức 1 cho hệ thống BI Dashboard. Sử dụng các công cụ như draw.io, Lucidchart, Visual Paradigm hoặc PlantUML để vẽ sơ đồ chính thức.*
