import json
import uuid
import logging
from pathlib import Path
from datetime import datetime

from .config import ENABLE_LOGGING

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = BASE_DIR / "logs"

STORAGE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


def get_logger(name: str):
    """
    Returns a logger that writes to memory/logs/<name>.log
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(
        LOGS_DIR / f"{name}.log",
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


def generate_id():
    return str(uuid.uuid4())


def current_time():
    return datetime.utcnow().isoformat()


def load_json(file_path):
    path = Path(file_path)

    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, default=str)


def write_log(log_name, message):

    if not ENABLE_LOGGING:
        return

    logger = get_logger(log_name)

    logger.info(message)