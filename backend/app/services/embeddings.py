from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
import urllib.error
import urllib.request

from app.config import get_settings
from app.services.nlp import tokenize


EMBEDDING_FALLBACK_COUNT = 0
LAST_EMBEDDING_PROVIDER = "offline-hashing"
LAST_EMBEDDING_ERROR = ""
EMBEDDING_LOAD_STATUS = "not_loaded"
EMBEDDING_DEVICE = "auto"
EMBEDDING_LATENCIES_MS: list[int] = []
LOCAL_MODEL_CACHE: dict[str, object] = {}


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingProvider:
    name = "offline-hashing"
    model = "hashing"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class OfflineEmbeddingProvider(EmbeddingProvider):
    name = "offline-hashing"
    model = "hashing"

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1 if digest[4] % 2 == 0 else -1
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 6) for value in vector]


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, api_key: str, model: str, name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        start = perf_counter()
        payload = {"model": self.model, "input": texts}
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise EmbeddingProviderError(
                f"{self.name} failed with status={exc.code}, model={self.model}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason.__class__.__name__ if hasattr(exc, "reason") else "URLError"
            raise EmbeddingProviderError(f"{self.name} network error={reason}, model={self.model}") from exc
        except TimeoutError as exc:
            raise EmbeddingProviderError(f"{self.name} timeout, model={self.model}") from exc

        data = body.get("data", [])
        if not isinstance(data, list):
            raise EmbeddingProviderError(f"{self.name} returned invalid data shape, model={self.model}")
        vectors = [_fit_dimension(item["embedding"], get_settings().embedding_dimension) for item in data]
        _record_embedding_latency(start)
        return vectors


class LocalEmbeddingProvider(EmbeddingProvider):
    name = "local-sentence-transformer"

    def __init__(self, dimension: int, model: str, device: str = "auto") -> None:
        self.dimension = dimension
        self.model = model
        self.device = device
        self.fallback = OfflineEmbeddingProvider(dimension)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        global EMBEDDING_LOAD_STATUS, EMBEDDING_DEVICE
        start = perf_counter()
        try:
            model = self._load_model()
            embeddings = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            vectors = [
                _fit_dimension([float(value) for value in embedding], get_settings().embedding_dimension)
                for embedding in embeddings
            ]
            EMBEDDING_LOAD_STATUS = "ready"
            EMBEDDING_DEVICE = self.device
            _record_embedding_latency(start)
            return vectors
        except Exception as exc:
            EMBEDDING_LOAD_STATUS = "fallback"
            raise EmbeddingProviderError(_sanitize_embedding_error(exc)) from exc

    def warmup(self) -> None:
        self.embed_texts(["本地 embedding 预热"])

    def _load_model(self):
        global EMBEDDING_LOAD_STATUS, EMBEDDING_DEVICE
        model_name_or_path = _resolve_local_model_path(self.model)
        cache_key = f"{model_name_or_path}|{self.device}"
        if cache_key in LOCAL_MODEL_CACHE:
            return LOCAL_MODEL_CACHE[cache_key]
        EMBEDDING_LOAD_STATUS = "loading"
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            EMBEDDING_LOAD_STATUS = "error"
            raise EmbeddingProviderError(
                "sentence-transformers is not installed; install backend/requirements-local-embedding.txt"
            ) from exc
        kwargs = {}
        if self.device and self.device != "auto":
            kwargs["device"] = self.device
        model = SentenceTransformer(model_name_or_path, **kwargs)
        LOCAL_MODEL_CACHE[cache_key] = model
        EMBEDDING_DEVICE = getattr(model, "device", self.device)
        EMBEDDING_LOAD_STATUS = "ready"
        return model


class FallbackEmbeddingProvider(EmbeddingProvider):
    def __init__(self, primary: EmbeddingProvider, fallback: EmbeddingProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.last_error: str | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        global EMBEDDING_FALLBACK_COUNT, LAST_EMBEDDING_PROVIDER, LAST_EMBEDDING_ERROR
        try:
            vectors = self.primary.embed_texts(texts)
            if len(vectors) != len(texts):
                raise ValueError("Embedding provider returned an unexpected number of vectors")
            vectors = [_fit_dimension(vector, get_settings().embedding_dimension) for vector in vectors]
            self.name = self.primary.name
            self.model = getattr(self.primary, "model", self.primary.model)
            self.last_error = None
            LAST_EMBEDDING_PROVIDER = self.name
            LAST_EMBEDDING_ERROR = ""
            return vectors
        except Exception as exc:
            self.name = f"{self.primary.name}->fallback:{self.fallback.name}"
            self.last_error = _sanitize_embedding_error(exc)
            EMBEDDING_FALLBACK_COUNT += 1
            LAST_EMBEDDING_PROVIDER = self.name
            LAST_EMBEDDING_ERROR = self.last_error
            return self.fallback.embed_texts(texts)


def cosine_vector(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def get_embedding_provider() -> EmbeddingProvider:
    global LAST_EMBEDDING_PROVIDER
    settings = get_settings()
    fallback = OfflineEmbeddingProvider(settings.embedding_dimension)
    provider_name = settings.embedding_provider.lower().strip()
    if provider_name in {"openai", "openai_compatible"}:
        base_url = settings.embedding_base_url or settings.openai_base_url
        api_key = settings.embedding_api_key or settings.openai_api_key
        model = settings.embedding_model or settings.openai_embedding_model
        if base_url and api_key and model:
            primary = OpenAICompatibleEmbeddingProvider(
                base_url=base_url,
                api_key=api_key,
                model=model,
                name=f"{provider_name}-embedding",
            )
            provider = FallbackEmbeddingProvider(primary, fallback)
            LAST_EMBEDDING_PROVIDER = provider.name
            return provider
    if provider_name == "local":
        primary = LocalEmbeddingProvider(
            settings.embedding_dimension,
            settings.embedding_model or "backend/models/bge-small-zh-v1.5",
            settings.embedding_device,
        )
        provider = FallbackEmbeddingProvider(primary, fallback)
        LAST_EMBEDDING_PROVIDER = provider.name
        return provider
    LAST_EMBEDDING_PROVIDER = fallback.name
    return fallback


def embedding_status() -> dict[str, str | int]:
    settings = get_settings()
    return {
        "embedding_provider": LAST_EMBEDDING_PROVIDER,
        "embedding_fallback_count": EMBEDDING_FALLBACK_COUNT,
        "embedding_configured_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model or settings.openai_embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "embedding_real_enabled": int(not LAST_EMBEDDING_PROVIDER.startswith("offline-hashing") and "fallback" not in LAST_EMBEDDING_PROVIDER),
        "embedding_last_error": LAST_EMBEDDING_ERROR,
        "embedding_device": str(EMBEDDING_DEVICE),
        "embedding_load_status": EMBEDDING_LOAD_STATUS,
        "embedding_latency_ms": _average_embedding_latency(),
    }


def warmup_embedding_provider() -> dict[str, str | int]:
    provider = get_embedding_provider()
    if hasattr(provider, "warmup"):
        provider.warmup()
    else:
        provider.embed_texts(["embedding warmup"])
    return embedding_status()


def _fit_dimension(vector: list[float], dimension: int) -> list[float]:
    if len(vector) == dimension:
        return vector
    if len(vector) > dimension:
        fitted = vector[:dimension]
    else:
        fitted = [*vector, *([0.0] * (dimension - len(vector)))]
    norm = math.sqrt(sum(value * value for value in fitted))
    if norm == 0:
        return fitted
    return [round(value / norm, 6) for value in fitted]


def _resolve_local_model_path(model: str) -> str:
    candidate = Path(model)
    if candidate.exists():
        return str(candidate)
    project_root = Path(__file__).resolve().parents[3]
    project_candidate = project_root / model
    if project_candidate.exists():
        return str(project_candidate)
    backend_candidate = Path(__file__).resolve().parents[2] / model
    if backend_candidate.exists():
        return str(backend_candidate)
    return model


def _sanitize_embedding_error(exc: Exception) -> str:
    text = str(exc)
    settings = get_settings()
    secrets = [
        settings.openai_api_key,
        settings.embedding_api_key,
        settings.openai_base_url,
        settings.embedding_base_url,
    ]
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    if "sk-" in text:
        text = text.split("sk-", 1)[0] + "sk-[redacted]"
    return text[:240]


def _record_embedding_latency(start: float) -> None:
    EMBEDDING_LATENCIES_MS.append(round((perf_counter() - start) * 1000))
    del EMBEDDING_LATENCIES_MS[:-20]


def _average_embedding_latency() -> int:
    if not EMBEDDING_LATENCIES_MS:
        return 0
    return round(sum(EMBEDDING_LATENCIES_MS) / len(EMBEDDING_LATENCIES_MS))
