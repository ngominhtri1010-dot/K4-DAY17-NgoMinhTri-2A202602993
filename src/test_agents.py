from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import CompactMemoryManager, UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Student TODO: build an isolated config for tests."""

    # Hint:
    # - point `state_dir` into tmp_path
    # - reduce compact threshold so compaction happens quickly in tests
    # Construct directly so external .env and environment variables cannot
    # redirect writes or alter thresholds during these offline tests.
    model = ProviderConfig(provider="openai", model_name="offline-test", temperature=0.0)
    return LabConfig(
        base_dir=tmp_path,
        data_dir=Path(__file__).resolve().parent.parent / "data",
        state_dir=tmp_path / "state",
        compact_threshold_tokens=300,
        compact_keep_messages=4,
        model=model,
        judge_model=replace(model),
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Student TODO: verify `User.md` can be created, updated, and edited."""

    store = UserProfileStore(make_config(tmp_path).state_dir / "profiles")
    assert store.file_size("demo") == 0
    assert not store.path_for("demo").exists()

    content = "# User\n- location: Huế\n- note: Huế\n"
    path = store.write_text("demo", content)
    assert path.name == "User.md"
    assert path.read_text(encoding="utf-8") == content
    assert store.read_text("demo") == content
    assert store.file_size("demo") == len(content.encode("utf-8"))

    assert store.edit_text("demo", "Huế", "Đà Nẵng")
    assert store.read_text("demo") == "# User\n- location: Đà Nẵng\n- note: Huế\n"
    unchanged = store.read_text("demo")
    assert not store.edit_text("demo", "not-present", "replacement")
    assert not store.edit_text("demo", "", "replacement")
    assert store.read_text("demo") == unchanged

    # Data survives a new store instance and stays isolated by user.
    assert UserProfileStore(store.root_dir).read_text("demo") == unchanged
    store.write_text("other", "# Another user\n")
    assert store.read_text("demo") == unchanged


def test_compact_trigger(tmp_path: Path) -> None:
    """Student TODO: verify long threads trigger compaction."""

    config = make_config(tmp_path)
    memory = CompactMemoryManager(config.compact_threshold_tokens, config.compact_keep_messages)
    memory.append("short", "user", "Xin chào")
    assert memory.compaction_count("short") == 0
    assert memory.context("short")["summary"] == ""

    turns = [{"role": "user", "content": f"Đoạn {index}: " + "ngữ cảnh dài " * 120} for index in range(12)]
    for turn in turns:
        memory.append("long", turn["role"], turn["content"])

    assert memory.compaction_count("long") > 1
    assert memory.context("long")["summary"].strip()
    assert memory.context("long")["messages"] == turns[-config.compact_keep_messages:]
    assert memory.context("short")["messages"] == [{"role": "user", "content": "Xin chào"}]
    assert memory.compaction_count("unknown") == 0


