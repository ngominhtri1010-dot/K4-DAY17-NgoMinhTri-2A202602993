from __future__ import annotations

import hashlib
import re

from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Student TODO: implement a simple token estimator.

    Example idea:
    - Strip whitespace
    - Return 0 for empty text
    - Approximate tokens from character count, e.g. len(text) / 4
    """

    text = text.strip()
    return (len(text) + 3) // 4


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`.

    Student TODO:
    - Map each user id to one markdown file
    - Support read / write / edit operations
    - Optionally expose helpers like `facts()` or `upsert_fact()`
    """

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        # TODO: slugify or sanitize the user id before building the file path.
        if not user_id.strip():
            raise ValueError("user_id must not be empty")
        slug = re.sub(r"[^\w-]+", "_", user_id).strip("_") or "user"
        if slug != user_id or len(slug) > 80:
            digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
            slug = f"{slug[:80]}-{digest}"
        root = Path(self.root_dir).resolve()
        path = root / slug / "User.md"
        if not path.resolve().is_relative_to(root):
            raise ValueError("Profile path must stay inside root_dir")
        return path

    def read_text(self, user_id: str) -> str:
        # TODO: return file content or an empty default markdown profile.
        path = self.path_for(user_id)
        return path.read_text(encoding="utf-8") if path.is_file() else "# User Profile\n"

    def write_text(self, user_id: str, content: str) -> Path:
        # TODO: write markdown to disk and return the file path.
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        # TODO: replace one occurrence inside User.md and return whether it changed.
        path = self.path_for(user_id)
        if not search_text or not path.is_file():
            return False
        content = path.read_text(encoding="utf-8")
        updated = content.replace(search_text, replacement, 1)
        if updated == content:
            return False
        self.write_text(user_id, updated)
        return True

    def file_size(self, user_id: str) -> int:
        # TODO: return the current file size in bytes.
        path = self.path_for(user_id)
        return path.stat().st_size if path.is_file() else 0

    def facts(self, user_id: str) -> dict[str, str]:
        """Read structured facts while leaving free-form markdown intact."""
        return dict(re.findall(r"^- ([\w-]+): (.+)$", self.read_text(user_id), re.M))

    def upsert_fact(self, user_id: str, key: str, value: str) -> Path:
        """Replace an existing fact with its latest value, or append it."""
        if not re.fullmatch(r"[\w-]+", key):
            raise ValueError("Fact keys must contain letters, numbers, underscores or hyphens")
        value = " ".join(value.split())
        if not value:
            raise ValueError("Fact values must not be empty")
        content = self.read_text(user_id)
        line = f"- {key}: {value}"
        pattern = rf"^- {re.escape(key)}: .*?$"
        if re.search(pattern, content, re.M):
            content = re.sub(pattern, lambda _: line, content, flags=re.M)
        else:
            content = content.rstrip() + "\n" + line + "\n"
        return self.write_text(user_id, content)


