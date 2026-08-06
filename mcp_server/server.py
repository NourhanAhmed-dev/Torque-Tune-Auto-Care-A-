from __future__ import annotations

import json
import logging
import asyncio
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    Prompt,
    PromptMessage,
    GetPromptResult,
    PromptArgument,
)
from mcp_server.database import get_db_connection
from mcp_server.config import POLICY_URI, POLICY_PATH, TUNING_CATEGORIES, PAYMENT_STATUSES
from mcp.types import Tool, TextContent, Resource, Prompt, PromptMessage, GetPromptResult, PromptArgument, SamplingMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("torque-tune-server")


def create_server() -> Server:
    app = Server("torque-tune-auto-care-server")
    _authenticated_tech: dict | None = None

    @app.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri=POLICY_URI,
                name="Tuning & Emissions Compliance Policy",
                mimeType="text/markdown",
                description="Guidelines on handling emissions-affecting modifications and factory warranties.",
            )
        ]

    @app.read_resource()
    async def read_resource(uri: str) -> str:
        if str(uri) == POLICY_URI:
            if POLICY_PATH.exists():
                return POLICY_PATH.read_text(encoding="utf-8")
            return "Default Compliance Policy: Emissions-affecting modifications require client notification."
        raise ValueError(f"Unknown resource URI: {uri}")

    @app.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="tuning_disclosure",
                description="Generate tuning disclosure and warranty warning prompt.",
                arguments=[
                    PromptArgument(name="vehicle_id", description="The ID of the vehicle", required=True),
                    PromptArgument(name="modification", description="The type of modification being performed", required=True),
                ]
            )
        ]

    @app.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
        if name == "tuning_disclosure":
            args = arguments or {}
            v_id = args.get("vehicle_id", "3")
            modification = args.get("modification", "ECU remap")
            return GetPromptResult(
                description="Tuning disclosure and warranty prompt",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text", 
                            text=f"Warning: Performing a '{modification}' on vehicle ID {v_id} requires customer disclosure regarding emissions and factory warranty impact."
                        )
                    )
                ]
            )
        raise ValueError(f"Unknown prompt: {name}")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        #base tools available to all users
        base_tools = [
            Tool(
                name="authenticate_technician",
                description="Authenticate technician using tech_id and tech_phone from technicians table.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tech_id": {"type": "integer", "minimum": 1},
                        "tech_phone": {"type": "string"},
                    },
                    "required": ["tech_id", "tech_phone"],
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="list_vehicles",
                description="List all registered vehicles with client details.",
                inputSchema={
                    "type": "object", 
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
        ]

        #(Notifications Trigger)
        if _authenticated_tech is not None:
            base_tools.extend([
                Tool(
                    name="log_tuning_modification",
                    description="Insert a new tuning log into tuning_logs table.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "vehicle_id": {"type": "integer", "minimum": 1},
                            "tech_id": {"type": "integer", "minimum": 1},
                            "status": {"type": "string"},
                            "category": {"type": "string", "enum": TUNING_CATEGORIES},
                            "description": {"type": "string", "minLength": 3, "maxLength": 500},
                        },
                        "required": ["vehicle_id", "tech_id", "status", "category", "description"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="create_invoice",
                    description="Create a new invoice in invoices table for a client.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "client_id": {"type": "integer", "minimum": 1},
                            "total_amount": {"type": "number", "minimum": 0},
                            "payment": {"type": "string", "enum": PAYMENT_STATUSES},
                        },
                        "required": ["client_id", "total_amount", "payment"],
                        "additionalProperties": False,
                    },
                ),
                Tool(
                    name="generate_service_report",
                    description="Generates a comprehensive service report with live progress tracking.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "client_id": {"type": "integer", "minimum": 1},
                        },
                        "required": ["client_id"],
                        "additionalProperties": False,
                    },
                ),
            ])

        return base_tools

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        nonlocal _authenticated_tech
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if name == "authenticate_technician":
                tech_id = arguments.get("tech_id")
                phone = arguments.get("tech_phone")
                cursor.execute("SELECT * FROM technicians WHERE tech_id = ? AND tech_phone = ?", (tech_id, phone))
                tech = cursor.fetchone()
                if tech:
                    _authenticated_tech = dict(tech)
                    logger.info(f"Technician authenticated: {_authenticated_tech.get('full_name', tech_id)}")
                    
                    # (Notifications / list_changed)
                    try:
                        session = app.request_context.session
                        await session.send_tool_list_changed()
                    except Exception as e:
                        logger.warning(f"Could not send tool_list_changed notification: {e}")

                    return [
                        TextContent(
                            type="text",
                            text=json.dumps({"authenticated": True, "technician": _authenticated_tech}, indent=2, default=str)
                        )
                    ]
                return [TextContent(type="text", text=json.dumps({"authenticated": False, "error": "Invalid credentials"}))]

            elif name == "list_vehicles":
                cursor.execute("""
                    SELECT v.vehicle_id, v.make, v.model, v.year, v.license_plate, v.vin, c.full_name as client_name 
                    FROM vehicles v JOIN clients c ON v.client_id = c.client_id
                """)
                vehicles = [dict(row) for row in cursor.fetchall()]
                return [TextContent(type="text", text=json.dumps(vehicles, indent=2, default=str))]

           
            elif name == "log_tuning_modification":
                if _authenticated_tech is None:
                    return [TextContent(type="text", text=json.dumps({"error": "Unauthorized. Please authenticate first."}))]
                
                vehicle_id = arguments.get("vehicle_id")
                tech_id = arguments.get("tech_id")
                status = arguments.get("status")
                category = arguments.get("category")
                description = arguments.get("description")

                if tech_id != _authenticated_tech.get("tech_id"):
                    return [TextContent(type="text", text=json.dumps({"error": "Tech ID mismatch with active session."}))]

                # SAMPLING . ELICITATION 
                if category == "emissions_affecting":
                    session = app.request_context.session
                    
                    # 1. SAMPLING:
                    try:
                        sampling_req = await session.create_message(
                            messages=[
                                SamplingMessage(
                                    role="user",
                                    content=TextContent(
                                        type="text",
                                        text=f"Draft a brief compliance warning about the risks of performing an '{category}' modification described as '{description}'."
                                    )
                                )
                            ],
                            system_prompt="You are an automotive compliance auditor.",
                            max_tokens=150
                        )
                        risk_warning = sampling_req.content.text if hasattr(sampling_req, 'content') else "Warranty void and emissions non-compliance."
                    except Exception as e:
                        logger.warning(f"Sampling failed or not supported: {e}")
                        risk_warning = "Emissions-affecting modifications void the factory warranty and violate environmental regulations."

                    # 2. ELICITATION: 
                    try:
                        elicit_res = await session.elicit(
                            message=f"EMISSIONS MODIFICATION WARNING:\n{risk_warning}\n\nDo you confirm the customer has been informed of these risks and agrees to proceed?",
                            requested_schema={
                                "type": "object",
                                "properties": {
                                    "customer_signature": {"type": "string", "description": "Customer Name or Signature"},
                                    "confirm": {"type": "boolean", "description": "Customer agrees to the risks"}
                                },
                                "required": ["customer_signature", "confirm"]
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Elicitation failed or not supported: {e}")
                        return [TextContent(type="text", text=json.dumps({"error": "Elicitation required for emissions-affecting modifications but client does not support it."}))]

                    # if did not accept, abort the modification
                    if elicit_res.action != "accept" or not elicit_res.content.get("confirm"):
                        return [TextContent(type="text", text=json.dumps({"error": "Customer did not agree to emissions modification risks. Modification aborted."}))]

                # after acceptance, log the modification
                cursor.execute(
                    "INSERT INTO tuning_logs (status, category, description, vehicle_id, tech_id) VALUES (?, ?, ?, ?, ?)",
                    (status, category, description, vehicle_id, tech_id),
                )
                conn.commit()
                return [TextContent(type="text", text=json.dumps({"success": True, "message": "Tuning log recorded successfully."}))]
            elif name == "create_invoice":
                if _authenticated_tech is None:
                    return [TextContent(type="text", text=json.dumps({"error": "Unauthorized. Technician authentication required."}))]

                client_id = arguments.get("client_id")
                total_amount = arguments.get("total_amount")
                payment = arguments.get("payment")

                #Server-side Validation (Defensive Tool Design)
                cursor.execute("SELECT client_id FROM clients WHERE client_id = ?", (client_id,))
                if not cursor.fetchone():
                    return [TextContent(type="text", text=json.dumps({"error": f"Authorization/Validation failed: Client ID {client_id} does not exist in database."}))]

                cursor.execute(
                    "INSERT INTO invoices (total_amount, payment, client_id) VALUES (?, ?, ?)",
                    (total_amount, payment, client_id),
                )
                conn.commit()
                return [TextContent(type="text", text=json.dumps({"success": True, "message": "Invoice created successfully."}))]
            elif name == "generate_service_report":
                if _authenticated_tech is None:
                    return [TextContent(type="text", text=json.dumps({"error": "Unauthorized. Technician authentication required."}))]

                client_id = arguments.get("client_id")
                
                # extract progress token from request context if available
                progress_token = None
                try:
                    progress_token = app.request_context.meta.get("progressToken")
                except Exception:
                    pass

                session = getattr(app.request_context, "session", None)

                if session and progress_token:
                    await session.send_progress(progress_token, progress=1, total=3, message="Fetching client vehicles...")
                await asyncio.sleep(0.2)

                cursor.execute("SELECT * FROM vehicles WHERE client_id = ?", (client_id,))
                vehicles = [dict(row) for row in cursor.fetchall()]

                if session and progress_token:
                    await session.send_progress(progress_token, progress=2, total=3, message="Compiling tuning logs...")
                await asyncio.sleep(0.2)

                cursor.execute("""
                    SELECT t.* FROM tuning_logs t 
                    JOIN vehicles v ON t.vehicle_id = v.vehicle_id 
                    WHERE v.client_id = ?
                """, (client_id,))
                logs = [dict(row) for row in cursor.fetchall()]

                if session and progress_token:
                    await session.send_progress(progress_token, progress=3, total=3, message="Report generation complete.")
                await asyncio.sleep(0.2)

                report_data = {
                    "client_id": client_id,
                    "vehicles": vehicles,
                    "tuning_logs": logs,
                    "status": "Generated successfully"
                }
                return [TextContent(type="text", text=json.dumps(report_data, indent=2, default=str))]
            else:
                return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        finally:
            conn.close()

    return app