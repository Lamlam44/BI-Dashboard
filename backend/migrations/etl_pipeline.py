"""
ETL Pipeline: Extract from POS System â†’ Transform â†’ Load into BI Data Warehouse.

This module demonstrates a realistic ETL flow from a normalized operational
database (pos_system) into the star-schema BI warehouse (retails_dataset).

New aggregate tables created:
  - agg_inventory_metrics    (Inventory Turnover, GMROI, Sell-Through Rate)
  - agg_product_performance  (Product-level ABC classification, revenue rank)
  - agg_customer_rfm         (RFM segmentation scores)
  - agg_kpi_summary          (Pre-computed retail KPIs for dashboard)
"""

import logging
import threading
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from core.config import DW_HOST, DW_PORT, DW_USER, DW_PASSWORD, DW_DATABASE

logger = logging.getLogger(__name__)

# Prevents two threads (startup ETL + periodic ETL) from running
# create_aggregate_tables() simultaneously — DDL race conditions on temp tables.
_AGG_LOCK = threading.Lock()


def _dw_url():
    return f"mysql+pymysql://{DW_USER}:{DW_PASSWORD}@{DW_HOST}:{DW_PORT}/{DW_DATABASE}?charset=utf8mb4"


def create_aggregate_tables(force: bool = False):
    """Incrementally update aggregate / KPI tables in the BI Data Warehouse.

    On the first run (or force=True) every table is built from scratch.
    On subsequent runs only rows added since the last successful run are
    processed, so ETL finishes in seconds/minutes instead of 30-60 min.

    High-water marks are stored in ``_etl_watermarks`` (auto-created).

    Args:
        force: If True, reset watermarks and rebuild everything from scratch.
    """
    if not _AGG_LOCK.acquire(blocking=False):
        logger.info("create_aggregate_tables: another run in progress, skipping.")
        return
    try:
        _run_aggregate_tables(force)
    finally:
        _AGG_LOCK.release()


