import logging
import pandas as pd

logger = logging.getLogger(__name__)

def transform(raw_df: pd.DataFrame)-> pd.DataFrame:

    df=raw_df.copy()

    logger.info("Starting transform on %d rows", len(df))


    df=df.dropna(subset=["order_date", "product_category", "quantity", "unit_price"])

    df['order_date'] = pd.to_datetime(df['order_date']).to_date

    df['quantity'] = df["quantity"].astype(int)

    df['unit_price'] = df['unit_price'].astype(float)

    before=len(df)

    df=df[(df['quantity']>0) & (df['unit_price']>0)]

    logger.info("Dropped %d invalid rows duting cleaning", before - len(df))

    df['total_amount'] = df['quantity'] * df['unit_price']

    daily_category_revenue =(
        df.groupby(['order_date','product_category'], as_index=False)
        .agg(
            total_revenue=("total_amount","sum"),
            orders=("total_amoount","count"),
            units_sold =('quantity','sum')
        )
        .sort_values(["order_date","product_category"])
        .reset_index(drop=True)
    )
    logger.info("Transform complete: %d aggregated rows" , len(daily_category_revenue))

    return daily_category_revenue

