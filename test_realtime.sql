-- ═══════════════════════════════════════════════════════════════════
-- TEST REALTIME UPDATE - BI Dashboard
-- ═══════════════════════════════════════════════════════════════════
-- Mục đích: Kiểm tra cơ chế cập nhật thời gian thực (near-real-time)
-- 
-- Cách dùng:
--   1. Mở BI Dashboard frontend (http://localhost:3000/dashboard)
--   2. Đảm bảo backend đang chạy (http://localhost:8000)
--   3. Mở MySQL client kết nối vào pos_system
--   4. Chạy từng bước bên dưới và quan sát dashboard thay đổi
--
-- Cơ chế hoạt động:
--   - Backend SSE endpoint /realtime/stream push dữ liệu mỗi 3 giây
--   - Cache TTL = 10 giây → sau 10 giây dữ liệu mới sẽ được đọc từ DB
--   - Frontend nhận SSE → tự động cập nhật panel "Today Live"
-- ═══════════════════════════════════════════════════════════════════

USE pos_system;

-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 0: Xem dữ liệu TRƯỚC KHI thay đổi
-- ═══════════════════════════════════════════════════════════════════

-- Xem metrics hiện tại của ngày hôm nay
SELECT * FROM realtime_daily_metrics 
WHERE metric_date = CURDATE() AND store_id = 0 AND channel = 'ALL';

-- Đếm số đơn hàng hôm nay
SELECT COUNT(*) AS orders_today 
FROM sales_orders 
WHERE DATE(order_date) = CURDATE() AND status = 'Completed';

-- Ghi lại giá trị hiện tại để so sánh
SELECT 
    COALESCE(today_revenue, 0) AS revenue_TRUOC,
    COALESCE(today_orders, 0) AS orders_TRUOC,
    COALESCE(today_items_sold, 0) AS items_TRUOC
FROM realtime_daily_metrics
WHERE metric_date = CURDATE() AND store_id = 0 AND channel = 'ALL';


-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 1: Tạo 1 đơn hàng MỚI vào bảng sales_orders
-- (Giả lập khách hàng mua hàng tại cửa hàng)
-- ═══════════════════════════════════════════════════════════════════

-- Lấy max order_id hiện tại
SET @max_order_id = (SELECT COALESCE(MAX(order_id), 0) FROM sales_orders);
SET @new_order_id = @max_order_id + 1;
SET @max_item_id = (SELECT COALESCE(MAX(item_id), 0) FROM sales_order_items);

-- Tạo đơn hàng mới - NGÀY HÔM NAY
INSERT INTO sales_orders 
    (order_id, order_number, order_date, customer_id, store_id, employee_id, 
     channel, promotion_id, status, total_amount, discount_amount, tax_amount, net_amount)
VALUES 
    (@new_order_id, 
     CONCAT('TEST-RT-', DATE_FORMAT(NOW(), '%H%i%s')),
     NOW(),                              -- Ngày hiện tại
     1,                                  -- customer_id = 1
     1,                                  -- store_id = 1  
     1,                                  -- employee_id = 1
     'InStore',                          -- Kênh bán: tại cửa hàng
     1,                                  -- promotion_id = 1 (No Promotion)
     'Completed',                        -- Đơn hàng hoàn thành
     250.00,                             -- Tổng tiền
     0.00,                               -- Giảm giá
     25.00,                              -- Thuế
     275.00                              -- Tiền thu
    );

-- Thêm 2 sản phẩm vào đơn hàng
INSERT INTO sales_order_items 
    (item_id, order_id, product_id, quantity, unit_price, unit_cost, discount_pct, line_total)
VALUES 
    (@max_item_id + 1, @new_order_id, 1, 3, 50.00, 30.00, 0, 150.00),
    (@max_item_id + 2, @new_order_id, 2, 2, 50.00, 25.00, 0, 100.00);

SELECT 'ĐÃ TẠO ĐƠN HÀNG TEST #1' AS status, @new_order_id AS order_id;


-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 2: Cập nhật bảng realtime_daily_metrics 
-- (Mô phỏng trigger/increment khi có đơn hàng mới)
-- ═══════════════════════════════════════════════════════════════════

-- Cập nhật dòng tổng hợp (store_id=0, channel='ALL')
INSERT INTO realtime_daily_metrics 
    (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
     today_orders, today_items_sold, today_discount, updated_at)
VALUES 
    (CURDATE(), 0, 'ALL', 250.00, 140.00, 110.00, 1, 5, 0, NOW())
ON DUPLICATE KEY UPDATE
    today_revenue = today_revenue + 250.00,
    today_cost = today_cost + 140.00,
    today_profit = today_profit + 110.00,
    today_orders = today_orders + 1,
    today_items_sold = today_items_sold + 5,
    updated_at = NOW();

-- Cập nhật theo channel 'InStore'
INSERT INTO realtime_daily_metrics 
    (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
     today_orders, today_items_sold, today_discount, updated_at)
VALUES 
    (CURDATE(), 0, 'InStore', 250.00, 140.00, 110.00, 1, 5, 0, NOW())
ON DUPLICATE KEY UPDATE
    today_revenue = today_revenue + 250.00,
    today_cost = today_cost + 140.00,
    today_profit = today_profit + 110.00,
    today_orders = today_orders + 1,
    today_items_sold = today_items_sold + 5,
    updated_at = NOW();

-- Cập nhật theo store_id = 1
INSERT INTO realtime_daily_metrics 
    (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
     today_orders, today_items_sold, today_discount, updated_at)
VALUES 
    (CURDATE(), 1, 'ALL', 250.00, 140.00, 110.00, 1, 5, 0, NOW())
ON DUPLICATE KEY UPDATE
    today_revenue = today_revenue + 250.00,
    today_cost = today_cost + 140.00,
    today_profit = today_profit + 110.00,
    today_orders = today_orders + 1,
    today_items_sold = today_items_sold + 5,
    updated_at = NOW();

SELECT 'ĐÃ CẬP NHẬT realtime_daily_metrics' AS status;


-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 3: KIỂM TRA - Xem dữ liệu SAU KHI thay đổi
-- (Chờ ~10 giây rồi xem Dashboard frontend tự cập nhật)
-- ═══════════════════════════════════════════════════════════════════

SELECT 
    COALESCE(today_revenue, 0) AS revenue_SAU,
    COALESCE(today_orders, 0) AS orders_SAU,
    COALESCE(today_items_sold, 0) AS items_SAU,
    updated_at AS last_updated
FROM realtime_daily_metrics
WHERE metric_date = CURDATE() AND store_id = 0 AND channel = 'ALL';


-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 4: Thêm ĐƠN HÀNG THỨ 2 (Online) để thấy rõ sự thay đổi
-- ═══════════════════════════════════════════════════════════════════

SET @max_order_id2 = (SELECT COALESCE(MAX(order_id), 0) FROM sales_orders);
SET @new_order_id2 = @max_order_id2 + 1;
SET @max_item_id2 = (SELECT COALESCE(MAX(item_id), 0) FROM sales_order_items);

INSERT INTO sales_orders 
    (order_id, order_number, order_date, customer_id, store_id, employee_id,
     channel, promotion_id, status, total_amount, discount_amount, tax_amount, net_amount)
VALUES 
    (@new_order_id2, 
     CONCAT('TEST-RT2-', DATE_FORMAT(NOW(), '%H%i%s')),
     NOW(), 2, 1, 2, 'Online', 1, 'Completed',
     500.00, 50.00, 45.00, 495.00);

INSERT INTO sales_order_items 
    (item_id, order_id, product_id, quantity, unit_price, unit_cost, discount_pct, line_total)
VALUES 
    (@max_item_id2 + 1, @new_order_id2, 3, 5, 60.00, 35.00, 10, 270.00),
    (@max_item_id2 + 2, @new_order_id2, 4, 4, 57.50, 30.00, 10, 230.00);

-- Cập nhật metrics cho đơn Online
INSERT INTO realtime_daily_metrics 
    (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
     today_orders, today_items_sold, today_discount, updated_at)
VALUES 
    (CURDATE(), 0, 'ALL', 500.00, 295.00, 205.00, 1, 9, 50.00, NOW())
ON DUPLICATE KEY UPDATE
    today_revenue = today_revenue + 500.00,
    today_cost = today_cost + 295.00,
    today_profit = today_profit + 205.00,
    today_orders = today_orders + 1,
    today_items_sold = today_items_sold + 9,
    today_discount = today_discount + 50.00,
    updated_at = NOW();

INSERT INTO realtime_daily_metrics 
    (metric_date, store_id, channel, today_revenue, today_cost, today_profit,
     today_orders, today_items_sold, today_discount, updated_at)
VALUES 
    (CURDATE(), 0, 'Online', 500.00, 295.00, 205.00, 1, 9, 50.00, NOW())
ON DUPLICATE KEY UPDATE
    today_revenue = today_revenue + 500.00,
    today_cost = today_cost + 295.00,
    today_profit = today_profit + 205.00,
    today_orders = today_orders + 1,
    today_items_sold = today_items_sold + 9,
    today_discount = today_discount + 50.00,
    updated_at = NOW();

SELECT 'ĐÃ TẠO ĐƠN HÀNG ONLINE #2 + CẬP NHẬT METRICS' AS status;


-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 5: Kiểm tra kết quả cuối cùng
-- ═══════════════════════════════════════════════════════════════════

-- Tổng hợp hôm nay
SELECT 
    metric_date, store_id, channel,
    today_revenue, today_cost, today_profit,
    today_orders, today_items_sold, today_discount,
    updated_at
FROM realtime_daily_metrics
WHERE metric_date = CURDATE()
ORDER BY store_id, channel;

-- Kiểm tra đơn hàng test
SELECT order_id, order_number, order_date, channel, status, total_amount
FROM sales_orders
WHERE order_number LIKE 'TEST-RT%'
ORDER BY order_id DESC;


-- ═══════════════════════════════════════════════════════════════════
-- BƯỚC 6 (OPTIONAL): Bạn cũng có thể invalidate cache qua API
-- Mở terminal/browser và gọi:
--   curl -X POST http://localhost:8000/realtime/cache/invalidate
-- Điều này sẽ buộc backend đọc lại DB ngay lập tức
-- ═══════════════════════════════════════════════════════════════════


-- ═══════════════════════════════════════════════════════════════════
-- DỌN DẸP: Xóa dữ liệu test (chạy khi test xong)
-- ═══════════════════════════════════════════════════════════════════
/*
-- Bỏ comment block này để chạy dọn dẹp:

DELETE soi FROM sales_order_items soi
JOIN sales_orders so ON so.order_id = soi.order_id
WHERE so.order_number LIKE 'TEST-RT%';

DELETE FROM sales_orders WHERE order_number LIKE 'TEST-RT%';

-- Khôi phục lại metrics (trừ đi giá trị đã cộng thêm: 250+500=750 revenue, etc.)
UPDATE realtime_daily_metrics SET
    today_revenue = GREATEST(today_revenue - 750.00, 0),
    today_cost = GREATEST(today_cost - 435.00, 0),
    today_profit = GREATEST(today_profit - 315.00, 0),
    today_orders = GREATEST(today_orders - 2, 0),
    today_items_sold = GREATEST(today_items_sold - 14, 0),
    today_discount = GREATEST(today_discount - 50.00, 0),
    updated_at = NOW()
WHERE metric_date = CURDATE() AND store_id = 0 AND channel = 'ALL';

SELECT 'ĐÃ DỌN DẸP DỮ LIỆU TEST' AS status;
*/