def _run_aggregate_tables(force: bool = False):
    """Internal: actual implementation of create_aggregate_tables."""
    from core.database import CONNECT_ARGS as _DW_CONNECT_ARGS
    # NullPool: khong giu connection, tranh vuot qua gioi han 25 conn TiDB Cloud
    engine = create_engine(
        _dw_url(),
        poolclass=NullPool,
        connect_args={
            **_DW_CONNECT_ARGS,
            "connect_timeout": 30,
            "read_timeout":    900,
            "write_timeout":   900,
        },
    )

    def _table_has_data(conn, table_name: str) -> bool:
        try:
            row = conn.execute(text(f"SELECT COUNT(*) AS cnt FROM {table_name}")).mappings().first()
            return row and row["cnt"] > 0
        except Exception:
            return False

    def _get_wm(conn, tbl: str) -> int:
        try:
            row = conn.execute(
                text("SELECT last_key FROM _etl_watermarks WHERE table_name = :t"),
                {"t": tbl},
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _set_wm(conn, tbl: str, val: int) -> None:
        conn.execute(
            text("""
                INSERT INTO _etl_watermarks (table_name, last_key, updated_at)
                VALUES (:t, :v, NOW())
                ON DUPLICATE KEY UPDATE last_key = :v, updated_at = NOW()
            """),
            {"t": tbl, "v": int(val)},
        )

    # -- Phase 1: kiem tra du lieu moi, COMMIT watermarks truoc khi chay agg
    # Neu Phase 2 fail, watermarks da luu -> vong lap ke tiep khong loop lai 9M rows
    try:
        with engine.begin() as wm_conn:
            # â”€â”€ High-water mark table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            wm_conn.execute(text("""
                CREATE TABLE IF NOT EXISTS _etl_watermarks (
                    table_name  VARCHAR(64) PRIMARY KEY,
                    last_key    BIGINT      NOT NULL DEFAULT 0,
                    updated_at  DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))

            # â”€â”€ Current maximums in each fact table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            sales_max  = wm_conn.execute(text("SELECT COALESCE(MAX(SalesKey),0)      FROM FactSales")).scalar()      or 0
            inv_max    = wm_conn.execute(text("SELECT COALESCE(MAX(InventoryKey),0)   FROM FactInventory")).scalar()   or 0
            online_max = wm_conn.execute(text("SELECT COALESCE(MAX(OnlineSalesKey),0) FROM FactOnlineSales")).scalar() or 0

            sales_wm  = 0 if force else _get_wm(wm_conn, "FactSales")
            inv_wm    = 0 if force else _get_wm(wm_conn, "FactInventory")
            online_wm = 0 if force else _get_wm(wm_conn, "FactOnlineSales")

            new_sales  = int(sales_max)  > int(sales_wm)
            new_inv    = int(inv_max)    > int(inv_wm)
            new_online = int(online_max) > int(online_wm)

            if not (new_sales or new_inv or new_online):
                logger.info("ETL: không có dữ liệu mới kể từ lần chạy trước, bỏ qua.")
                engine.dispose()
                return

            logger.info(
                "ETL incremental: FactSales +%d | FactInventory +%d | FactOnlineSales +%d",
                int(sales_max) - int(sales_wm),
                int(inv_max)   - int(inv_wm),
                int(online_max) - int(online_wm),
            )

            # Commit watermarks truoc khi chay agg computation
            _set_wm(wm_conn, "FactSales",       int(sales_max))
            _set_wm(wm_conn, "FactInventory",   int(inv_max))
            _set_wm(wm_conn, "FactOnlineSales", int(online_max))
            logger.info(
                "ETL watermarks committed (pre-agg): FactSales=%d FactInventory=%d FactOnlineSales=%d",
                sales_max, inv_max, online_max,
            )
    except Exception as exc:
        logger.error("ETL phase 1 (watermark) failed: %s", exc)
        engine.dispose()
        return

    # -- Phase 2: tinh toan aggregate (NullPool -> connection moi)
    # Neu fail: watermarks da saved, vong lap ke tiep khong loop lai
    with engine.begin() as conn:

        # Boost timeouts - bo qua neu TiDB Cloud khong ho tro
        try:
            conn.execute(text("SET SESSION wait_timeout        = 86400"))   # 24 h
        except Exception:
            pass
        try:
            conn.execute(text("SET SESSION interactive_timeout = 86400"))   # 24 h
        except Exception:
            pass
        try:
            conn.execute(text("SET SESSION net_read_timeout    = 7200"))    # 2 h
        except Exception:
            pass
        try:
            conn.execute(text("SET SESSION net_write_timeout   = 7200"))    # 2 h
        except Exception:
            pass
        try:
            conn.execute(text("SET SESSION tmp_table_size      = 1073741824"))  # 1 GB
        except Exception:
            pass
        try:
            conn.execute(text("SET SESSION max_heap_table_size = 1073741824"))  # 1 GB
        except Exception:
            pass

        # ═══════════════════════════════════════════════════════════════
        # 1. agg_inventory_metrics
        #    Chiáº¿n lÆ°á»£c: xÃ¡c Ä‘á»‹nh cÃ¡c tá»• há»£p (product, store, month)
        #    bá»‹ áº£nh hÆ°á»Ÿng bá»Ÿi dá»¯ liá»‡u má»›i tá»« FactInventory HOáº¶C
        #    FactSales, sau Ä‘Ã³ tÃ­nh láº¡i ÄÃšNG cÃ¡c tá»• há»£p Ä‘Ã³ tá»« toÃ n
        #    bá»™ nguá»“n (Ä‘á»ƒ AVG chÃ­nh xÃ¡c).
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_inventory_metrics (
                product_key         BIGINT NOT NULL,
                store_key           BIGINT NOT NULL,
                period_month        VARCHAR(7) NOT NULL,
                avg_on_hand         DECIMAL(14,2) DEFAULT 0,
                total_sold          DECIMAL(14,2) DEFAULT 0,
                total_cost_sold     DECIMAL(14,2) DEFAULT 0,
                total_revenue       DECIMAL(14,2) DEFAULT 0,
                gross_profit        DECIMAL(14,2) DEFAULT 0,
                inventory_turnover  DECIMAL(10,4) DEFAULT 0,
                sell_through_rate   DECIMAL(10,4) DEFAULT 0,
                gmroi               DECIMAL(10,4) DEFAULT 0,
                days_of_supply      DECIMAL(10,2) DEFAULT 0,
                PRIMARY KEY (product_key, store_key, period_month)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if new_inv or new_sales or force or not _table_has_data(conn, "agg_inventory_metrics"):
            is_full_inv = force or not _table_has_data(conn, "agg_inventory_metrics")

            conn.execute(text("DROP TABLE IF EXISTS _tmp_new_combos"))
            conn.execute(text("DROP TABLE IF EXISTS _tmp_inv_agg"))
            conn.execute(text("DROP TABLE IF EXISTS _tmp_sales_agg"))

            if is_full_inv:
                # â”€â”€ Full rebuild: one store at a time using StoreKey index.
                #    Each store has ~25K rows in FactInventory â†’ fast GROUP BY.
                #    ~310 stores Ã— ~5s = ~26 min total (vs 7.8M-row full scans).
                stores_res = conn.execute(text(
                    "SELECT DISTINCT StoreKey FROM FactInventory ORDER BY StoreKey"
                )).fetchall()
                stores_list = [int(r[0]) for r in stores_res]
                logger.info("agg_inventory_metrics: rebuilding %d stores ...", len(stores_list))
                _store_sql = text("""
                    REPLACE INTO agg_inventory_metrics
                        (product_key, store_key, period_month,
                         avg_on_hand, total_sold, total_cost_sold, total_revenue,
                         gross_profit, inventory_turnover, sell_through_rate,
                         gmroi, days_of_supply)
                    SELECT
                        fi.ProductKey, fi.StoreKey,
                        fi.ym,
                        fi.avg_on_hand,
                        COALESCE(fs.total_qty, 0),
                        COALESCE(fs.total_cost, 0),
                        COALESCE(fs.total_revenue, 0),
                        COALESCE(fs.total_revenue, 0) - COALESCE(fs.total_cost, 0),
                        CASE WHEN fi.avg_inv_cost > 0
                             THEN COALESCE(fs.total_cost, 0) / fi.avg_inv_cost ELSE 0 END,
                        CASE WHEN (COALESCE(fs.total_qty,0) + fi.avg_on_hand) > 0
                             THEN COALESCE(fs.total_qty,0) /
                                  (COALESCE(fs.total_qty,0) + fi.avg_on_hand)
                             ELSE 0 END,
                        CASE WHEN fi.avg_inv_cost > 0
                             THEN (COALESCE(fs.total_revenue,0) - COALESCE(fs.total_cost,0))
                                  / fi.avg_inv_cost ELSE 0 END,
                        CASE WHEN COALESCE(fs.daily_avg_sold,0) > 0
                             THEN fi.avg_on_hand / fs.daily_avg_sold ELSE 0 END
                    FROM (
                        SELECT ProductKey, StoreKey,
                            CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0')) AS ym,
                            AVG(OnHandQuantity)              AS avg_on_hand,
                            AVG(OnHandQuantity * UnitCost)   AS avg_inv_cost
                        FROM FactInventory
                        WHERE StoreKey = :sk
                        GROUP BY ProductKey, StoreKey,
                                 CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0'))
                    ) fi
                    LEFT JOIN (
                        SELECT ProductKey, StoreKey,
                            CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0')) AS ym,
                            SUM(SalesQuantity) AS total_qty,
                            SUM(TotalCost)     AS total_cost,
                            SUM(SalesAmount)   AS total_revenue,
                            SUM(SalesQuantity) / NULLIF(COUNT(DISTINCT DateKey), 0)
                                AS daily_avg_sold
                        FROM FactSales
                        WHERE StoreKey = :sk
                        GROUP BY ProductKey, StoreKey,
                                 CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0'))
                    ) fs ON fs.ProductKey = fi.ProductKey
                          AND fs.StoreKey   = fi.StoreKey
                          AND fs.ym         = fi.ym
                """)
                for idx, sk in enumerate(stores_list):
                    with engine.begin() as mc:
                        mc.execute(text("SET SESSION net_read_timeout=7200, net_write_timeout=7200"))
                        mc.execute(_store_sql, {"sk": sk})
                    if (idx + 1) % 50 == 0:
                        logger.info("  agg_inventory_metrics: %d/%d stores done", idx + 1, len(stores_list))
                logger.info("agg_inventory_metrics: rebuilt %d stores", len(stores_list))
            else:
                # â”€â”€ Incremental: collect only affected (product, store, month)
                #    combos then re-aggregate. Temp-table JOIN approach.
                conn.execute(text(f"""
                    CREATE TABLE _tmp_new_combos AS
                    SELECT DISTINCT ProductKey, StoreKey,
                        CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0')) AS ym
                    FROM FactInventory WHERE InventoryKey > {int(inv_wm)}
                    UNION
                    SELECT DISTINCT ProductKey, StoreKey,
                        CONCAT(YEAR(DateKey),'-',LPAD(MONTH(DateKey),2,'0')) AS ym
                    FROM FactSales WHERE SalesKey > {int(sales_wm)}
                """))
                # Index skipped intentionally: delta tables are tiny (only new-since-
                # watermark rows), a full-scan nested-loop JOIN is faster than index overhead.

                conn.execute(text("""
                    CREATE TABLE _tmp_inv_agg AS
                    SELECT fi.ProductKey, fi.StoreKey,
                        CONCAT(YEAR(fi.DateKey),'-',LPAD(MONTH(fi.DateKey),2,'0')) AS ym,
                        AVG(fi.OnHandQuantity)              AS avg_on_hand,
                        AVG(fi.OnHandQuantity * fi.UnitCost) AS avg_inv_cost
                    FROM FactInventory fi
                    JOIN _tmp_new_combos nc
                      ON nc.ProductKey = fi.ProductKey
                     AND nc.StoreKey   = fi.StoreKey
                     AND nc.ym = CONCAT(YEAR(fi.DateKey),'-',LPAD(MONTH(fi.DateKey),2,'0'))
                    GROUP BY fi.ProductKey, fi.StoreKey,
                             CONCAT(YEAR(fi.DateKey),'-',LPAD(MONTH(fi.DateKey),2,'0'))
                """))
                logger.info("_tmp_inv_agg (partial) created")

                conn.execute(text("""
                    CREATE TABLE _tmp_sales_agg AS
                    SELECT fs.ProductKey, fs.StoreKey,
                        CONCAT(YEAR(fs.DateKey),'-',LPAD(MONTH(fs.DateKey),2,'0')) AS ym,
                        SUM(fs.SalesQuantity) AS total_qty,
                        SUM(fs.TotalCost)     AS total_cost,
                        SUM(fs.SalesAmount)   AS total_revenue,
                        SUM(fs.SalesQuantity) / NULLIF(COUNT(DISTINCT DATE(fs.DateKey)),0) AS daily_avg_sold
                    FROM FactSales fs
                    JOIN _tmp_new_combos nc
                      ON nc.ProductKey = fs.ProductKey
                     AND nc.StoreKey   = fs.StoreKey
                     AND nc.ym = CONCAT(YEAR(fs.DateKey),'-',LPAD(MONTH(fs.DateKey),2,'0'))
                    GROUP BY fs.ProductKey, fs.StoreKey,
                             CONCAT(YEAR(fs.DateKey),'-',LPAD(MONTH(fs.DateKey),2,'0'))
                """))
                logger.info("_tmp_sales_agg (partial) created")

                conn.execute(text("""
                    REPLACE INTO agg_inventory_metrics
                        (product_key, store_key, period_month,
                         avg_on_hand, total_sold, total_cost_sold, total_revenue, gross_profit,
                         inventory_turnover, sell_through_rate, gmroi, days_of_supply)
                    SELECT
                        inv.ProductKey, inv.StoreKey, inv.ym,
                        inv.avg_on_hand,
                        COALESCE(s.total_qty, 0),
                        COALESCE(s.total_cost, 0),
                        COALESCE(s.total_revenue, 0),
                        COALESCE(s.total_revenue, 0) - COALESCE(s.total_cost, 0),
                        CASE WHEN inv.avg_inv_cost > 0
                             THEN COALESCE(s.total_cost, 0) / inv.avg_inv_cost ELSE 0 END,
                        CASE WHEN (COALESCE(s.total_qty,0) + inv.avg_on_hand) > 0
                             THEN COALESCE(s.total_qty,0) / (COALESCE(s.total_qty,0) + inv.avg_on_hand)
                             ELSE 0 END,
                        CASE WHEN inv.avg_inv_cost > 0
                             THEN (COALESCE(s.total_revenue,0) - COALESCE(s.total_cost,0)) / inv.avg_inv_cost
                             ELSE 0 END,
                        CASE WHEN COALESCE(s.daily_avg_sold,0) > 0
                             THEN inv.avg_on_hand / s.daily_avg_sold ELSE 0 END
                    FROM _tmp_inv_agg inv
                    LEFT JOIN _tmp_sales_agg s
                      ON s.ProductKey = inv.ProductKey
                     AND s.StoreKey   = inv.StoreKey
                     AND s.ym         = inv.ym
                """))
                conn.execute(text("DROP TABLE IF EXISTS _tmp_new_combos"))
                conn.execute(text("DROP TABLE IF EXISTS _tmp_inv_agg"))
                conn.execute(text("DROP TABLE IF EXISTS _tmp_sales_agg"))
                logger.info("agg_inventory_metrics updated (affected combos only)")
        else:
            logger.info("agg_inventory_metrics: no new data, skipping")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # 2. agg_product_performance
        #    Rank vÃ  ABC class phá»¥ thuá»™c toÃ n bá»™ sáº£n pháº©m â†’ tÃ­nh láº¡i
        #    Ä‘áº§y Ä‘á»§ khi cÃ³ dá»¯ liá»‡u bÃ¡n hÃ ng má»›i, bá» qua náº¿u khÃ´ng.
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_product_performance (
                product_key         BIGINT PRIMARY KEY,
                product_name        VARCHAR(255),
                brand_name          VARCHAR(100),
                category_name       VARCHAR(100),
                subcategory_name    VARCHAR(100),
                total_revenue       DECIMAL(18,2) DEFAULT 0,
                total_quantity      DECIMAL(18,2) DEFAULT 0,
                total_cost          DECIMAL(18,2) DEFAULT 0,
                gross_profit        DECIMAL(18,2) DEFAULT 0,
                profit_margin       DECIMAL(10,4) DEFAULT 0,
                revenue_rank        INT DEFAULT 0,
                abc_class           CHAR(1) DEFAULT 'C',
                cumulative_pct      DECIMAL(10,4) DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if new_sales or force or not _table_has_data(conn, "agg_product_performance"):
            conn.execute(text("DELETE FROM agg_product_performance"))
            conn.execute(text("""
                INSERT INTO agg_product_performance
                    (product_key, product_name, brand_name, category_name, subcategory_name,
                     total_revenue, total_quantity, total_cost, gross_profit, profit_margin,
                     revenue_rank, abc_class, cumulative_pct)
                SELECT
                    p.ProductKey, p.ProductName, p.BrandName,
                    COALESCE(pc.ProductCategoryName, ''),
                    COALESCE(psc.ProductSubcategoryName, ''),
                    agg.total_revenue, agg.total_quantity, agg.total_cost,
                    agg.total_revenue - agg.total_cost,
                    CASE WHEN agg.total_revenue > 0
                         THEN (agg.total_revenue - agg.total_cost) / agg.total_revenue
                         ELSE 0 END,
                    RANK() OVER (ORDER BY agg.total_revenue DESC),
                    'C',
                    SUM(agg.total_revenue) OVER (ORDER BY agg.total_revenue DESC)
                        / SUM(agg.total_revenue) OVER ()
                FROM (
                    SELECT ProductKey,
                           SUM(SalesAmount)   AS total_revenue,
                           SUM(SalesQuantity) AS total_quantity,
                           SUM(TotalCost)     AS total_cost
                    FROM v_total_sales
                    GROUP BY ProductKey
                ) agg
                JOIN DimProduct p ON p.ProductKey = agg.ProductKey
                LEFT JOIN DimProductSubcategory psc
                  ON psc.ProductSubcategoryKey = p.ProductSubcategoryKey
                LEFT JOIN DimProductCategory pc
                  ON pc.ProductCategoryKey = psc.ProductCategoryKey
            """))
            conn.execute(text("""
                UPDATE agg_product_performance SET abc_class =
                    CASE WHEN cumulative_pct <= 0.80 THEN 'A'
                         WHEN cumulative_pct <= 0.95 THEN 'B'
                         ELSE 'C' END
            """))
            logger.info("agg_product_performance rebuilt")
        else:
            logger.info("agg_product_performance: no new sales, skipping")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # 3. agg_customer_rfm
        #    NTILE yÃªu cáº§u toÃ n bá»™ khÃ¡ch hÃ ng â†’ tÃ­nh láº¡i Ä‘áº§y Ä‘á»§,
        #    nhÆ°ng chá»‰ khi cÃ³ dá»¯ liá»‡u FactOnlineSales má»›i.
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_customer_rfm (
                customer_key    BIGINT PRIMARY KEY,
                last_order_date DATE,
                recency_days    INT DEFAULT 0,
                frequency       INT DEFAULT 0,
                monetary        DECIMAL(14,2) DEFAULT 0,
                r_score         TINYINT DEFAULT 1,
                f_score         TINYINT DEFAULT 1,
                m_score         TINYINT DEFAULT 1,
                rfm_segment     VARCHAR(30) DEFAULT 'Unknown'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if new_online or force or not _table_has_data(conn, "agg_customer_rfm"):
            conn.execute(text("DELETE FROM agg_customer_rfm"))
            conn.execute(text("""
                INSERT INTO agg_customer_rfm
                    (customer_key, last_order_date, recency_days, frequency, monetary,
                     r_score, f_score, m_score, rfm_segment)
                SELECT
                    base.CustomerKey, base.last_order_date, base.recency_days,
                    base.frequency, base.monetary,
                    base.r_score, base.f_score, base.m_score,
                    CASE
                        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champion'
                        WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal'
                        WHEN r_score >= 4 AND f_score <= 2                  THEN 'New Customer'
                        WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'At Risk'
                        WHEN r_score <= 2 AND f_score <= 2                  THEN 'Lost'
                        WHEN r_score >= 3 AND m_score >= 3                  THEN 'Potential Loyalist'
                        ELSE 'Need Attention'
                    END AS rfm_segment
                FROM (
                    SELECT rfm.*,
                        NTILE(5) OVER (ORDER BY recency_days ASC)  AS r_score,
                        NTILE(5) OVER (ORDER BY frequency ASC)     AS f_score,
                        NTILE(5) OVER (ORDER BY monetary ASC)      AS m_score
                    FROM (
                        SELECT CustomerKey,
                            MAX(DATE(DateKey)) AS last_order_date,
                            DATEDIFF(
                                (SELECT MAX(DATE(DateKey)) FROM FactOnlineSales),
                                MAX(DATE(DateKey))
                            ) AS recency_days,
                            COUNT(DISTINCT SalesOrderNumber) AS frequency,
                            SUM(SalesAmount) AS monetary
                        FROM FactOnlineSales
                        WHERE CustomerKey IS NOT NULL
                        GROUP BY CustomerKey
                    ) rfm
                ) base
            """))
            logger.info("agg_customer_rfm rebuilt")
        else:
            logger.info("agg_customer_rfm: no new online sales, skipping")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # 4. agg_kpi_summary
        #    TÃ­nh láº¡i Ä‘áº§y Ä‘á»§ (query Ä‘Æ¡n giáº£n, khÃ´ng tá»‘n nhiá»u thá»i
        #    gian) chá»‰ khi cÃ³ dá»¯ liá»‡u má»›i.
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_kpi_summary (
                kpi_key     VARCHAR(50) PRIMARY KEY,
                kpi_label   VARCHAR(100),
                kpi_value   DECIMAL(18,4) DEFAULT 0,
                kpi_unit    VARCHAR(20) DEFAULT '',
                period      VARCHAR(20) DEFAULT 'ALL',
                computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if new_sales or new_online or force or not _table_has_data(conn, "agg_kpi_summary"):
            # Use REPLACE INTO (upsert by kpi_key PK) — never DELETE first so stale
            # data is preserved if any individual query below fails (e.g. lock timeout).
            conn.execute(text("DROP TABLE IF EXISTS _tmp_kpi_agg"))
            conn.execute(text("""
                CREATE TABLE _tmp_kpi_agg AS
                SELECT COUNT(*)           AS cnt,
                       SUM(SalesAmount)   AS sum_amt,
                       SUM(TotalCost)     AS sum_cost,
                       AVG(SalesAmount)   AS avg_amt,
                       AVG(SalesQuantity) AS avg_qty
                FROM v_total_sales
            """))
            logger.info("_tmp_kpi_agg created (single scan of v_total_sales)")
            conn.execute(text("""
                REPLACE INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'total_revenue','Total Revenue',sum_amt,'USD','ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'total_transactions','Total Transactions',cnt,'count','ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'avg_transaction_value','Average Transaction Value',avg_amt,'USD','ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'avg_basket_size','Average Basket Size',avg_qty,'units','ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'gross_margin','Gross Profit Margin',
                       CASE WHEN sum_amt>0 THEN (sum_amt-sum_cost)/sum_amt*100 ELSE 0 END,
                       'pct','ALL'
                FROM _tmp_kpi_agg
            """))
            conn.execute(text("DROP TABLE IF EXISTS _tmp_kpi_agg"))
            conn.execute(text("""
                REPLACE INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'active_stores','Active Stores',COUNT(DISTINCT StoreKey),'count','ALL'
                FROM DimStore WHERE Status = 'On'
            """))
            conn.execute(text("""
                REPLACE INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'product_count','Product Count',COUNT(*),'count','ALL' FROM DimProduct
            """))
            conn.execute(text("""
                REPLACE INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'unique_customers','Unique Customers',
                       COUNT(DISTINCT CustomerKey),'count','ALL'
                FROM FactOnlineSales WHERE CustomerKey IS NOT NULL
            """))
            conn.execute(text("""
                REPLACE INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'avg_inventory_turnover','Avg Inventory Turnover',
                       AVG(inventory_turnover),'ratio','ALL'
                FROM agg_inventory_metrics WHERE inventory_turnover > 0
            """))
            logger.info("agg_kpi_summary updated")
        else:
            logger.info("agg_kpi_summary: no new data, skipping")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # 5. agg_store_monthly_costs
        #    True incremental: cá»™ng dá»“n delta tá»« cÃ¡c dÃ²ng FactSales
        #    má»›i vÃ o cÃ¡c thÃ¡ng Ä‘Ã£ cÃ³, táº¡o thÃ¡ng má»›i náº¿u chÆ°a tá»“n táº¡i.
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_store_monthly_costs (
                store_key             BIGINT NOT NULL,
                calendar_year         INT NOT NULL,
                month_number          INT NOT NULL,
                total_cost            DECIMAL(18,2) DEFAULT 0,
                total_return_amount   DECIMAL(18,2) DEFAULT 0,
                total_return_quantity DECIMAL(14,2) DEFAULT 0,
                PRIMARY KEY (store_key, calendar_year, month_number)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if force or not _table_has_data(conn, "agg_store_monthly_costs"):
            conn.execute(text("DELETE FROM agg_store_monthly_costs"))
            conn.execute(text("""
                INSERT INTO agg_store_monthly_costs
                    (store_key, calendar_year, month_number,
                     total_cost, total_return_amount, total_return_quantity)
                SELECT StoreKey, YEAR(DateKey), MONTH(DateKey),
                       SUM(TotalCost), SUM(ReturnAmount), SUM(ReturnQuantity)
                FROM FactSales
                GROUP BY StoreKey, YEAR(DateKey), MONTH(DateKey)
            """))
            logger.info("agg_store_monthly_costs built (full)")
        elif new_sales:
            # Chá»‰ xá»­ lÃ½ cÃ¡c dÃ²ng má»›i, cá»™ng dá»“n vÃ o thÃ¡ng hiá»‡n cÃ³
            conn.execute(text(f"""
                INSERT INTO agg_store_monthly_costs
                    (store_key, calendar_year, month_number,
                     total_cost, total_return_amount, total_return_quantity)
                SELECT StoreKey, YEAR(DateKey), MONTH(DateKey),
                       SUM(TotalCost), SUM(ReturnAmount), SUM(ReturnQuantity)
                FROM FactSales
                WHERE SalesKey > {int(sales_wm)}
                GROUP BY StoreKey, YEAR(DateKey), MONTH(DateKey)
                ON DUPLICATE KEY UPDATE
                    total_cost            = total_cost            + VALUES(total_cost),
                    total_return_amount   = total_return_amount   + VALUES(total_return_amount),
                    total_return_quantity = total_return_quantity + VALUES(total_return_quantity)
            """))
            logger.info("agg_store_monthly_costs updated (incremental)")
        else:
            logger.info("agg_store_monthly_costs: no new sales, skipping")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # 6. agg_channel_summary
        #    Chá»‰ 2 dÃ²ng káº¿t quáº£ â†’ tÃ­nh láº¡i Ä‘áº§y Ä‘á»§ ráº¥t nhanh.
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_channel_summary (
                channel      VARCHAR(20) NOT NULL,
                revenue      DECIMAL(20,2) DEFAULT 0,
                profit       DECIMAL(20,2) DEFAULT 0,
                transactions BIGINT DEFAULT 0,
                PRIMARY KEY (channel)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if new_sales or new_online or force or not _table_has_data(conn, "agg_channel_summary"):
            conn.execute(text("DELETE FROM agg_channel_summary"))
            conn.execute(text("""
                INSERT INTO agg_channel_summary (channel, revenue, profit, transactions)
                SELECT 'Offline',
                       SUM(s.total_sales_amount),
                       SUM(s.total_sales_amount) - SUM(s.total_sales_quantity * p.UnitCost),
                       SUM(s.total_sales_quantity)
                FROM summary_daily_sales s
                LEFT JOIN DimProduct p ON p.ProductKey = s.ProductKey
            """))
            conn.execute(text("""
                INSERT INTO agg_channel_summary (channel, revenue, profit, transactions)
                SELECT 'Online',
                       SUM(o.SalesAmount),
                       SUM(o.SalesAmount) - SUM(o.SalesQuantity * p.UnitCost),
                       SUM(o.SalesQuantity)
                FROM FactOnlineSales o
                LEFT JOIN DimProduct p ON p.ProductKey = o.ProductKey
            """))
            logger.info("agg_channel_summary rebuilt")
        else:
            logger.info("agg_channel_summary: no new data, skipping")

        # â”€â”€ LÆ°u watermarks sau khi táº¥t cáº£ thÃ nh cÃ´ng â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    engine.dispose()
    logger.info("ETL incremental update complete.")


def run_etl():
    """Run the full ETL pipeline: POSâ†’DW sync, then incrementally update all aggregate tables."""
    # Step 1: Sync POS data into DW fact tables
    try:
        from modules.data_management.pos_etl import sync_pos_to_dw
        stats = sync_pos_to_dw()
        logger.info("POSâ†’DW sync: %s", stats)
    except Exception as exc:
        logger.warning("POSâ†’DW sync skipped: %s", exc)

    # Step 2: Update aggregate tables (incremental)
    create_aggregate_tables(force=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_etl()