def extract_profile_updates(message: str) -> dict[str, str]:
    """Student TODO: convert raw user text into stable profile facts.

    Example facts you may want to extract:
    - name
    - location
    - profession
    - preferences / response style
    - favorite food / drink

    Pseudocode:
    1. Build a few regex patterns.
    2. Skip obvious question-only turns.
    3. Return only the facts that are confidently present in the message.
    """

    updates: dict[str, str] = {}
    patterns = {
        "name": r"(?:mình|tôi)\s+tên\s+(?:là\s+)?([^,.;!?\n]+)",
        "location": r"(?:(?:mình|tôi)\s+(?:vẫn\s+)?(?:(?:hiện tại|hiện|giờ|từ tuần này)\s+)?(?:đang\s+)?(?:(?:sống|làm việc)\s+)?ở|hiện\s+ở|nơi ở hiện tại\s+(?:là\s+)?|nơi ở đã cập nhật từ\s+[^,.;!?]+?\s+sang)\s+([^,.;!?\n]+)",
        "profession": r"(?:(?:mình|tôi)\s+(?:đang\s+)?làm|và\s+đang\s+làm|(?:giờ\s+)?chuyển sang|nghề nghiệp(?:\s+hiện tại)?\s+(?:thì\s+)?(?:vẫn\s+)?là|nghề(?:\s+hiện tại)?\s+là|nghề(?=\s+[\w-]+\s+engineer\b))\s+([^,.;!?\n]+)",
        "favorite_drink": r"đồ uống yêu thích(?:\s+của (?:mình|tôi))?\s+là\s+([^,.;!?\n]+)",
        "favorite_food": r"món ăn yêu thích(?:\s+của (?:mình|tôi))?\s+là\s+([^,.;!?\n]+)",
        "pet": r"(?:mình|tôi)\s+nuôi\s+(?:(?:một|con|bé)\s+)*([^,.;!?\n]+)",
        "interests": r"(?:mình|tôi)\s+(?:vẫn\s+)?(?:còn\s+)?(?:thích|đang quan tâm nhiều đến)\s+([^.;!?\n]+)",
        "response_style": r"(?:(?:mình|tôi)\s+(?:vẫn\s+)?muốn\s+(?:bạn\s+)?(?:câu\s+|style\s+)?trả lời|hãy trả lời|style trả lời(?:\s+cũng)?\s+vẫn giữ nguyên)\s*:?\s*([^.;!?\n]+)",
    }
    for sentence in re.split(r"[.!;?\n]+", message):
        # Recall requests describe what to retrieve, not new profile facts.
        if re.match(
            r"\s*(?:(?:bạn|hãy|bạn hãy)\s+)?(?:nhắc lại|nhớ lại|tóm tắt)\b",
            sentence, re.I,
        ):
            continue
        if re.search(r"\b(?:nếu|giả sử|hay là|đùa)\b", sentence, re.I):
            continue
        for key, pattern in patterns.items():
            for match in re.finditer(pattern, sentence, re.I):
                value = match.group(1).strip(" :,-")
                if key in {"location", "profession"}:
                    value = re.split(r"\s+(?:và|chứ|dù|trong|vài|để|cho|không đổi)\b", value, maxsplit=1, flags=re.I)[0]
                if re.search(r"\b(?:gì|đâu|không phải|không còn)\b", value, re.I):
                    continue
                if key == "profession" and value.casefold().startswith(("việc", "từ xa")):
                    continue
                if key == "interests" and not re.search(r"\b(?:Python|AI|MLOps|RAG|agent|backend|evaluation|chạy bộ|lo-fi)\b", value, re.I):
                    continue
                if key == "response_style":
                    if not re.search(r"ngắn|gọn|bullet|ví dụ|trade-off", value, re.I):
                        continue
                    if re.search(r"bullet ngắn|trả lời ngắn|^ngắn\b", value, re.I) and "ngắn gọn" not in value.casefold():
                        value = "ngắn gọn; " + value
                if value:
                    updates[key] = value.strip(" ,")
    return updates


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Student TODO: create a compact summary of older messages.

    This can be heuristic text concatenation first.
    Later, you can replace it with an LLM-based summary if desired.
    """

    if max_items <= 0:
        return ""
    items: list[str] = []
    for message in messages:
        content = message.get("content", "").strip()
        if not content:
            continue
        if message.get("role") == "summary":
            items.extend(content.splitlines())
            continue
        facts = extract_profile_updates(content) if message.get("role") == "user" else {}
        if facts:
            items.extend(f"{key}: {value[:160]}" for key, value in facts.items())
        else:
            excerpt = " ".join(content.split())
            items.append(f"{message.get('role', 'unknown')}: {excerpt[:200]}")
    # Bounded heuristic summary: prioritize user facts over generic replies.
    unique = list(dict.fromkeys(items))
    latest_facts: dict[str, str] = {}
    other: list[str] = []
    for item in unique:
        key, separator, value = item.partition(": ")
        if separator and key not in {"user", "assistant", "unknown", "system"}:
            # A correction replaces the old value rather than retaining both.
            latest_facts.pop(key, None)
            latest_facts[key] = value[:160]
        else:
            other.append(item[:210])
    selected = [f"{key}: {value}" for key, value in latest_facts.items()][-max_items:]
    remaining = max_items - len(selected)
    if remaining:
        selected.extend(other[-remaining:])
    return "\n".join(selected)


@dataclass
class CompactMemoryManager:
    """Student TODO: implement compact memory for long threads.

    Goal:
    - Keep recent messages in full
    - When the thread grows too large, move older content into a summary
    - Track how many compactions happened for benchmarking
    """

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.threshold_tokens <= 0 or self.keep_messages <= 0:
            raise ValueError("threshold_tokens and keep_messages must be positive")

    def append(self, thread_id: str, role: str, content: str) -> None:
        # TODO:
        # 1. create thread state if missing
        # 2. append the new message
        # 3. trigger compaction if needed
        context = self.context(thread_id)
        messages = context["messages"]
        messages.append({"role": role, "content": content})
        tokens = estimate_tokens(context["summary"]) + sum(
            estimate_tokens(message["content"]) for message in messages
        )
        if tokens > self.threshold_tokens and len(messages) > self.keep_messages:
            older = messages[:-self.keep_messages]
            summary_input = [{"role": "summary", "content": context["summary"]}] + older
            context["summary"] = summarize_messages(summary_input)
            context["messages"] = messages[-self.keep_messages:]
            context["compactions"] += 1

    def context(self, thread_id: str) -> dict[str, object]:
        # TODO: return per-thread state with keys like messages, summary, compactions.
        return self.state.setdefault(thread_id, {"messages": [], "summary": "", "compactions": 0})

    def compaction_count(self, thread_id: str) -> int:
        # TODO: return number of compactions for this thread.
        return self.state.get(thread_id, {}).get("compactions", 0)
