"""
Invoice Simulator for BI Dashboard.

Tự động tạo hóa đơn ngẫu nhiên (FactSales hoặc FactOnlineSales),
đóng gói thành JSON và gửi tới Backend BI Dashboard qua URL + API Key.

Cách dùng:
    python invoice_simulator.py [--count N] [--url URL] [--api-key KEY]

Mặc định:
    --count   10            (số hóa đơn mỗi lần gửi)
    --url     http://127.0.0.1:8000/realtime/ingest
    --api-key bi-dashboard-ingest-key-2026
"""

import argparse
import json
import random
import string
import sys
from datetime import date
from typing import Any, Dict, List

import requests
import sqlalchemy
from sqlalchemy import create_engine, text

# ── Cấu hình kết nối local MySQL ──────────────────────────────
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "12345"
DB_NAME = "retails_dataset"

BACKEND_URL = "http://127.0.0.1:8000/realtime/ingest"
API_KEY = "bi-dashboard-ingest-key-2026"


def _get_engine():
    url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})


def _fetch_valid_keys(engine) -> Dict[str, List[int]]:
    """Lấy danh sách khóa hợp lệ từ các bảng Dimension."""
    keys: Dict[str, List[int]] = {}
    tables_cols = {
        "product_keys":    ("DimProduct",    "ProductKey"),
        "store_keys":      ("DimStore",      "StoreKey"),
        "employee_keys":   ("DimEmployee",   "EmployeeKey"),
        "promotion_keys":  ("DimPromotion",  "PromotionKey"),
        "currency_keys":   ("DimCurrency",   "CurrencyKey"),
        "customer_keys":   ("DimCustomer",   "CustomerKey"),
    }
    with engine.connect() as conn:
        for key_name, (table, col) in tables_cols.items():
            try:
                rows = conn.execute(
                    text(f"SELECT DISTINCT {col} FROM {table} ORDER BY RAND() LIMIT 200")
                ).fetchall()
                keys[key_name] = [int(r[0]) for r in rows if r[0] is not None]
            except Exception:
                keys[key_name] = []
    # Fallback: nếu bảng rỗng, dùng giá trị mặc định
    if not keys.get("product_keys"):
        keys["product_keys"] = list(range(1, 51))
    if not keys.get("store_keys"):
        keys["store_keys"] = list(range(1, 11))
    if not keys.get("promotion_keys"):
        keys["promotion_keys"] = [1]
    if not keys.get("currency_keys"):
        keys["currency_keys"] = [1]
    if not keys.get("customer_keys"):
        keys["customer_keys"] = list(range(1, 101))
    return keys


def _random_date() -> str:
    """Trả về ngày hôm nay."""
    return date.today().isoformat()


def _random_order_number() -> str:
    suffix = "".join(random.choices(string.digits, k=8))
    return f"SIM-{suffix}"


def generate_offline_invoice(keys: Dict[str, List[int]]) -> Dict[str, Any]:
    """Tạo một hóa đơn FactSales ngẫu nhiên."""
    unit_cost = round(random.uniform(5.0, 200.0), 2)
    unit_price = round(unit_cost * random.uniform(1.1, 2.5), 2)
    qty = random.randint(1, 20)
    disc_pct = random.choice([0, 0, 0, 5, 10, 15, 20])
    disc_amt = round(unit_price * qty * disc_pct / 100, 2)
    sales_amt = round(unit_price * qty - disc_amt, 2)
    total_cost = round(unit_cost * qty, 2)

    is_return = random.random() < 0.05  # 5% xác suất là đơn hoàn trả
    return_qty = qty if is_return else 0
    return_amt = round(sales_amt, 2) if is_return else 0.0

    return {
        "type":             "offline",
        "DateKey":          _random_date(),
        "channelKey":       1,
        "StoreKey":         random.choice(keys["store_keys"]),
        "ProductKey":       random.choice(keys["product_keys"]),
        "PromotionKey":     random.choice(keys["promotion_keys"]),
        "CurrencyKey":      random.choice(keys["currency_keys"]),
        "UnitCost":         unit_cost,
        "UnitPrice":        unit_price,
        "SalesQuantity":    0 if is_return else qty,
        "ReturnQuantity":   return_qty,
        "ReturnAmount":     return_amt,
        "DiscountQuantity": 0,
        "DiscountAmount":   disc_amt,
        "SalesAmount":      0.0 if is_return else sales_amt,
        "TotalCost":        total_cost,
    }


