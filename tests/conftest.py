import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str):
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))
