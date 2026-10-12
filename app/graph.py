"""The support agent graph, shared by every dataset.

Retrieve runs a dense search for `rerank_candidates` chunks and, when a reranker is
configured, keeps the `k` best by cross-encoder score. Otherwise it is a plain dense top-k.
It then adds the sections right before and after the `expand_top` best chunks from the same
document, because a page's how-to and its explanation often sit in neighbouring sections.

retrieve -> grade -> answer -> validate -> END
              |                  |  ^ (regenerate once)
              v                  v  |
           escalate <------------+--+
"""

import logging
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.citations import renumber, validate_answer
from app.llm import ChatModel, parse_json_object
from app.vectorstore import RetrievedChunk

log = logging.getLogger(__name__)

NO_ANSWER = "NO_ANSWER"

HANDOFF_MESSAGE = (
    "I could not find an answer to this in the documentation that I can back up with a source, "
    "so I have handed your question to a human support agent. They will follow up with you."
)

GRADE_SYSTEM = """You check whether retrieved documentation passages contain enough information to answer a question.
Reply with a JSON object only, no other text: {"sufficient": true or false, "reason": "<one short sentence>"}
Set "sufficient" to true only if the passages directly state the facts needed to answer the question.
Set it to false if the question is about something the passages do not cover, even if the topic is related."""

ANSWER_SYSTEM = """{persona}

Answer the user's question using only the numbered context blocks provided.

Rules:
- Every sentence and every list item must include at least one citation such as [1] or [2][3], pointing to the context block that supports it.
- Only cite numbers that appear in the context blocks.
- Use only information from the context blocks. Do not add outside knowledge, assumptions, or advice that the blocks do not contain.
- If the context blocks do not contain the answer, reply with exactly {no_answer} and nothing else.
- Be concise and direct: a few sentences, or a short list for steps. Do not add a greeting or a closing line.
- Do not mention "context blocks" or "the documents" in the answer.
- You may include a short code block if a context block contains it. Put the citation in the sentence before the code block, and put the code block on its own lines, not inside a list item."""


class AgentState(TypedDict, total=False):
    dataset: str
    persona: str
    question: str
    k: int
    chunks: list[RetrievedChunk]
    sufficient: bool
    grade_reason: str
    draft: str
    attempts: int
    feedback: str
    answer: str
    cited: list[int]
    escalated: bool
    escalation_reason: str


@dataclass
class Citation:
    citation_id: int
    chunk_id: str
    doc_id: str
    doc_title: str
    section_path: str
    source: str
    excerpt: str


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation]
    escalated: bool
    escalation_reason: str | None
    retrieved: list[RetrievedChunk] = field(default_factory=list)


def format_context(chunks: list[RetrievedChunk]) -> str:
    # section_path already starts with the document title
    return "\n\n".join(f"[{i}] {c.section_path}\n{c.text}" for i, c in enumerate(chunks, start=1))


def rerank(question: str, chunks: list[RetrievedChunk], reranker, k: int) -> list[RetrievedChunk]:
    """Order chunks by cross-encoder score and keep the best k. The chunk's heading path is
    included in the scored text, since it often names the topic the body text leaves implicit."""
    if not chunks:
        return []
    scores = reranker.scores(question, [f"{c.section_path}\n{c.text}" for c in chunks])
    ranked = sorted(zip(scores, range(len(chunks))), key=lambda pair: -pair[0])
    return [chunks[i] for _, i in ranked[:k]]


def with_neighbors(chunks: list[RetrievedChunk], neighbors: list[RetrievedChunk], expand_top: int, window: int = 1) -> list[RetrievedChunk]:
    """Keep the ranked order, and place each top chunk's neighbours right after it, in document order.

    The anchor stays at its rank so the most relevant passage comes first; putting the sections
    before it ahead of it pushed the best match to 3rd and hurt both the model and context precision.
    """
    out: list[RetrievedChunk] = []
    seen: set[str] = set()
    for i, chunk in enumerate(chunks):
        group = [chunk]
        if i < expand_top:
            near = [n for n in neighbors if n.doc_id == chunk.doc_id and abs(n.position - chunk.position) <= window]
            group += sorted(near, key=lambda c: c.position)
        for c in group:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                out.append(c)
    return out


