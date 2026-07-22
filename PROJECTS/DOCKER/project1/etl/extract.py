import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

RAW_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "raw_sales.csv"

def extract() -> pd.DataFrame:
    logger.info(f"Extracting data from {RAW_DATA_PATH}")
    try:
        df =pd.read_csv(RAW_DATA_PATH)
        logger.info(f"Successfully extracted data with shape {df.shape} and columns {df.columns.tolist()} and extracted rows {len(df)}")
        return df
    except Exception as e:
        logger.error(f"Error extracting data: {e}")
        raise
