from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.metrics import run_evaluation  # noqa: E402
from app.services.agent import JobAgent  # noqa: E402
from app.services.llm import OfflineProvider  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(run_evaluation(JobAgent(llm_provider=OfflineProvider())).model_dump(mode="json"), ensure_ascii=False, indent=2))
