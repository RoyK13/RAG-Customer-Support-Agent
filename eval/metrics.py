"""Custom metrics: citation accuracy, escalation accuracy, and retrieval hit rate."""

from app.citations import CITATION_RE, split_claims

CITATION_SYSTEM = """You check whether documentation passages support claims.
For each numbered pair, decide whether the passage states the information in the claim.
A claim is supported only if every fact in it appears in the passage. Paraphrasing is fine.
Reply with JSON only: {"verdicts": [true, false, ...]} with one boolean per pair, in order."""


def citation_pairs(answer: str, citations: list[dict]) -> list[tuple[str, str]]:
    """(claim, cited excerpt) for every citation marker attached to a claim."""
    by_id = {c["citation_id"]: c["excerpt"] for c in citations}
    pairs = []
    for claim in split_claims(answer):
        ids = [int(n) for group in CITATION_RE.findall(claim) for n in group.split(",")]
        bare = CITATION_RE.sub("", claim).strip()
        for cid in dict.fromkeys(ids):
            if cid in by_id:
                pairs.append((bare, by_id[cid]))
    return pairs


def judge_citations(judge, answer: str, citations: list[dict]) -> list[bool]:
    pairs = citation_pairs(answer, citations)
    if not pairs:
        return []
    prompt = "\n\n".join(f"Pair {i}\nClaim: {claim}\nPassage:\n{passage}" for i, (claim, passage) in enumerate(pairs, 1))
    data = judge.complete_json(prompt, system=CITATION_SYSTEM)
    verdicts = [bool(v) for v in data.get("verdicts", [])]
    if len(verdicts) != len(pairs):
        raise ValueError(f"expected {len(pairs)} verdicts, got {len(verdicts)}")
    return verdicts


def escalation_summary(rows: list[dict]) -> dict:
    correct = sum(1 for r in rows if r["escalated"] == r["should_escalate"])
    return {
        "value": correct / len(rows) if rows else None,
        "correct": correct,
        "total": len(rows),
        "missed_escalations": sum(1 for r in rows if r["should_escalate"] and not r["escalated"]),
        "false_escalations": sum(1 for r in rows if not r["should_escalate"] and r["escalated"]),
    }


def retrieval_hit(expected: dict | None, retrieved: list[dict]) -> bool | None:
    """Whether the expected section (doc and section path) is among the retrieved chunks."""
    if not expected:
        return None
    return any(
        r["doc_id"] == expected["doc_id"] and r["section_path"].startswith(expected["section_path"])
        for r in retrieved
    )
