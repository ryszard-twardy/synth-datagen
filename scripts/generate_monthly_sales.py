from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.monthly_sales_cli import app  # noqa: E402


if __name__ == "__main__":
    app()
