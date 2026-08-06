from __future__ import annotations

from typing import AsyncContextManager, Callable, Tuple, Any
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from agent.config import AgentConfig, TransportMode
from mcp.client.streamable_http import streamable_http_client

def open_transport(
    config: AgentConfig,
) -> AsyncContextManager[Tuple[Any, Any, Callable[[], str | None]]]:
    if config.transport_mode is TransportMode.STDIO:
        server_params = StdioServerParameters(
            command=config.stdio_command,
            args=list(config.stdio_args),
        )
        return stdio_client(server_params)
    elif config.transport_mode is TransportMode.HTTP:
        return streamable_http_client(config.http_url)
    else:
        raise ValueError(f"Unsupported transport mode: {config.transport_mode}")