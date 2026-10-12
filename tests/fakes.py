"""Deterministic stand-ins for the embedding and chat models, used by tests."""

import hashlib
import math
import re


class FakeEmbedder:
    """Bag-of-words hashing embedder. Similar texts get similar vectors, no model download needed."""

    name = "fake:hash-64"
    dim = 64

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class ScriptedChat:
    """Returns queued replies in order and records every prompt it receives."""

    name = "scripted"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise AssertionError("ScriptedChat ran out of replies")
        return self.replies.pop(0)


class EchoChat:
    """Grades every context as sufficient and answers by quoting the first context block with [1]."""

    name = "echo"

    def complete(self, system: str, user: str) -> str:
        if "sufficient" in system:
            return '{"sufficient": true, "reason": "test"}'
        match = re.search(r"\[1\] [^\n]*\n(.+?)(?:\n\n\[2\]|\n\nQuestion:)", user, re.DOTALL)
        first = match.group(1).strip().splitlines()[0] if match else "No context"
        return f"{first.rstrip('.')} [1]."
