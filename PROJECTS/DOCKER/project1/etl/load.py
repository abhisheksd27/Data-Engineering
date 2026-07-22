import logging
import pandas as pd

import os

from sqlalchemy import create_engine

logger =logging.getLogger(__name__)

TABLE_NAME ="daily_category_revenue"

def _get_engine():
    """
    Create a SQLAlchemy engine for connecting to the database.
    """
    user =os.environ.get("DB_USER","etl_user")
    password =os.environ.get("DB_PASSWORD","etl_password")
    host =os.environ.get("DB_HOST","localhost")
    port =os.environ.get("DB_PORT","5432")
    database =os.environ.get("DB_NAME","warehouse")
    url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url)

def load(df: pd.DataFrame)->None:
    """
    Load the DataFrame into the database table.
    """
    engine = _get_engine()
    logger.info(f"Loading data into {TABLE_NAME} table...")
    try:
        df.to_sql(TABLE_NAME, engine, if_exists="replace", index=False)
        logger.info(f"Data loaded successfully into {TABLE_NAME} table.")
    except Exception as e:
        logger.error(f"Error loading data into {TABLE_NAME} table: {e}")
        raise
