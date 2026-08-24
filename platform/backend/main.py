from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import deps
from .api import graphs, runs, hitl, tickets, tools, resources, agents

app = FastAPI(title="Torque-Tune Platform API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

from fastapi import Depends
from .auth import router as auth_router, require_admin
from .api import graphs, runs, hitl, tickets, tools, resources, agents, sourcing, warranty

app.include_router(sourcing.router, dependencies=[Depends(require_admin)])
app.include_router(warranty.router, dependencies=[Depends(require_admin)])
app.include_router(auth_router)                                  
app.include_router(graphs.router)                                
app.include_router(agents.router)                                
app.include_router(runs.router,     dependencies=[Depends(require_admin)])
app.include_router(hitl.router,     dependencies=[Depends(require_admin)])
app.include_router(tickets.router,  dependencies=[Depends(require_admin)])
app.include_router(tools.router,    dependencies=[Depends(require_admin)])
app.include_router(resources.router, dependencies=[Depends(require_admin)])

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")

@app.on_event("shutdown")
def _shutdown():
    stack = deps.peek_stack()
    if stack:
        try:
            stack.mcp.close()
        except Exception:
            pass