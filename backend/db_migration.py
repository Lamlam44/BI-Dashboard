from sqlalchemy import text

from db_utils import get_engine, resolve_database_name


INDEX_PLAN = {
    "FactSales": ["DateKey", "StoreKey", "ProductKey", "PromotionKey"],
    "FactOnlineSales": ["DateKey", "StoreKey", "ProductKey", "PromotionKey"],
    "DimEmployee": ["EmployeeKey", "ParentEmployeeKey"],
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
        PRIMARY KEY (DateKey, StoreKey, ProductKey, PromotionKey)
    )
    """

    refill_sql = """
    REPLACE INTO summary_daily_sales
        (DateKey, StoreKey, ProductKey, PromotionKey, total_sales_quantity, total_sales_amount)
    SELECT
        DATE(DateKey) AS DateKey,
        COALESCE(StoreKey, 0) AS StoreKey,
        ProductKey,
        COALESCE(PromotionKey, 0) AS PromotionKey,
        SUM(SalesQuantity) AS total_sales_quantity,
        SUM(SalesAmount) AS total_sales_amount
    FROM v_total_sales
    GROUP BY DATE(DateKey), COALESCE(StoreKey, 0), ProductKey, COALESCE(PromotionKey, 0)
    """

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(create_table_sql))
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
