from __future__ import annotations

import json
from typing import Any

from groq import AsyncGroq

from app.config import GROQ_API_KEY, LLM_MODEL
from worker.agent.llm.base import LLMResponse, ToolCall


class GroqProvider:
    def __init__(self, model: str | None = None) -> None:
        self._client = AsyncGroq(api_key=GROQ_API_KEY)
        self._model = model or LLM_MODEL

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "temperature": 0.3}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LLMResponse(content=msg.content or "", tool_calls=calls)
