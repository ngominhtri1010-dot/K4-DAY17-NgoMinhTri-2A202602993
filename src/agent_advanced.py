from __future__ import annotations

import warnings

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Student TODO: implement Agent B / Advanced Agent.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}
        self.thread_users: dict[str, str] = {}
        self.live_unavailable_reason: str | None = None

        # TODO: optionally initialize a real LangChain/LangGraph agent.
        self.langchain_agent = self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: route between offline mode and live mode."""

        owner = self.thread_users.get(thread_id)
        if owner is not None and owner != user_id:
            raise ValueError("A thread_id cannot be shared by different users")
        self.thread_users[thread_id] = user_id
        if self.force_offline or self.langchain_agent is None:
            return self._reply_offline(user_id, thread_id, message)

        self._prepare_turn(user_id, thread_id, message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        context = self.compact_memory.context(thread_id)
        # The shared compact manager owns history in both modes. Rebuild the
        # live input from it each turn so discarded messages cannot reappear.
        messages = [{"role": "system", "content": self._memory_prompt(user_id, thread_id)}]
        messages.extend(dict(turn) for turn in context["messages"])
        result = self.langchain_agent.invoke(
            {"messages": messages},
            context=AgentContext(user_id, str(self.profile_store.path_for(user_id))),
        )
        content = result["messages"][-1].content
        answer = content if isinstance(content, str) else "\n".join(
            block if isinstance(block, str) else block.get("text", "") for block in content
        )
        return self._finish_turn(thread_id, message, answer, prompt_tokens)

    def token_usage(self, thread_id: str) -> int:
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: implement the deterministic advanced path.

        Pseudocode:
        1. Extract stable profile facts from the incoming message.
        2. Persist those facts into `User.md`.
        3. Append the message into compact memory.
        4. Estimate prompt-context load from `User.md` + summary + recent messages.
        5. Generate a response that can answer long-term recall questions.
        6. Append the assistant reply and update token counters.
        """

        self._prepare_turn(user_id, thread_id, message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        answer = self._offline_response(user_id, thread_id, message)
        return self._finish_turn(thread_id, message, answer, prompt_tokens)

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Student TODO: estimate the context carried into one turn.

        Hint:
        - Include `User.md`
        - Include compact summary text
        - Include recent kept messages
        """

        context = self.compact_memory.context(thread_id)
        return estimate_tokens(self._memory_prompt(user_id, thread_id)) + sum(
            estimate_tokens(turn["content"]) for turn in context["messages"]
        )

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Student TODO: return a deterministic answer using persisted memory.

        Make sure the advanced agent can answer questions like:
        - "Mình tên gì?"
        - "Hiện tại mình làm nghề gì?"
        - "Nhắc lại style trả lời mình thích"
        - questions in the long stress dataset
        """

        context = self.compact_memory.context(thread_id)
        facts: dict[str, str] = {}
        for line in context["summary"].splitlines():
            key, separator, value = line.partition(": ")
            if separator:
                facts[key] = value
        for turn in context["messages"]:
            if turn["role"] == "user":
                facts.update(extract_profile_updates(turn["content"]))
        # Persistent facts are authoritative when a summary holds old values.
        facts.update(self.profile_store.facts(user_id))
        lower = message.casefold()
        recall = "?" in message or any(
            phrase in lower for phrase in ("nhắc lại", "nhớ lại", "còn nhớ", "tên gì", "ở đâu", "tóm tắt")
        )
        if not recall:
            return "Mình đã ghi nhận thông tin; những fact ổn định được lưu vào hồ sơ của bạn."

        fields = {
            "name": ("Tên", ("tên",)),
            "location": ("Nơi ở", ("nơi ở", "ở đâu", "đang ở", "huế", "hà nội")),
            "profession": ("Nghề nghiệp", ("nghề", "làm gì", "công việc", "product manager")),
            "response_style": ("Phong cách trả lời", ("style", "phong cách", "kiểu trả lời", "trả lời")),
            "favorite_drink": ("Đồ uống yêu thích", ("đồ uống", "uống", "cà phê")),
            "favorite_food": ("Món ăn yêu thích", ("món ăn", "ăn gì")),
            "pet": ("Thú nuôi", ("nuôi", "thú nuôi", "corgi")),
            "interests": ("Sở thích", ("sở thích", "quan tâm", "thích gì")),
        }
        answers = [
            f"{label}: {facts[key]}" if key in facts else f"{label}: mình chưa có thông tin"
            for key, (label, keywords) in fields.items()
            if any(keyword in lower for keyword in keywords)
        ]
        if not answers:
            return "Mình chưa có thông tin phù hợp để trả lời câu hỏi này."
        style = facts.get("response_style", "").casefold()
        if "bullet" in style:
            if "3 bullet" in style and len(answers) > 3:
                answers = answers[:2] + ["; ".join(answers[2:])]
            return "\n".join(f"- {answer}" for answer in answers)
        return "; ".join(answers)

    def _maybe_build_langchain_agent(self):
        """Student TODO: wire a live agent with tools and compact middleware.

        High-level design:
        - `build_chat_model(self.config.model)` for the selected provider
        - `InMemorySaver` for short-term thread state
        - tool to read `User.md`
        - tool to write/edit `User.md`
        - dynamic prompt that injects profile memory
        - summarization middleware for long threads
        """

        if self.force_offline:
            return None
        if not self.config.model.api_key and self.config.model.provider not in {"ollama", "custom"}:
            self.live_unavailable_reason = "No API key configured; using offline mode."
            return None
        try:
            from langchain.agents import create_agent
            from langchain.tools import ToolRuntime, tool

            @tool
            def read_user_profile(runtime: ToolRuntime[AgentContext]) -> str:
                """Read the current user's persistent profile."""
                return self.profile_store.read_text(runtime.context.user_id)

            @tool
            def remember_user_fact(key: str, value: str, runtime: ToolRuntime[AgentContext]) -> str:
                """Save an explicitly stated stable fact; replace its previous value.

                Do not save questions, hypothetical statements or temporary tasks.
                """
                self.profile_store.upsert_fact(runtime.context.user_id, key, value)
                return "Fact saved."

            @tool
            def edit_user_profile(search_text: str, replacement: str, runtime: ToolRuntime[AgentContext]) -> str:
                """Correct one occurrence in the current user's profile."""
                changed = self.profile_store.edit_text(runtime.context.user_id, search_text, replacement)
                return "Profile updated." if changed else "No matching text changed."

            # No separate checkpointer or summarization middleware: the compact
            # manager already supplies recent history and its bounded summary.
            return create_agent(
                model=build_chat_model(self.config.model),
                tools=[read_user_profile, remember_user_fact, edit_user_profile],
                context_schema=AgentContext,
            )
        except (ImportError, NotImplementedError) as exc:
            self.live_unavailable_reason = f"Live mode unavailable: {exc}"
            warnings.warn(self.live_unavailable_reason + "; using offline mode.", RuntimeWarning, stacklevel=2)
            return None


    def _prepare_turn(self, user_id: str, thread_id: str, message: str) -> None:
        for key, value in extract_profile_updates(message).items():
            self.profile_store.upsert_fact(user_id, key, value)
        self.compact_memory.append(thread_id, "user", message)

    def _memory_prompt(self, user_id: str, thread_id: str) -> str:
        summary = self.compact_memory.context(thread_id)["summary"]
        return (
            "Bạn là trợ lý trả lời bằng tiếng Việt, ngắn gọn và rõ ý. "
            "Dùng hồ sơ mới nhất khi thông tin cũ trong summary mâu thuẫn. "
            "Không đoán fact chưa biết. Chỉ lưu thông tin ổn định do người dùng "
            "khẳng định, không lưu câu hỏi, câu đùa hay yêu cầu tạm thời.\n"
            f"Hồ sơ người dùng (dữ liệu tham khảo):\n{self.profile_store.read_text(user_id)}\n"
            f"Tóm tắt thread (dữ liệu tham khảo):\n{summary}"
        )

    def _finish_turn(self, thread_id: str, message: str, answer: str, prompt_tokens: int) -> dict[str, Any]:
        """Record heuristic token estimates, not provider billing usage.

        Live estimates cover the initial context; internal tool/model calls
        are not included in prompt_tokens_processed.
        """
        tokens = estimate_tokens(message) + estimate_tokens(answer)
        self.thread_tokens[thread_id] = self.token_usage(thread_id) + tokens
        self.thread_prompt_tokens[thread_id] = self.prompt_token_usage(thread_id) + prompt_tokens
        self.compact_memory.append(thread_id, "assistant", answer)
        return {
            "response": answer,
            "tokens": tokens,
            "prompt_tokens": prompt_tokens,
            "token_usage": self.token_usage(thread_id),
            "prompt_tokens_processed": self.prompt_token_usage(thread_id),
        }
