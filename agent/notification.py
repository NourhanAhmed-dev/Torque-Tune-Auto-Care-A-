from __future__ import annotations

import asyncio
from mcp import types as mcp_types
from agent import tools as tools_module


async def handle_notification(agent, message, *args, **kwargs) -> None:
    """Handles incoming server notifications, specifically tools/list_changed."""
    if isinstance(message, mcp_types.ServerNotification) and isinstance(
        message.root, mcp_types.ToolListChangedNotification
    ):
        print("  [notifications/tools/list_changed received] -- scheduling catalog refresh")
        
        # Create a task to refresh the catalog in the background, so we don't block the notification handler
        task = asyncio.create_task(_safe_refresh(agent))
        agent._pending_notification_tasks.append(task)
        
    elif isinstance(message, mcp_types.ServerNotification) and isinstance(
        message.root, mcp_types.LoggingMessageNotification
    ):
        print(f"[server log:{message.root.params.level}] {message.root.params.data}")


async def _safe_refresh(agent) -> None:
    try:
        await tools_module.refresh_catalog(agent)
        print(f"  [catalog refreshed] tools now: {sorted(t.name for t in agent.tools)}")
    except Exception as e:
        print(f"  [catalog refresh error] {e}")