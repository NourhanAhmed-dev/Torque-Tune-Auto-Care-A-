from __future__ import annotations

from typing import Any
from google.genai import types as gtypes
from mcp import types, ClientSession

from agent.helpers import content_to_text


async def handle_sampling(
    agent: Any,
    # ctx: RequestContext[ClientSession, Any],
    params: types.CreateMessageRequestParams,
) -> types.CreateMessageResult:
    if agent._llm is None:
        raise types.McpError(
            code=types.INTERNAL_ERROR,
            message="Agent has no GEMINI_API_KEY configured for sampling.",
        )

    prompt_parts = []
    for m in params.messages:
        text_content = content_to_text(m.content)
        prompt_parts.append(f"{m.role}: {text_content}")

    prompt_text = "\n".join(prompt_parts)

    config = gtypes.GenerateContentConfig(
        system_instruction=params.systemPrompt,
        max_output_tokens=params.maxTokens,
        temperature=params.temperature,
    )

    response = await agent._llm.aio.models.generate_content(
        model=agent.config.gemini_model,
        contents=prompt_text,
        config=config,
    )

    response_text = response.text or ""

    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text=response_text),
        model=agent.config.gemini_model,
        stopReason="endTurn",
    )