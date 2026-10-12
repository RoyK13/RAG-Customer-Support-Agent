"""Parse, validate, and renumber inline citations such as [1] or [2, 3]."""

import re
from dataclasses import dataclass, field

CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
CITATION_GROUP = r"(?:\s*\[\d+(?:\s*,\s*\d+)*\])+"
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(*`])")


@dataclass
class ValidationResult:
    cited_ids: list[int] = field(default_factory=list)
    invalid_ids: list[int] = field(default_factory=list)
    uncited_claims: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.cited_ids) and not self.invalid_ids and not self.uncited_claims

    def describe(self) -> str:
        problems = []
        if not self.cited_ids:
            problems.append("The answer has no citations.")
        if self.invalid_ids:
            problems.append(f"These citation numbers do not exist in the context: {self.invalid_ids}.")
        for claim in self.uncited_claims[:5]:
            problems.append(f"This sentence has no citation: {claim!r}")
        return " ".join(problems)


def cited_ids_in(text: str) -> list[int]:
    """Citation numbers in order of first appearance."""
    seen: list[int] = []
    for group in CITATION_RE.findall(text):
        for n in group.split(","):
            value = int(n)
            if value not in seen:
                seen.append(value)
    return seen


def _attach_trailing_citations(text: str) -> str:
    # "Sentence. [1]" -> "Sentence [1]." so the citation stays with its sentence.
    return re.sub(rf"([.!?])({CITATION_GROUP})", lambda m: f"{m.group(2)}{m.group(1)}", text)


def _prose_lines(answer: str) -> str:
    """The answer without fenced code blocks. A fence counts even after a list marker or
    indentation ("2. ```python"), which models produce when they put code inside a list item."""
    kept: list[str] = []
    fence: str | None = None
    for line in answer.splitlines():
        if fence is None:
            opening = re.search(r"`{3,}|~{3,}", line)
            if opening:
                fence = opening.group(0)[0] * 3
                before = line[: opening.start()]
                if LIST_MARKER_RE.sub("", before).strip():
                    kept.append(before)  # prose before a fence that opens mid-line
                continue
            kept.append(line)
        else:
            closing = re.match(r"`{3,}|~{3,}", LIST_MARKER_RE.sub("", line).lstrip())
            if closing and closing.group(0).startswith(fence):
                fence = None
    return "\n".join(kept)


def split_claims(answer: str) -> list[str]:
    """Split an answer into claims: sentences and list items. Code blocks and lead-in lines are not claims."""
    text = _attach_trailing_citations(_prose_lines(answer))
    claims: list[str] = []
    for line in text.splitlines():
        line = LIST_MARKER_RE.sub("", line).strip()
        if not line or line.startswith("#"):
            continue
        for sentence in SENTENCE_SPLIT_RE.split(line):
            sentence = sentence.strip()
            if not sentence:
                continue
            bare = CITATION_RE.sub("", sentence).strip()
            if bare.endswith(":") and not CITATION_RE.search(sentence):
                continue  # lead-in to a list or code block, e.g. "Follow these steps:"
            if len(re.sub(r"[\W_]+", "", bare)) < 3:
                continue  # stray punctuation or a lone citation marker
            claims.append(sentence)
    return claims


def validate_answer(answer: str, num_blocks: int) -> ValidationResult:
    cited = cited_ids_in(answer)
    return ValidationResult(
        cited_ids=cited,
        invalid_ids=[n for n in cited if n < 1 or n > num_blocks],
        uncited_claims=[c for c in split_claims(answer) if not CITATION_RE.search(c)],
    )


def renumber(answer: str, cited_ids: list[int]) -> tuple[str, dict[int, int]]:
    """Renumber citations to 1..n in order of first appearance. Returns new text and old->new mapping."""
    mapping = {old: new for new, old in enumerate(cited_ids, start=1)}

    def repl(match: re.Match) -> str:
        nums = [mapping[int(n)] for n in match.group(1).split(",")]
        return "".join(f"[{n}]" for n in dict.fromkeys(nums))

    return CITATION_RE.sub(repl, answer), mapping
