import pandas as pd
data_dir = r'c:\Users\LEGION\BI-Dashboard\BI_Datasets'
fact_path = f"{data_dir}/FactSales.csv"
store_path = f"{data_dir}/DimStore.csv"

df_fact = pd.read_csv(fact_path, nrows=100)
df_store = pd.read_csv(store_path)

if 'StoreKey' in df_fact.columns and 'StoreKey' in df_store.columns:
    cols_to_keep = ['StoreKey'] + ([c for c in ['StoreName'] if c in df_store.columns])
    df_store_slim = df_store[cols_to_keep].drop_duplicates()
    
    if 'StoreName' in df_fact.columns:
        df_fact = df_fact.drop(columns=['StoreName'])
        
    df_fact = pd.merge(df_fact, df_store_slim, on='StoreKey', how='left')

df_fact['TotalSales'] = df_fact.get('SalesQuantity', 0) * df_fact.get('UnitPrice', 0) - df_fact.get('DiscountAmount', 0)

store_col = 'StoreName' if 'StoreName' in df_fact.columns else 'StoreKey'
pie = df_fact.groupby(store_col)['TotalSales'].sum().reset_index()
pie_data = {
    "labels": pie[store_col].astype(str).tolist(),
    "data": pie['TotalSales'].fillna(0).tolist()
}
print("New Pie Chart Labels:", pie_data['labels'])
