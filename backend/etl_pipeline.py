"""
ETL Pipeline: Extract from POS System → Transform → Load into BI Data Warehouse.

This module demonstrates a realistic ETL flow from a normalized operational
database (pos_system) into the star-schema BI warehouse (retails_dataset).

New aggregate tables created:
  - agg_inventory_metrics    (Inventory Turnover, GMROI, Sell-Through Rate)
  - agg_product_performance  (Product-level ABC classification, revenue rank)
  - agg_customer_rfm         (RFM segmentation scores)
  - agg_kpi_summary          (Pre-computed retail KPIs for dashboard)
"""

import logging
from sqlalchemy import create_engine, text

from config import (
    DW_HOST, DW_PORT, DW_USER, DW_PASSWORD, DW_DATABASE,
)

logger = logging.getLogger(__name__)


def _dw_url():
    return f"mysql+pymysql://{DW_USER}:{DW_PASSWORD}@{DW_HOST}:{DW_PORT}/{DW_DATABASE}?charset=utf8mb4"


def create_aggregate_tables(force: bool = False):
    """Create all aggregate/KPI tables in the BI Data Warehouse.

    CONSTRAINT: Only uses CREATE TABLE IF NOT EXISTS and SELECT.
    Never ALTER/UPDATE/DELETE existing DW tables.

    Args:
        force: If False (startup), skip tables that already have data.
               If True (manual ETL), rebuild all tables.
    """
    engine = create_engine(_dw_url(), pool_pre_ping=True)

    def _table_has_data(conn, table_name: str) -> bool:
        """Return True if the table exists and has at least one row."""
        try:
            row = conn.execute(text(f"SELECT COUNT(*) AS cnt FROM {table_name}")).mappings().first()
            return row and row["cnt"] > 0
        except Exception:
            return False

    with engine.begin() as conn:

        # ═══════════════════════════════════════════════════════════
        # 1. agg_inventory_metrics
        #    Calculates key inventory KPIs per product per store per month.
        # ═══════════════════════════════════════════════════════════
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

        if force or not _table_has_data(conn, "agg_inventory_metrics"):
            # Step 1: Pre-aggregate FactSales into temp table
            conn.execute(text("DROP TABLE IF EXISTS _tmp_sales_agg"))
            conn.execute(text("""
                CREATE TABLE _tmp_sales_agg AS
                SELECT
                    ProductKey,
                    StoreKey,
                    CONCAT(YEAR(DateKey), '-', LPAD(MONTH(DateKey),2,'0')) AS ym,
                    SUM(SalesQuantity) AS total_qty,
                    SUM(TotalCost) AS total_cost,
                    SUM(SalesAmount) AS total_revenue,
                    SUM(SalesQuantity) / COUNT(DISTINCT DATE(DateKey)) AS daily_avg_sold
                FROM FactSales
                GROUP BY ProductKey, StoreKey, CONCAT(YEAR(DateKey), '-', LPAD(MONTH(DateKey),2,'0'))
            """))
            conn.execute(text("""
                ALTER TABLE _tmp_sales_agg
                ADD INDEX idx_tmp_sa (ProductKey, StoreKey, ym)
            """))
            logger.info("_tmp_sales_agg created")

            # Step 2: Pre-aggregate FactInventory into temp table
            conn.execute(text("DROP TABLE IF EXISTS _tmp_inv_agg"))
            conn.execute(text("""
                CREATE TABLE _tmp_inv_agg AS
                SELECT
                    ProductKey,
                    StoreKey,
                    CONCAT(YEAR(DateKey), '-', LPAD(MONTH(DateKey),2,'0')) AS ym,
                    AVG(OnHandQuantity) AS avg_on_hand,
                    AVG(OnHandQuantity * UnitCost) AS avg_inv_cost
                FROM FactInventory
                GROUP BY ProductKey, StoreKey, CONCAT(YEAR(DateKey), '-', LPAD(MONTH(DateKey),2,'0'))
            """))
            conn.execute(text("""
                ALTER TABLE _tmp_inv_agg
                ADD INDEX idx_tmp_ia (ProductKey, StoreKey, ym)
            """))
            logger.info("_tmp_inv_agg created")

            # Step 3: Join two small aggregated tables
            conn.execute(text("""
                REPLACE INTO agg_inventory_metrics
                    (product_key, store_key, period_month,
                     avg_on_hand, total_sold, total_cost_sold, total_revenue, gross_profit,
                     inventory_turnover, sell_through_rate, gmroi, days_of_supply)
                SELECT
                    inv.ProductKey,
                    inv.StoreKey,
                    inv.ym,
                    inv.avg_on_hand,
                    COALESCE(s.total_qty, 0),
                    COALESCE(s.total_cost, 0),
                    COALESCE(s.total_revenue, 0),
                    COALESCE(s.total_revenue, 0) - COALESCE(s.total_cost, 0),
                    CASE WHEN inv.avg_inv_cost > 0
                         THEN COALESCE(s.total_cost, 0) / inv.avg_inv_cost
                         ELSE 0
                    END,
                    CASE WHEN (COALESCE(s.total_qty, 0) + inv.avg_on_hand) > 0
                         THEN COALESCE(s.total_qty, 0) / (COALESCE(s.total_qty, 0) + inv.avg_on_hand)
                         ELSE 0
                    END,
                    CASE WHEN inv.avg_inv_cost > 0
                         THEN (COALESCE(s.total_revenue, 0) - COALESCE(s.total_cost, 0)) / inv.avg_inv_cost
                         ELSE 0
                    END,
                    CASE WHEN COALESCE(s.daily_avg_sold, 0) > 0
                         THEN inv.avg_on_hand / s.daily_avg_sold
                         ELSE 0
                    END
                FROM _tmp_inv_agg inv
                LEFT JOIN _tmp_sales_agg s
                    ON s.ProductKey = inv.ProductKey
                   AND s.StoreKey = inv.StoreKey
                   AND s.ym = inv.ym
            """))

            # Cleanup temp tables
            conn.execute(text("DROP TABLE IF EXISTS _tmp_sales_agg"))
            conn.execute(text("DROP TABLE IF EXISTS _tmp_inv_agg"))
            logger.info("agg_inventory_metrics populated")
        else:
            logger.info("agg_inventory_metrics already has data, skipping")

        # ═══════════════════════════════════════════════════════════
        # 2. agg_product_performance
        #    ABC Classification + revenue rank per product
        # ═══════════════════════════════════════════════════════════
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

        if force or not _table_has_data(conn, "agg_product_performance"):
            conn.execute(text("DELETE FROM agg_product_performance"))
            conn.execute(text("""
            INSERT INTO agg_product_performance
                (product_key, product_name, brand_name, category_name, subcategory_name,
                 total_revenue, total_quantity, total_cost, gross_profit, profit_margin,
                 revenue_rank, abc_class, cumulative_pct)
            SELECT
                p.ProductKey,
                p.ProductName,
                p.BrandName,
                COALESCE(pc.ProductCategoryName, ''),
                COALESCE(psc.ProductSubcategoryName, ''),
                agg.total_revenue,
                agg.total_quantity,
                agg.total_cost,
                agg.total_revenue - agg.total_cost AS gross_profit,
                CASE WHEN agg.total_revenue > 0
                     THEN (agg.total_revenue - agg.total_cost) / agg.total_revenue
                     ELSE 0
                END AS profit_margin,
                RANK() OVER (ORDER BY agg.total_revenue DESC) AS revenue_rank,
                'C' AS abc_class,
                SUM(agg.total_revenue) OVER (ORDER BY agg.total_revenue DESC)
                    / SUM(agg.total_revenue) OVER () AS cumulative_pct
            FROM (
                SELECT ProductKey,
                       SUM(SalesAmount) AS total_revenue,
                       SUM(SalesQuantity) AS total_quantity,
                       SUM(TotalCost) AS total_cost
                FROM v_total_sales
                GROUP BY ProductKey
            ) agg
            JOIN DimProduct p ON p.ProductKey = agg.ProductKey
            LEFT JOIN DimProductSubcategory psc ON psc.ProductSubcategoryKey = p.ProductSubcategoryKey
            LEFT JOIN DimProductCategory pc ON pc.ProductCategoryKey = psc.ProductCategoryKey
        """))

            # Fix ABC class in-place
            conn.execute(text("""
                UPDATE agg_product_performance
                SET abc_class = CASE
                    WHEN cumulative_pct <= 0.80 THEN 'A'
                    WHEN cumulative_pct <= 0.95 THEN 'B'
                    ELSE 'C'
                END
            """))
            logger.info("agg_product_performance populated")
        else:
            logger.info("agg_product_performance already has data, skipping")

        # ═══════════════════════════════════════════════════════════
        # 3. agg_customer_rfm
        #    RFM Analysis for customer segmentation
        # ═══════════════════════════════════════════════════════════
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

        if force or not _table_has_data(conn, "agg_customer_rfm"):
            conn.execute(text("DELETE FROM agg_customer_rfm"))
            conn.execute(text("""
            INSERT INTO agg_customer_rfm
                (customer_key, last_order_date, recency_days, frequency, monetary,
                 r_score, f_score, m_score, rfm_segment)
            SELECT
                base.CustomerKey,
                base.last_order_date,
                base.recency_days,
                base.frequency,
                base.monetary,
                base.r_score,
                base.f_score,
                base.m_score,
                CASE
                    WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champion'
                    WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal'
                    WHEN r_score >= 4 AND f_score <= 2 THEN 'New Customer'
                    WHEN r_score <= 2 AND f_score >= 3 AND m_score >= 3 THEN 'At Risk'
                    WHEN r_score <= 2 AND f_score <= 2 THEN 'Lost'
                    WHEN r_score >= 3 AND m_score >= 3 THEN 'Potential Loyalist'
                    ELSE 'Need Attention'
                END AS rfm_segment
            FROM (
                SELECT
                    rfm.*,
                    NTILE(5) OVER (ORDER BY recency_days ASC)  AS r_score,
                    NTILE(5) OVER (ORDER BY frequency ASC)     AS f_score,
                    NTILE(5) OVER (ORDER BY monetary ASC)      AS m_score
                FROM (
                    SELECT
                        CustomerKey,
                        MAX(DATE(DateKey)) AS last_order_date,
                        DATEDIFF((SELECT MAX(DATE(DateKey)) FROM FactOnlineSales), MAX(DATE(DateKey))) AS recency_days,
                        COUNT(DISTINCT SalesOrderNumber) AS frequency,
                        SUM(SalesAmount) AS monetary
                    FROM FactOnlineSales
                    WHERE CustomerKey IS NOT NULL
                    GROUP BY CustomerKey
                ) rfm
            ) base
        """))

            logger.info("agg_customer_rfm populated")
        else:
            logger.info("agg_customer_rfm already has data, skipping")

        # ═══════════════════════════════════════════════════════════
        # 4. agg_kpi_summary
        #    Pre-computed retail KPIs for dashboard cards.
        # ═══════════════════════════════════════════════════════════
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_kpi_summary (
                kpi_key             VARCHAR(50) PRIMARY KEY,
                kpi_label           VARCHAR(100),
                kpi_value           DECIMAL(18,4) DEFAULT 0,
                kpi_unit            VARCHAR(20) DEFAULT '',
                period              VARCHAR(20) DEFAULT 'ALL',
                computed_at         DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if force or not _table_has_data(conn, "agg_kpi_summary"):
            conn.execute(text("DELETE FROM agg_kpi_summary"))

            # Single scan of v_total_sales → temp aggregate
            conn.execute(text("DROP TABLE IF EXISTS _tmp_kpi_agg"))
            conn.execute(text("""
                CREATE TABLE _tmp_kpi_agg AS
                SELECT
                    COUNT(*)           AS cnt,
                    SUM(SalesAmount)   AS sum_amt,
                    SUM(TotalCost)     AS sum_cost,
                    AVG(SalesAmount)   AS avg_amt,
                    AVG(SalesQuantity) AS avg_qty
                FROM v_total_sales
            """))
            logger.info("_tmp_kpi_agg created (single scan of v_total_sales)")

            # Insert all 5 sales KPIs from the temp table
            conn.execute(text("""
                INSERT INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'total_revenue', 'Total Revenue', sum_amt, 'USD', 'ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'total_transactions', 'Total Transactions', cnt, 'count', 'ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'avg_transaction_value', 'Average Transaction Value', avg_amt, 'USD', 'ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'avg_basket_size', 'Average Basket Size', avg_qty, 'units', 'ALL' FROM _tmp_kpi_agg
                UNION ALL
                SELECT 'gross_margin', 'Gross Profit Margin',
                       CASE WHEN sum_amt > 0 THEN (sum_amt - sum_cost) / sum_amt * 100 ELSE 0 END,
                       'pct', 'ALL'
                FROM _tmp_kpi_agg
            """))
            conn.execute(text("DROP TABLE IF EXISTS _tmp_kpi_agg"))

            # Active Store Count
            conn.execute(text("""
                INSERT INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'active_stores', 'Active Stores',
                       COUNT(DISTINCT StoreKey), 'count', 'ALL'
                FROM DimStore
                WHERE Status = 'On'
            """))

            # Product Count
            conn.execute(text("""
                INSERT INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'product_count', 'Product Count',
                       COUNT(*), 'count', 'ALL'
                FROM DimProduct
            """))

            # Unique Customers
            conn.execute(text("""
                INSERT INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'unique_customers', 'Unique Customers',
                       COUNT(DISTINCT CustomerKey), 'count', 'ALL'
                FROM FactOnlineSales
                WHERE CustomerKey IS NOT NULL
            """))

            # Average Inventory Turnover
            conn.execute(text("""
                INSERT INTO agg_kpi_summary (kpi_key, kpi_label, kpi_value, kpi_unit, period)
                SELECT 'avg_inventory_turnover', 'Avg Inventory Turnover',
                       AVG(inventory_turnover), 'ratio', 'ALL'
                FROM agg_inventory_metrics
                WHERE inventory_turnover > 0
            """))

            logger.info("agg_kpi_summary populated")
        else:
            logger.info("agg_kpi_summary already has data, skipping")

        # ═══════════════════════════════════════════════════════════
        # 5. agg_store_monthly_costs
        #    Pre-aggregated cost & return data per store per month
        #    from FactSales for Employee Performance dashboard.
        # ═══════════════════════════════════════════════════════════
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_store_monthly_costs (
                store_key       BIGINT NOT NULL,
                calendar_year   INT NOT NULL,
                month_number    INT NOT NULL,
                total_cost      DECIMAL(18,2) DEFAULT 0,
                total_return_amount  DECIMAL(18,2) DEFAULT 0,
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
            SELECT
                StoreKey,
                YEAR(DateKey),
                MONTH(DateKey),
                SUM(TotalCost),
                SUM(ReturnAmount),
                SUM(ReturnQuantity)
            FROM FactSales
            GROUP BY StoreKey, YEAR(DateKey), MONTH(DateKey)
        """))

            logger.info("agg_store_monthly_costs populated")
        else:
            logger.info("agg_store_monthly_costs already has data, skipping")

        # ═══════════════════════════════════════════════════════════
        # 6. agg_channel_summary
        #    Pre-aggregated revenue/profit/transactions per channel
        #    (Offline from summary_daily_sales, Online from FactOnlineSales).
        # ═══════════════════════════════════════════════════════════
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agg_channel_summary (
                channel       VARCHAR(20) NOT NULL,
                revenue       DECIMAL(20,2) DEFAULT 0,
                profit        DECIMAL(20,2) DEFAULT 0,
                transactions  BIGINT DEFAULT 0,
                PRIMARY KEY (channel)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        if force or not _table_has_data(conn, "agg_channel_summary"):
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
            logger.info("agg_channel_summary populated")
        else:
            logger.info("agg_channel_summary already has data, skipping")

    engine.dispose()
    logger.info("All aggregate tables created and populated.")


def run_etl():
    """Run the full ETL pipeline: POS→DW sync, then force rebuild all aggregate tables."""
    # Step 1: Sync POS data into DW fact tables
    try:
        from data_management.pos_etl import sync_pos_to_dw
        stats = sync_pos_to_dw()
        logger.info("POS→DW sync: %s", stats)
    except Exception as exc:
        logger.warning("POS→DW sync skipped: %s", exc)

    # Step 2: Rebuild aggregate tables
    create_aggregate_tables(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_etl()
