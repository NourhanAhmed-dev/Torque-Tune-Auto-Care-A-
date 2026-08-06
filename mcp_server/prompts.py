PROMPT_DEFS = {
    "tuning_disclosure": {
        "description": "Generate a compliance and warranty warning draft for a vehicle modification.",
        "arguments": [
            {"name": "vehicle_id", "description": "The target vehicle ID", "required": True},
            {"name": "modification", "description": "Description of the tuning work", "required": True},
        ],
    }
}

def render_prompt(name: str, arguments: dict) -> str:
    if name == "tuning_disclosure":
        vid = arguments.get("vehicle_id", "Unknown")
        mod = arguments.get("modification", "Unknown")
        return (
            f"Attention Technician: Reviewing modification '{mod}' for vehicle #{vid}. "
            "Please ensure compliance with emissions regulations and inform the client regarding potential warranty impacts."
        )
    return f"Unknown prompt: {name}"