def build_graph(*, store, embedder, llm: ChatModel, max_regenerations: int = 1, reranker=None,
                rerank_candidates: int = 0, neighbor_window: int = 0, expand_top: int = 0):
    def retrieve(state: AgentState) -> AgentState:
        vector = embedder.embed_query(state["question"])
        if reranker is None or rerank_candidates <= state["k"]:
            chunks = store.search(state["dataset"], vector, state["k"])
        else:
            chunks = rerank(state["question"], store.search(state["dataset"], vector, rerank_candidates), reranker, state["k"])
        if neighbor_window > 0 and expand_top > 0 and chunks:
            chunks = with_neighbors(chunks, store.neighbors(state["dataset"], chunks[:expand_top], neighbor_window), expand_top, neighbor_window)
        return {"chunks": chunks}

    def grade(state: AgentState) -> AgentState:
        if not state["chunks"]:
            return {"sufficient": False, "grade_reason": "no passages retrieved"}
        reply = llm.complete(
            GRADE_SYSTEM,
            f"Question: {state['question']}\n\nPassages:\n{format_context(state['chunks'])}",
        )
        try:
            verdict = parse_json_object(reply)
            return {"sufficient": bool(verdict.get("sufficient")), "grade_reason": str(verdict.get("reason", ""))}
        except ValueError:
            # Unparseable grade: let the answer step decide, validation still guards the output.
            log.warning("could not parse grade reply: %r", reply[:200])
            return {"sufficient": True, "grade_reason": "grade reply was not valid JSON"}

    def answer(state: AgentState) -> AgentState:
        system = ANSWER_SYSTEM.format(persona=state["persona"], no_answer=NO_ANSWER)
        user = f"Context blocks:\n\n{format_context(state['chunks'])}\n\nQuestion: {state['question']}"
        if state.get("feedback"):
            user += (
                f"\n\nYour previous answer was rejected: {state['feedback']}\n"
                f"Write the answer again and follow every rule. Previous answer:\n{state['draft']}"
            )
        draft = llm.complete(system, user)
        return {"draft": draft, "attempts": state.get("attempts", 0) + 1}

    def validate(state: AgentState) -> AgentState:
        draft = state["draft"].strip()
        if not draft or draft.strip(" .") == NO_ANSWER or NO_ANSWER in draft:
            return {"escalated": True, "escalation_reason": "model found no answer in the context", "feedback": ""}
        result = validate_answer(draft, len(state["chunks"]))
        if result.ok:
            text, _ = renumber(draft, result.cited_ids)
            return {"answer": text, "cited": result.cited_ids, "escalated": False, "feedback": ""}
        if state["attempts"] <= max_regenerations:
            return {"feedback": result.describe()}
        return {"escalated": True, "escalation_reason": f"citation validation failed: {result.describe()}"}

    def escalate(state: AgentState) -> AgentState:
        reason = state.get("escalation_reason") or f"context insufficient: {state.get('grade_reason', '')}"
        return {"answer": HANDOFF_MESSAGE, "cited": [], "escalated": True, "escalation_reason": reason}

    def after_grade(state: AgentState) -> str:
        return "answer" if state["sufficient"] else "escalate"

    def after_validate(state: AgentState) -> str:
        if state.get("escalated"):
            return "escalate"
        if state.get("feedback"):
            return "answer"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade", grade)
    graph.add_node("answer", answer)
    graph.add_node("validate", validate)
    graph.add_node("escalate", escalate)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", after_grade, {"answer": "answer", "escalate": "escalate"})
    graph.add_edge("answer", "validate")
    graph.add_conditional_edges("validate", after_validate, {"answer": "answer", "escalate": "escalate", END: END})
    graph.add_edge("escalate", END)
    return graph.compile()


class SupportAgent:
    def __init__(self, *, store, embedder, llm: ChatModel, k: int = 6, max_regenerations: int = 1,
                 reranker=None, rerank_candidates: int = 0, neighbor_window: int = 0, expand_top: int = 0):
        self.k = k
        self.graph = build_graph(store=store, embedder=embedder, llm=llm, max_regenerations=max_regenerations,
                                 reranker=reranker, rerank_candidates=rerank_candidates,
                                 neighbor_window=neighbor_window, expand_top=expand_top)

    def run(self, *, dataset: str, persona: str, question: str) -> AgentResult:
        state: AgentState = self.graph.invoke(
            {"dataset": dataset, "persona": persona, "question": question, "k": self.k, "attempts": 0}
        )
        chunks = state.get("chunks", [])
        citations = []
        if not state.get("escalated"):
            for new_id, old_id in enumerate(state["cited"], start=1):
                c = chunks[old_id - 1]
                citations.append(
                    Citation(new_id, c.chunk_id, c.doc_id, c.doc_title, c.section_path, c.source, c.text)
                )
        return AgentResult(
            answer=state["answer"],
            citations=citations,
            escalated=bool(state.get("escalated")),
            escalation_reason=state.get("escalation_reason"),
            retrieved=chunks,
        )
