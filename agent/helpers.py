from __future__ import annotations

import json
from typing import Any
from google.genai import types as gtypes
from mcp import types


def content_to_text(content: Any) -> str:
    if isinstance(content, list):
        return "\n".join(content_to_text(c) for c in content)
    if isinstance(content, types.TextContent):
        return content.text
    return str(content)


def tool_result_to_text(result: types.CallToolResult) -> str:
    parts = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        else:
            parts.append(json.dumps(block.model_dump(mode="json")))
    return "\n".join(parts) or "(empty tool result)"


def coerce(raw: str, json_type: str) -> Any:
    if json_type == "number":
        return float(raw)
    if json_type == "integer":
        return int(raw)
    if json_type == "boolean":
        return raw.strip().lower() in {"y", "yes", "true", "1"}
    return raw


def _clean_schema(schema: dict | None) -> dict:
    """Cleans a JSON schema to ensure full compatibility with Google GenAI function declarations."""
    if not isinstance(schema, dict):
        return {}
    
    cleaned = {}
    forbidden_keys = {
        "additionalProperties", 
        "exclusiveMinimum", 
        "exclusiveMaximum", 
        "$schema", 
        "$id", 
        "default"
    }

    for key, value in schema.items():
        if key in forbidden_keys:
            continue
        if isinstance(value, dict):
            cleaned[key] = _clean_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _clean_schema(item) if isinstance(item, dict) else item 
                for item in value
            ]
        else:
            cleaned[key] = value
            
    return cleaned


def mcp_tools_to_gemini(tools: list[types.Tool]) -> list[gtypes.Tool]:
    declarations = [
        gtypes.FunctionDeclaration(
            name=tool.name,
            description=tool.description or "",
            parameters=_clean_schema(tool.inputSchema),
        )
        for tool in tools
    ]
    return [gtypes.Tool(function_declarations=declarations)] if declarations else []


async def call_tool_with_progress(
    agent, name: str, arguments: dict[str, Any]
) -> types.CallToolResult:
    assert agent.session is not None

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        pct = f"{(progress / total) * 100:.0f}%" if total else f"{progress:g}"
        print(f"  [progress] {pct}{f' - {message}' if message else ''}")

    return await agent.session.call_tool(name, arguments, progress_callback=on_progress)