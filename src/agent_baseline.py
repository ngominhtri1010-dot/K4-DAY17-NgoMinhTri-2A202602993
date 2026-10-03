from __future__ import annotations

import warnings

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Student TODO: implement Agent A.

    Requirements:
    - Within-session memory only
    - No persistent `User.md`
    - Should forget long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.thread_users: dict[str, str] = {}
        self.live_unavailable_reason: str | None = None

        # TODO: optionally initialize a real LangChain/LangGraph agent when dependencies exist.
        self.langchain_agent = self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: return the agent response and token accounting.

        Pseudocode:
        - If a live agent exists, call the live path.
        - Otherwise use a deterministic offline path.
        """

        owner = self.thread_users.get(thread_id)
        if owner is not None and owner != user_id:
            raise ValueError("A thread_id cannot be shared by different users")
        self.thread_users[thread_id] = user_id
        if self.force_offline or self.langchain_agent is None:
            return self._reply_offline(thread_id, message)

        result = self.langchain_agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        content = result["messages"][-1].content
        if isinstance(content, str):
            answer = content
        else:
            answer = "\n".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in content
            )
        return self._record_turn(thread_id, message, answer)

    def token_usage(self, thread_id: str) -> int:
        # TODO: return cumulative agent token count for one thread.
        session = self.sessions.get(thread_id)
        return session.token_usage if session else 0

    def prompt_token_usage(self, thread_id: str) -> int:
        # TODO: estimate how much prompt context this baseline kept processing.
        session = self.sessions.get(thread_id)
        return session.prompt_tokens_processed if session else 0

    def compaction_count(self, thread_id: str) -> int:
        # Baseline has no compact memory.
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Student TODO: implement a simple offline behavior.

        Suggested behavior:
        - Store the new user message in the session
        - Generate a short deterministic reply
        - Update token counts
        - Never remember facts across different thread ids
        """

        session = self.sessions.setdefault(thread_id, SessionState())
        facts: dict[str, str] = {}
        # Rebuild facts from this thread only; no persistent profile is used.
        for turn in session.messages + [{"role": "user", "content": message}]:
            if turn["role"] == "user":
                facts.update(extract_profile_updates(turn["content"]))

        requested: list[str] = []
        lower = message.casefold()
        recall = "?" in message or any(
            phrase in lower for phrase in ("nhắc lại", "nhớ lại", "còn nhớ", "tên gì", "ở đâu", "tóm tắt")
        )
        if recall:
            for key, keywords in {
                "name": ("tên",),
                "location": ("nơi ở", "ở đâu", "đang ở", "huế", "hà nội"),
                "profession": ("nghề", "làm gì", "công việc", "product manager"),
                "response_style": ("style", "phong cách", "kiểu trả lời", "trả lời"),
                "favorite_drink": ("đồ uống", "uống", "cà phê"),
                "favorite_food": ("món ăn", "ăn gì"),
                "pet": ("nuôi", "thú nuôi", "corgi"),
                "interests": ("sở thích", "quan tâm", "thích gì"),
            }.items():
                if any(keyword in lower for keyword in keywords):
                    requested.append(key)
            labels = {
                "name": "Tên", "location": "Nơi ở", "profession": "Nghề nghiệp",
                "response_style": "Phong cách trả lời", "favorite_drink": "Đồ uống yêu thích",
                "favorite_food": "Món ăn yêu thích", "interests": "Sở thích", "pet": "Thú nuôi",
            }
            answer = "; ".join(
                f"{labels[key]}: {facts[key]}" if key in facts
                else f"{labels[key]}: bạn chưa cung cấp trong thread này"
                for key in requested
            ) or "Mình chưa có thông tin phù hợp trong thread này."
        else:
            answer = "Mình đã ghi nhận thông tin trong cuộc trò chuyện này."
        return self._record_turn(thread_id, message, answer)

    def _maybe_build_langchain_agent(self):
        """Student TODO: optionally wire `create_agent` + `InMemorySaver` here.

        Use `build_chat_model(self.config.model)` so the baseline can run with any supported provider.
        """

        if self.force_offline:
            return None
        if not self.config.model.api_key and self.config.model.provider not in {"ollama", "custom"}:
            self.live_unavailable_reason = "No API key configured; using offline mode."
            return None
        try:
            from langchain.agents import create_agent
            from langgraph.checkpoint.memory import InMemorySaver

            model = build_chat_model(self.config.model)
            return create_agent(
                model=model,
                tools=[],
                checkpointer=InMemorySaver(),
                system_prompt=(
                    "Bạn là trợ lý trả lời bằng tiếng Việt, ngắn gọn và rõ ý. "
                    "Chỉ dùng thông tin trong thread hiện tại. Nếu chưa có thông tin, "
                    "hãy nói rõ; không đoán hồ sơ người dùng."
                ),
            )
        except (ImportError, NotImplementedError) as exc:
            self.live_unavailable_reason = f"Live mode unavailable: {exc}"
            warnings.warn(self.live_unavailable_reason + "; using offline mode.", RuntimeWarning, stacklevel=2)
            return None


    def _record_turn(self, thread_id: str, message: str, answer: str) -> dict[str, Any]:
        """Track input/output tokens and the full history processed per turn.

        These are heuristic estimates in both modes, not provider billing data.
        """
        session = self.sessions.setdefault(thread_id, SessionState())
        session.messages.append({"role": "user", "content": message})
        prompt_tokens = sum(estimate_tokens(turn["content"]) for turn in session.messages)
        turn_tokens = estimate_tokens(message) + estimate_tokens(answer)
        session.prompt_tokens_processed += prompt_tokens
        session.token_usage += turn_tokens
        session.messages.append({"role": "assistant", "content": answer})
        return {
            "response": answer,
            "tokens": turn_tokens,
            "prompt_tokens": prompt_tokens,
            "token_usage": session.token_usage,
            "prompt_tokens_processed": session.prompt_tokens_processed,
        }
