"""
embeddings.py — pluggable embedding providers + a dense index for HYBRID retrieval.

Layer 3's lexical BM25 seed is fused with a DENSE (semantic) seed. The embedder is
pluggable and OFF by default (retrieval stays BM25-only, identical to before):

  SUBK_EMBED_PROVIDER unset / "none"  -> no dense channel (default).
  SUBK_EMBED_PROVIDER=hashing         -> HashingEmbedder: pure-stdlib, deterministic
        hashing vectorizer over word + character n-grams. Offline, no install, no network.
        A stand-in that makes the hybrid pipeline runnable and TESTABLE everywhere; it adds
        fuzzy lexical matching (spacing/morphology), NOT true synonymy — that needs a model.
  SUBK_EMBED_PROVIDER=openai          -> OpenAIEmbedder: real semantic embeddings via the
        API (text-embedding-3-small). Pure stdlib urllib, no SDK dependency. Needs
        OPENAI_API_KEY. This is the production choice; use no-train / zero-retention terms
        (the query and node text can carry matter facts — see DEPLOY.md, Rule 1.6).

Vectors are L2-normalized, so cosine similarity is a plain dot product.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request

_WORD = re.compile(r"[a-z0-9]+")


def _l2(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    # both operands are L2-normalized, so the dot product IS the cosine similarity
    return sum(x * y for x, y in zip(a, b))


class HashingEmbedder:
    """Deterministic, dependency-free hashing vectorizer (the offline stand-in)."""
    name = "hashing"

    def __init__(self, dim: int = 256, ngrams=(3, 4)):
        self.dim = dim
        self.ngrams = ngrams

    def _features(self, text: str):
        for w in _WORD.findall(text.lower()):
            yield "w:" + w
            s = "^" + w + "$"
            for n in self.ngrams:
                for i in range(len(s) - n + 1):
                    yield s[i:i + n]

    def embed(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for f in self._features(text):
            # blake2b (not Python's randomized hash) => stable across processes
            h = hashlib.blake2b(f.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % self.dim
            v[idx] += 1.0 if (h[4] & 1) else -1.0  # signed hashing trick
        return _l2(v)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    """Real semantic embeddings via the OpenAI API (stdlib urllib, no SDK)."""
    name = "openai"

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536,
                 api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.dim = dim
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set (required for SUBK_EMBED_PROVIDER=openai)")

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/embeddings", data=body,
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        rows = sorted(data["data"], key=lambda d: d["index"])
        return [_l2(d["embedding"]) for d in rows]

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]


def get_embedder(provider: str | None = None):
    """Build the configured embedder, or None when the dense channel is off."""
    provider = provider if provider is not None else os.environ.get("SUBK_EMBED_PROVIDER")
    if not provider or provider == "none":
        return None
    if provider == "hashing":
        return HashingEmbedder(dim=int(os.environ.get("SUBK_EMBED_DIM", "256")))
    if provider == "openai":
        return OpenAIEmbedder(model=os.environ.get("SUBK_EMBED_MODEL", "text-embedding-3-small"))
    raise ValueError(f"unknown SUBK_EMBED_PROVIDER: {provider!r} (use none|hashing|openai)")


class DenseIndex:
    """Node vectors + the query embedder; yields a cosine score per node id."""
    def __init__(self, embedder, vectors: dict):
        self.embedder = embedder
        self.vectors = vectors

    def scores(self, question: str) -> dict:
        q = self.embedder.embed(question)
        return {nid: cosine(q, v) for nid, v in self.vectors.items()}

    @classmethod
    def from_docs(cls, embedder, docs: dict) -> "DenseIndex":
        """Embed each node's document text once (the in-memory dense index)."""
        ids = list(docs)
        vecs = embedder.embed_many([docs[i] for i in ids])
        return cls(embedder, dict(zip(ids, vecs)))
