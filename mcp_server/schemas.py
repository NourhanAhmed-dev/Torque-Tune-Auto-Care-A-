TUNING_CATEGORIES = ["cosmetic", "performance", "emissions_affecting"]
PAYMENT_STATUSES = ["paid", "unpaid", "partial"]

GET_CLIENT = {
    "type": "object",
    "properties": {
        "client_id": {"type": "integer", "minimum": 1, "description": "Primary key of the client to look up."},
    },
    "required": ["client_id"],
    "additionalProperties": False,
}

GET_VEHICLE = {
    "type": "object",
    "properties": {
        "vehicle_id": {"type": "integer", "minimum": 1, "description": "Primary key of the vehicle to look up."},
    },
    "required": ["vehicle_id"],
    "additionalProperties": False,
}

LIST_CLIENT_VEHICLES = {
    "type": "object",
    "properties": {
        "client_id": {"type": "integer", "minimum": 1, "description": "Client whose vehicles to list."},
    },
    "required": ["client_id"],
    "additionalProperties": False,
}

LIST_APPOINTMENTS = {
    "type": "object",
    "properties": {
        "vehicle_id": {"type": "integer", "minimum": 1, "description": "Filter by vehicle (optional)."},
        "tech_id": {"type": "integer", "minimum": 1, "description": "Filter by technician (optional)."},
    },
    "additionalProperties": False,
}

GET_INVOICE = {
    "type": "object",
    "properties": {
        "invoice_id": {"type": "integer", "minimum": 1, "description": "Primary key of the invoice to look up."},
    },
    "required": ["invoice_id"],
    "additionalProperties": False,
}

LIST_TUNING_LOGS = {
    "type": "object",
    "properties": {
        "vehicle_id": {"type": "integer", "minimum": 1, "description": "Vehicle whose tuning history to list."},
    },
    "required": ["vehicle_id"],
    "additionalProperties": False,
}

AUTHENTICATE_TECHNICIAN = {
    "type": "object",
    "properties": {
        "tech_id": {"type": "integer", "minimum": 1, "description": "Technician ID badge number."},
        "tech_phone": {
            "type": "string",
            "pattern": "^01[0-9]{9}$",
            "description": "Technician's registered phone number.",
        },
    },
    "required": ["tech_id", "tech_phone"],
    "additionalProperties": False,
}

CREATE_APPOINTMENT = {
    "type": "object",
    "properties": {
        "vehicle_id": {"type": "integer", "minimum": 1},
        "tech_id": {"type": "integer", "minimum": 1},
        "appointment_date": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
            "description": "Format: YYYY-MM-DD HH:MM",
        },
    },
    "required": ["vehicle_id", "tech_id", "appointment_date"],
    "additionalProperties": False,
}

LOG_TUNING_MODIFICATION = {
    "type": "object",
    "properties": {
        "vehicle_id": {"type": "integer", "minimum": 1},
        "tech_id": {"type": "integer", "minimum": 1},
        "category": {"type": "string", "enum": TUNING_CATEGORIES},
        "description": {"type": "string", "minLength": 5, "maxLength": 500},
    },
    "required": ["vehicle_id", "tech_id", "category", "description"],
    "additionalProperties": False,
}

MARK_TUNING_COMPLETE = {
    "type": "object",
    "properties": {
        "log_id": {"type": "integer", "minimum": 1},
    },
    "required": ["log_id"],
    "additionalProperties": False,
}

CREATE_INVOICE = {
    "type": "object",
    "properties": {
        "client_id": {"type": "integer", "minimum": 1},
        "total_amount": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000000},
        "payment": {"type": "string", "enum": PAYMENT_STATUSES},
    },
    "required": ["client_id", "total_amount", "payment"],
    "additionalProperties": False,
}

GENERATE_SERVICE_REPORT = {
    "type": "object",
    "properties": {
        "client_id": {"type": "integer", "minimum": 1},
    },
    "required": ["client_id"],
    "additionalProperties": False,
}

FLAG_TUNING_MODIFICATION_FOR_REVIEW = {
    "type": "object",
    "properties": {
        "vehicle_id": {"type": "integer", "minimum": 1},
        "category": {"type": "string", "enum": TUNING_CATEGORIES},
        "description": {"type": "string", "minLength": 5, "maxLength": 500},
    },
    "required": ["vehicle_id", "category", "description"],
    "additionalProperties": False,
}