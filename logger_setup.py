import logging
from datetime import datetime

from config import LOGS_DIR


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_file = LOGS_DIR / f'auto_responsible_{datetime.now():%Y-%m-%d}.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )