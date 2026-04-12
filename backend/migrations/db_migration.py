from sqlalchemy import text

from core.database import get_engine, resolve_database_name


INDEX_PLAN = {
    "FactSales":       ["SalesKey", "DateKey", "StoreKey", "ProductKey", "PromotionKey"],
    "FactOnlineSales": ["OnlineSalesKey", "DateKey", "StoreKey", "ProductKey", "PromotionKey"],
    "FactInventory":   ["DateKey", "StoreKey", "ProductKey"],
    "DimEmployee":     ["EmployeeKey", "ParentEmployeeKey"],
}


def _column_exists(table_name: str, column_name: str) -> bool:
    schema_name = resolve_database_name()
    sql = text(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = :schema_name
          AND table_name = :table_name
          AND column_name = :column_name
        LIMIT 1
        """
    )
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {"schema_name": schema_name, "table_name": table_name, "column_name": column_name},
        ).first()
    return row is not None


def _ensure_index(table_name: str, column_name: str) -> None:
    schema_name = resolve_database_name()
    index_name = f"idx_{table_name.lower()}_{column_name.lower()}"
    engine = get_engine()

    check_sql = text(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = :schema_name
          AND table_name = :table_name
          AND index_name = :index_name
        LIMIT 1
        """
    )
    column_info_sql = text(
        """
        SELECT data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = :schema_name
          AND table_name = :table_name
          AND column_name = :column_name
        LIMIT 1
        """
    )

    with engine.begin() as conn:
        exists = conn.execute(
            check_sql,
            {"schema_name": schema_name, "table_name": table_name, "index_name": index_name},
        ).first()
        if not exists:
            col = conn.execute(
                column_info_sql,
                {"schema_name": schema_name, "table_name": table_name, "column_name": column_name},
            ).first()
            if not col:
                return

            data_type = str(col[0]).lower()
            char_len = int(col[1]) if col[1] else 0
            if data_type in {"varchar", "char", "text", "tinytext", "mediumtext", "longtext", "blob", "tinyblob", "mediumblob", "longblob"}:
                prefix = min(32, char_len) if char_len > 0 else 32
                create_sql = text(f"CREATE INDEX {index_name} ON {table_name} ({column_name}({prefix}))")
            else:
                create_sql = text(f"CREATE INDEX {index_name} ON {table_name} ({column_name})")

            conn.execute(create_sql)


def _ensure_view() -> None:
    offline_key = "SalesKey" if _column_exists("FactSales", "SalesKey") else "NULL"
    if _column_exists("FactOnlineSales", "OnlineSalesKey"):
        online_key = "OnlineSalesKey"
    elif _column_exists("FactOnlineSales", "SalesKey"):
        online_key = "SalesKey"
    else:
        online_key = "NULL"

    sql = f"""
    CREATE OR REPLACE VIEW v_total_sales AS
    SELECT
        {offline_key} AS SaleKey,
        DateKey,
        StoreKey,
        ProductKey,
        PromotionKey,
        NULL AS CustomerKey,
        SalesQuantity,
        SalesAmount,
        ReturnAmount,
        DiscountAmount,
        TotalCost,
        'OFFLINE' AS SaleChannel
    FROM FactSales
    UNION ALL
    SELECT
        {online_key} AS SaleKey,
        DateKey,
        StoreKey,
        ProductKey,
        PromotionKey,
        CustomerKey,
        SalesQuantity,
        SalesAmount,
        ReturnAmount,
        DiscountAmount,
        TotalCost,
        'ONLINE' AS SaleChannel
    FROM FactOnlineSales
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql))


def _ensure_summary_table() -> None:
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS summary_daily_sales (
        DateKey DATE NOT NULL,
        StoreKey BIGINT NOT NULL,
        ProductKey BIGINT NOT NULL,
        PromotionKey BIGINT NOT NULL DEFAULT 0,
        total_sales_quantity DECIMAL(18, 2) NOT NULL DEFAULT 0,
        total_sales_amount DECIMAL(18, 2) NOT NULL DEFAULT 0,
        total_return_amount DECIMAL(18, 2) NOT NULL DEFAULT 0,
        total_discount_amount DECIMAL(18, 2) NOT NULL DEFAULT 0,
        total_cost DECIMAL(18, 2) NOT NULL DEFAULT 0,
        PRIMARY KEY (DateKey, StoreKey, ProductKey, PromotionKey)
    )
    """

    refill_sql = """
    REPLACE INTO summary_daily_sales
        (DateKey, StoreKey, ProductKey, PromotionKey,
         total_sales_quantity, total_sales_amount,
         total_return_amount, total_discount_amount, total_cost)
    SELECT
        DATE(DateKey) AS DateKey,
        COALESCE(StoreKey, 0) AS StoreKey,
        ProductKey,
        COALESCE(PromotionKey, 0) AS PromotionKey,
        SUM(SalesQuantity) AS total_sales_quantity,
        SUM(SalesAmount) AS total_sales_amount,
        SUM(COALESCE(ReturnAmount, 0)) AS total_return_amount,
        SUM(COALESCE(DiscountAmount, 0)) AS total_discount_amount,
        SUM(COALESCE(TotalCost, 0)) AS total_cost
    FROM v_total_sales
    GROUP BY DATE(DateKey), COALESCE(StoreKey, 0), ProductKey, COALESCE(PromotionKey, 0)
    """

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(create_table_sql))
        # Add columns if they don't exist (for existing tables)
        for col, coldef in [
            ("total_return_amount", "DECIMAL(18,2) NOT NULL DEFAULT 0"),
            ("total_discount_amount", "DECIMAL(18,2) NOT NULL DEFAULT 0"),
            ("total_cost", "DECIMAL(18,2) NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(text(
                    f"ALTER TABLE summary_daily_sales ADD COLUMN {col} {coldef}"
                ))
            except Exception:
                pass  # column already exists
        row = conn.execute(text("SELECT COUNT(*) AS cnt FROM summary_daily_sales")).mappings().first()
        if row and row["cnt"] > 0:
            # Check if return/discount columns are populated
            check = conn.execute(text(
                "SELECT COALESCE(SUM(total_return_amount),0) AS s FROM summary_daily_sales LIMIT 1"
            )).mappings().first()
            if check and float(check["s"]) == 0:
                # Update existing rows with return/discount data instead of full rebuild
                conn.execute(text("""
                    UPDATE summary_daily_sales sds
                    JOIN (
                        SELECT
                            DATE(DateKey) AS dk,
                            COALESCE(StoreKey, 0) AS sk,
                            ProductKey AS pk,
                            COALESCE(PromotionKey, 0) AS promk,
                            SUM(COALESCE(ReturnAmount, 0)) AS ra,
                            SUM(COALESCE(DiscountAmount, 0)) AS da
                        FROM v_total_sales
                        GROUP BY DATE(DateKey), COALESCE(StoreKey, 0), ProductKey, COALESCE(PromotionKey, 0)
                    ) src ON sds.DateKey = src.dk
                        AND sds.StoreKey = src.sk
                        AND sds.ProductKey = src.pk
                        AND sds.PromotionKey = src.promk
                    SET sds.total_return_amount = src.ra,
                        sds.total_discount_amount = src.da
                """))
            return
        conn.execute(text(refill_sql))


def run_migration() -> None:
    for table_name, columns in INDEX_PLAN.items():
        for column_name in columns:
            _ensure_index(table_name, column_name)

    _ensure_view()
    _ensure_summary_table()


if __name__ == "__main__":
    run_migration()
    print("Migration completed successfully.")

