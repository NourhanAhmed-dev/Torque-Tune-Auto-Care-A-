from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "db" / "redline.db"))
POLICY_PATH = Path(os.getenv("POLICY_PATH", BASE_DIR / "db" / "policy.md"))

TUNING_CATEGORIES = ["cosmetic", "performance", "emissions_affecting"]
PAYMENT_STATUSES = ["paid", "unpaid", "partial"]
POLICY_URI = "policy://emissions-warranty"