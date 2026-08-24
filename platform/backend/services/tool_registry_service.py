"""Live MCP server"""
from state_graph import db
from ..deps import get_stack


def list_tools():
    stack = get_stack()
    live_catalog = stack.mcp.list_tools()
    with db.connect() as conn:
        disabled = {r["tool_name"] for r in conn.execute(
            "SELECT tool_name FROM tool_overrides WHERE enabled = 0")}
    return {"live_catalog": live_catalog, "disabled": sorted(disabled)}


def set_tool(tool_name: str, enabled: bool):
    with db.connect() as conn:
        conn.execute("""INSERT INTO tool_overrides(tool_name, enabled)
                        VALUES (?, ?)
                        ON CONFLICT(tool_name) DO UPDATE SET
                          enabled = excluded.enabled,
                          updated_at = CURRENT_TIMESTAMP""",
                     (tool_name, int(enabled)))
        
    return {"live_catalog_after": get_stack().mcp.list_tools()}