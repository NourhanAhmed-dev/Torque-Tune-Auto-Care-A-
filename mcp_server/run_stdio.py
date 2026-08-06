import anyio
from mcp.server.lowlevel import NotificationOptions
from mcp.server.stdio import stdio_server
from mcp_server.server import create_server

async def main():
    app = create_server()

    init_options = app.create_initialization_options(
        notification_options=NotificationOptions(
            tools_changed=True
        )
    )

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            init_options,
        )

if __name__ == "__main__":
    anyio.run(main)