def test_cross_session_recall(tmp_path: Path) -> None:
    """Student TODO: verify advanced remembers across sessions and baseline does not."""

    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    for message in ("Mình tên là DũngCT.", "Mình đang ở Huế.", "Mình đang ở Đà Nẵng."):
        baseline.reply("demo", "learn", message)
        advanced.reply("demo", "learn", message)

    question = "Nhắc lại tên và nơi ở hiện tại của mình?"
    same_thread = baseline.reply("demo", "learn", question)["response"]
    assert "DũngCT" in same_thread and "Đà Nẵng" in same_thread
    forgotten = baseline.reply("demo", "new", question)["response"]
    assert "DũngCT" not in forgotten and "Đà Nẵng" not in forgotten

    # A new agent instance rules out recall from process-local thread memory.
    restored = AdvancedAgent(config, force_offline=True)
    recalled = restored.reply("demo", "new", question)["response"]
    assert "DũngCT" in recalled
    assert "Đà Nẵng" in recalled
    assert "Huế" not in recalled
    assert restored.memory_file_size("demo") > 0
    other_user = restored.reply("other", "other-thread", question)["response"]
    assert "DũngCT" not in other_user and "Đà Nẵng" not in other_user


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Student TODO: compare prompt load of baseline vs advanced on a long thread."""

    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)
    # Same input and deterministic offline responses; length forces repeated
    # compaction while the baseline keeps its full history.
    for index in range(24):
        message = f"Đoạn hội thoại {index}: " + "Nội dung kỹ thuật dùng để đánh giá tải ngữ cảnh. " * 100
        baseline.reply("demo", "long", message)
        advanced.reply("demo", "long", message)

    assert baseline.compaction_count("long") == 0
    assert advanced.compaction_count("long") > 1
    assert baseline.prompt_token_usage("long") > 0
    assert 0 < advanced.prompt_token_usage("long") < baseline.prompt_token_usage("long") * 0.5
    assert len(advanced.compact_memory.context("long")["messages"]) <= config.compact_keep_messages
    assert advanced.token_usage("long") > 0


@pytest.mark.parametrize("user_id", ["../escape", "a/b", "a b", "a" * 200])
def test_profile_path_stays_inside_root(tmp_path: Path, user_id: str) -> None:
    store = UserProfileStore(tmp_path / "profiles")
    path = store.write_text(user_id, "# User\n")
    assert path.resolve().is_relative_to(store.root_dir.resolve())
    assert path.read_text(encoding="utf-8") == "# User\n"
    assert store.path_for("a/b") != store.path_for("a b")


def test_upsert_replaces_old_fact(tmp_path: Path) -> None:
    store = UserProfileStore(tmp_path / "profiles")
    store.upsert_fact("demo", "location", "Huế")
    store.upsert_fact("demo", "location", "Đà Nẵng")
    assert store.facts("demo") == {"location": "Đà Nẵng"}
    assert "Huế" not in store.read_text("demo")


@pytest.mark.parametrize("agent_class", [BaselineAgent, AdvancedAgent])
def test_thread_cannot_be_shared_between_users(tmp_path: Path, agent_class) -> None:
    agent = agent_class(make_config(tmp_path), force_offline=True)
    agent.reply("first", "shared", "Mình tên là DũngCT.")
    with pytest.raises(ValueError, match="thread_id"):
        agent.reply("second", "shared", "Mình tên gì?")


def test_profile_recall_matches_dataset_fields(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    agent = AdvancedAgent(config, force_offline=True)
    for message in (
        "Mình tên là DũngCT.",
        "Mình ở Huế và đang làm backend engineer cho startup AI.",
        "Mình không còn làm backend engineer nữa, giờ chuyển sang MLOps engineer.",
        "Mình nuôi một bé corgi tên Bơ.",
        "Mình đang quan tâm nhiều đến Python, AI agent và benchmark memory.",
        "Mình thích markdown vì dễ mở.",
        "Mình muốn bạn trả lời ngắn gọn và có ví dụ thực chiến.",
    ):
        agent.reply("demo", "learn", message)
    restored = AdvancedAgent(config, force_offline=True)
    answer = restored.reply("demo", "recall", "Tóm tắt tên, nghề hiện tại, mối quan tâm, thú nuôi và style trả lời.")["response"]
    for fact in ("DũngCT", "Huế", "MLOps engineer", "Python", "AI", "corgi", "ngắn gọn"):
        if fact != "Huế":
            assert fact in answer
    assert "backend engineer" not in answer
    assert restored.profile_store.facts("demo")["location"] == "Huế"


@pytest.mark.parametrize("value, expected", [
    (" OPENAI ", "openai"), ("anthorpic", "anthropic"),
    ("google", "gemini"), ("ollama", "ollama"), ("open-router", "openrouter"),
])
def test_normalize_provider(value: str, expected: str) -> None:
    from model_provider import normalize_provider

    assert normalize_provider(value) == expected


def test_unknown_provider_is_rejected() -> None:
    from model_provider import normalize_provider

    with pytest.raises(ValueError, match="Unsupported provider"):
        normalize_provider("unknown")