def generate_online_invoice(keys: Dict[str, List[int]]) -> Dict[str, Any]:
    """Tạo một hóa đơn FactOnlineSales ngẫu nhiên."""
    unit_cost = round(random.uniform(5.0, 200.0), 2)
    unit_price = round(unit_cost * random.uniform(1.1, 2.8), 2)
    qty = random.randint(1, 10)
    disc_amt = round(unit_price * qty * random.choice([0, 0, 0.05, 0.1, 0.2]), 2)
    sales_amt = round(unit_price * qty - disc_amt, 2)
    total_cost = round(unit_cost * qty, 2)

    is_return = random.random() < 0.05
    return_qty = qty if is_return else 0
    return_amt = round(sales_amt, 2) if is_return else 0.0

    order_no = _random_order_number()
    return {
        "type":                  "online",
        "DateKey":               _random_date(),
        "StoreKey":              random.choice(keys["store_keys"]) if keys["store_keys"] else 1,
        "ProductKey":            random.choice(keys["product_keys"]),
        "PromotionKey":          random.choice(keys["promotion_keys"]),
        "CurrencyKey":           random.choice(keys["currency_keys"]),
        "CustomerKey":           random.choice(keys["customer_keys"]) if keys["customer_keys"] else 1,
        "SalesOrderNumber":      order_no,
        "SalesOrderLineNumber":  1,
        "SalesQuantity":         0 if is_return else qty,
        "SalesAmount":           0.0 if is_return else sales_amt,
        "ReturnQuantity":        return_qty,
        "ReturnAmount":          return_amt,
        "DiscountQuantity":      0,
        "DiscountAmount":        disc_amt,
        "TotalCost":             total_cost,
        "UnitCost":              unit_cost,
        "UnitPrice":             unit_price,
    }


def generate_invoices(count: int, keys: Dict[str, List[int]]) -> List[Dict[str, Any]]:
    """Tạo danh sách hóa đơn ngẫu nhiên (offline hoặc online)."""
    invoices = []
    for _ in range(count):
        if random.random() < 0.6:  # 60% offline, 40% online
            invoices.append(generate_offline_invoice(keys))
        else:
            invoices.append(generate_online_invoice(keys))
    return invoices


def send_invoices(invoices: List[Dict[str, Any]], url: str, api_key: str) -> None:
    """Đóng gói JSON và gửi tới backend BI Dashboard."""
    payload = {"invoices": invoices}
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }

    print(f"\n→ Gửi {len(invoices)} hóa đơn tới: {url}")
    print(f"  Offline: {sum(1 for i in invoices if i['type'] == 'offline')}")
    print(f"  Online:  {sum(1 for i in invoices if i['type'] == 'online')}")

    import time as _time
    MAX_CLIENT_RETRIES = 5
    for attempt in range(MAX_CLIENT_RETRIES):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code == 503:
                wait = 15 * (attempt + 1)
                print(f"  Server bận (ETL đang chạy), thử lại sau {wait}s... (lần {attempt+1}/{MAX_CLIENT_RETRIES})")
                _time.sleep(wait)
                continue
            resp.raise_for_status()
            result = resp.json()
            print(f"\n✓ Thành công!")
            print(f"  Đã lưu offline (FactSales):       {result.get('inserted_offline', 0)}")
            print(f"  Đã lưu online (FactOnlineSales):  {result.get('inserted_online', 0)}")
            if result.get("errors"):
                print(f"  Lỗi: {result['errors']}")
            return
        except requests.exceptions.ConnectionError:
            print(f"\n✗ Không thể kết nối tới backend: {url}")
            print("  Hãy đảm bảo backend đang chạy: cd backend && python main.py")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            print(f"\n✗ HTTP Error {resp.status_code}: {resp.text}")
            sys.exit(1)
        except Exception as e:
            print(f"\n✗ Lỗi: {e}")
            sys.exit(1)
    print(f"\n✗ Không thể gửi sau {MAX_CLIENT_RETRIES} lần thử (server bận).")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="BI Dashboard Invoice Simulator")
    parser.add_argument("--count",   type=int, default=10,
                        help="Số hóa đơn cần tạo (mặc định: 10)")
    parser.add_argument("--url",     type=str, default=BACKEND_URL,
                        help=f"URL backend nhận invoice (mặc định: {BACKEND_URL})")
    parser.add_argument("--api-key", type=str, default=API_KEY,
                        help="API Key xác thực")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ in JSON ra màn hình, không gửi lên backend")
    args = parser.parse_args()

    print("=== BI Dashboard Invoice Simulator ===")
    print(f"Đang lấy danh sách khóa hợp lệ từ {DB_NAME}@{DB_HOST}:{DB_PORT}...")

    try:
        engine = _get_engine()
        keys = _fetch_valid_keys(engine)
        engine.dispose()
    except Exception as e:
        print(f"✗ Không thể kết nối database local: {e}")
        print(f"  Kiểm tra MySQL đang chạy và database '{DB_NAME}' tồn tại.")
        sys.exit(1)

    print(f"  ProductKey: {len(keys['product_keys'])} | StoreKey: {len(keys['store_keys'])} "
          f"| CustomerKey: {len(keys['customer_keys'])}")

    invoices = generate_invoices(args.count, keys)

    if args.dry_run:
        print(f"\n--- DRY RUN: {len(invoices)} hóa đơn ---")
        print(json.dumps({"invoices": invoices}, ensure_ascii=False, indent=2))
        return

    send_invoices(invoices, args.url, args.api_key)


if __name__ == "__main__":
    main()
