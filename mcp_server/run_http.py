"""Streamable HTTP transport entrypoint."""
from contextlib import asynccontextmanager
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.lowlevel import NotificationOptions
from mcp_server.server import create_server

server = create_server()

# declare of initialization options with tools_changed=True
_original_create_init_options = server.create_initialization_options

def _patched_create_init_options(*args, **kwargs):
    # Ensure that notification_options is set with tools_changed=True
    kwargs.setdefault("notification_options", NotificationOptions(tools_changed=True))
    return _original_create_init_options(*args, **kwargs)

# set the patched method to the server instance
server.create_initialization_options = _patched_create_init_options

session_manager = StreamableHTTPSessionManager(app=server, json_response=True)

@asynccontextmanager
async def lifespan(app):
    async with session_manager.run():
        yield

app = Starlette(routes=[Mount("/mcp", app=session_manager.handle_request)], lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)