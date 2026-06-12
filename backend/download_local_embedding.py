from __future__ import annotations

import os
from pathlib import Path

from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-zh-v1.5"
TARGET_DIR = Path(__file__).resolve().parent / "models" / "bge-small-zh-v1.5"
CACHE_DIR = Path(__file__).resolve().parent / ".hf-cache"


def main() -> None:
    os.environ.setdefault("HF_HOME", str(CACHE_DIR))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(CACHE_DIR / "hub"))
    TARGET_DIR.parent.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer(MODEL_NAME, cache_folder=str(CACHE_DIR))
    model.save(str(TARGET_DIR))
    print(TARGET_DIR)


if __name__ == "__main__":
    main()
