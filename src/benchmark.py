from __future__ import annotations

import json
import unicodedata
from uuid import uuid4
from tempfile import TemporaryDirectory

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Student TODO: read JSON conversations from disk."""

    with path.open(encoding="utf-8") as handle:
        conversations = json.load(handle)
    if not isinstance(conversations, list):
        raise ValueError("Dataset must be a list of conversations")
    ids: set[str] = set()
    for index, conversation in enumerate(conversations):
        if not isinstance(conversation, dict):
            raise ValueError(f"Conversation {index} must be an object")
        for key in ("id", "user_id"):
            if not isinstance(conversation.get(key), str) or not conversation[key].strip():
                raise ValueError(f"Conversation {index} needs a non-empty {key}")
        if conversation["id"] in ids:
            raise ValueError(f"Duplicate conversation id: {conversation['id']}")
        ids.add(conversation["id"])
        turns = conversation.get("turns")
        questions = conversation.get("recall_questions")
        if not isinstance(turns, list) or not all(isinstance(turn, str) for turn in turns):
            raise ValueError(f"Conversation {index} needs a list of text turns")
        if not isinstance(questions, list):
            raise ValueError(f"Conversation {index} needs recall_questions")
        for question in questions:
            if not isinstance(question, dict) or not isinstance(question.get("question"), str):
                raise ValueError(f"Invalid recall question in conversation {index}")
            expected = question.get("expected_contains")
            if not isinstance(expected, list) or not expected or not all(
                isinstance(item, str) and item.strip() for item in expected
            ):
                raise ValueError(f"Recall question in conversation {index} needs non-empty expected strings")
    return conversations


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def recall_points(answer: str, expected: list[str]) -> float:
    """Student TODO: return 0 / 0.5 / 1 depending on how many expected facts appear."""

    if not expected:
        return 0.0
    normalized = _normalize(answer)
    matches = sum(_normalize(item) in normalized for item in expected)
    if matches == len(expected):
        return 1.0
    return 0.5 if matches else 0.0


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Student TODO: add a lightweight quality score for offline mode."""

    # Offline proxy: fraction of expected facts present. This is not a
    # judge-model score and does not assess correctness beyond substring hits.
    if not answer.strip() or not expected:
        return 0.0
    normalized = _normalize(answer)
    return sum(_normalize(item) in normalized for item in expected) / len(expected)


def run_agent_benchmark(agent_name: str, agent, conversations: list[dict[str, Any]], config) -> BenchmarkRow:
    """Student TODO: evaluate one agent over many conversations.

    Pseudocode:
    1. Feed all turns to the agent.
    2. Track `agent tokens only`.
    3. Track `prompt tokens processed`.
    4. Ask recall questions in a fresh thread.
    5. Compute average recall and quality.
    6. Record memory file growth and compaction count.
    """

    run_id = uuid4().hex
    user_ids = {conversation["user_id"] for conversation in conversations}
    size_method = getattr(agent, "memory_file_size", None)
    initial_bytes = sum(size_method(user_id) for user_id in user_ids) if size_method else 0
    thread_ids: list[str] = []
    recall_scores: list[float] = []
    quality_scores: list[float] = []

    # Evaluate recall immediately after each conversation so later corrections
    # do not invalidate the expected facts of an earlier conversation.
    for index, conversation in enumerate(conversations):
        user_id = conversation["user_id"]
        thread_id = f"{run_id}:conversation:{index}"
        thread_ids.append(thread_id)
        for message in conversation["turns"]:
            agent.reply(user_id, thread_id, message)
        for question_index, question in enumerate(conversation["recall_questions"]):
            # Each question has a fresh thread, avoiding recall-question leakage.
            recall_thread = f"{run_id}:recall:{index}:{question_index}"
            thread_ids.append(recall_thread)
            result = agent.reply(user_id, recall_thread, question["question"])
            answer = result["response"]
            expected = question["expected_contains"]
            recall_scores.append(recall_points(answer, expected))
            quality_scores.append(heuristic_quality(answer, expected))

    final_bytes = sum(size_method(user_id) for user_id in user_ids) if size_method else 0
    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=sum(agent.token_usage(thread_id) for thread_id in thread_ids),
        prompt_tokens_processed=sum(agent.prompt_token_usage(thread_id) for thread_id in thread_ids),
        recall_score=sum(recall_scores) / len(recall_scores) if recall_scores else 0.0,
        response_quality=sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
        memory_growth_bytes=final_bytes - initial_bytes,
        compactions=sum(agent.compaction_count(thread_id) for thread_id in thread_ids),
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Student TODO: print a markdown table or tabulated output."""

    headers = [
        "Agent", "Agent tokens only", "Prompt tokens processed",
        "Cross-session recall", "Response quality", "Memory growth (bytes)", "Compactions",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        values = [
            row.agent_name.replace("|", r"\|").replace("\n", " "),
            str(row.agent_tokens_only), str(row.prompt_tokens_processed),
            f"{row.recall_score:.1%}", f"{row.response_quality:.1%}",
            str(row.memory_growth_bytes), str(row.compactions),
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def main() -> None:
    """Student TODO: run both benchmark suites.

    Required benchmark sections:
    - Standard benchmark from `data/conversations.json`
    - Long-context stress benchmark from `data/advanced_long_context.json`

    Compare:
    - Baseline
    - Advanced

    Keep the same output columns as the solved lab:
    - Agent tokens only
    - Prompt tokens processed
    - Cross-session recall
    - Response quality
    - Memory growth (bytes)
    - Compactions
    """

    config = load_config(Path(__file__).resolve().parent.parent)

    # TODO:
    # - load both datasets from root/data
    # - initialize baseline and advanced agents
    # - run benchmarks
    # - print comparison tables
    print("Offline benchmark: heuristic token estimates; counts include conversation and recall turns.")
    print("Recall: 0 / 0.5 / 1 per question. Quality: fraction of expected strings found, not an LLM judge score.")
    print("Each suite starts with fresh agents and an isolated temporary memory directory.\n")
    for title, filename in (
        ("Standard Benchmark", "conversations.json"),
        ("Long-Context Stress Benchmark", "advanced_long_context.json"),
    ):
        conversations = load_conversations(config.data_dir / filename)
        with TemporaryDirectory(prefix="memory-benchmark-") as temporary:
            suite_config = replace(config, state_dir=Path(temporary))
            rows = [
                run_agent_benchmark("Baseline", BaselineAgent(suite_config, force_offline=True), conversations, suite_config),
                run_agent_benchmark("Advanced", AdvancedAgent(suite_config, force_offline=True), conversations, suite_config),
            ]
        print(f"## {title}\n")
        print(format_rows(rows))
        print()


if __name__ == "__main__":
    main()
