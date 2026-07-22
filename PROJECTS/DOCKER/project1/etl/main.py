import logging
import pandas as pd

from etl.extract import extract
from etl.transform import transform
from etl.load import load

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

def run_pipeline():
    logger.info("Starting ETL process...")
    try:
        raw_data = extract()
        logger.info("Data extraction completed.")
        transformed_data = transform(raw_data)
        logger.info("Data transformation completed.")
        load(transformed_data)
        logger.info("Data loading completed.")
    except Exception as e:
        logger.error(f"ETL process failed: {e}")
        raise

if __name__ == "__main__":
    run_pipeline()