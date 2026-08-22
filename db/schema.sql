PRAGMA foreign_keys = ON;

-- ============================================================
-- CLIENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    address TEXT
);

-- ============================================================
-- TECHNICIANS
-- ============================================================

CREATE TABLE IF NOT EXISTS technicians (
    tech_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    tech_phone TEXT NOT NULL UNIQUE,
    specialization TEXT
);

-- ============================================================
-- VEHICLES
-- ============================================================

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    license_plate TEXT,
    vin TEXT,
    FOREIGN KEY (client_id)
        REFERENCES clients(client_id)
);

-- ============================================================
-- APPOINTMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_date TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL,
    tech_id INTEGER NOT NULL,
    FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (tech_id)
        REFERENCES technicians(tech_id)
);

-- ============================================================
-- TUNING LOGS
-- ============================================================

CREATE TABLE IF NOT EXISTS tuning_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL,
    tech_id INTEGER NOT NULL,
    FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (tech_id)
        REFERENCES technicians(tech_id)
);

-- ============================================================
-- PARTS CATALOG
-- ============================================================

CREATE TABLE IF NOT EXISTS parts_catalog (
    part_id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,
    part_name TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    price REAL DEFAULT 0,
    FOREIGN KEY (log_id)
        REFERENCES tuning_logs(log_id)
);

-- ============================================================
-- INVOICES
-- ============================================================

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_amount REAL NOT NULL,
    payment TEXT NOT NULL,
    client_id INTEGER NOT NULL,
    FOREIGN KEY (client_id)
        REFERENCES clients(client_id)
);

-- ============================================================
-- EPISODIC MEMORY
-- ============================================================

CREATE TABLE IF NOT EXISTS episodic_memories (
    memory_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 1,
    reason TEXT,
    vehicle_id INTEGER,
    client_id INTEGER,
    tech_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id),

    FOREIGN KEY (client_id)
        REFERENCES clients(client_id),

    FOREIGN KEY (tech_id)
        REFERENCES technicians(tech_id)
);

-- ============================================================
-- SEMANTIC FACTS
-- ============================================================

CREATE TABLE IF NOT EXISTS semantic_facts (
    fact_id TEXT PRIMARY KEY,
    fact TEXT NOT NULL,
    category TEXT,
    version INTEGER DEFAULT 1,
    active INTEGER DEFAULT 1,
    source_episode TEXT,
    expires_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    client_id INTEGER,
    vehicle_id INTEGER,

    FOREIGN KEY (client_id)
        REFERENCES clients(client_id),

    FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id)
);

-- ============================================================
-- MEMORY ROUTING LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS routing_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_excerpt TEXT,
    decision TEXT NOT NULL,
    -- 'episodic' | 'forget'
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- STATE GRAPH RUNS
-- ============================================================

CREATE TABLE IF NOT EXISTS state_graph_runs (
    run_id TEXT PRIMARY KEY,
    graph_type TEXT NOT NULL,
    status TEXT NOT NULL,
    current_state TEXT,
    vehicle_id INTEGER,
    client_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id)
        REFERENCES vehicles(vehicle_id),

    FOREIGN KEY (client_id)
        REFERENCES clients(client_id)
);

-- ============================================================
-- STATE GRAPH CHECKPOINTS
-- ============================================================

CREATE TABLE IF NOT EXISTS state_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    graph_name TEXT NOT NULL,
    node_name TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,

    FOREIGN KEY (run_id)
        REFERENCES state_graph_runs(run_id)
        ON DELETE CASCADE
);

-- ============================================================
-- HUMAN-IN-THE-LOOP TASKS
-- ============================================================

CREATE TABLE IF NOT EXISTS hitl_tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    checkpoint_id TEXT,
    state TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    admin_id TEXT,
    decision TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,

    FOREIGN KEY (run_id)
        REFERENCES state_graph_runs(run_id)
        ON DELETE CASCADE
);

-- ============================================================
-- FAILURE / RECOVERY TICKETS
-- ============================================================

CREATE TABLE IF NOT EXISTS failure_tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    state TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    checkpoint_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    assigned_to TEXT,
    resolution TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,

    FOREIGN KEY (run_id)
        REFERENCES state_graph_runs(run_id)
        ON DELETE CASCADE,

    FOREIGN KEY (checkpoint_id)
        REFERENCES state_checkpoints(checkpoint_id)
        ON DELETE SET NULL
);

-- ============================================================
-- MULTI-SUPPLIER PARTS SOURCING
-- ============================================================

CREATE TABLE IF NOT EXISTS supplier_orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    supplier TEXT NOT NULL,
    status TEXT NOT NULL,
    -- pending | ordered | backorder | shipped |
    -- delivered | cancelled | failed

    quoted_price REAL NOT NULL,
    final_price REAL,
    expected_delivery TEXT,
    actual_delivery TEXT,
    api_attempts INTEGER DEFAULT 0,
    last_api_error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id)
        REFERENCES state_graph_runs(run_id)
        ON DELETE CASCADE
);

-- ============================================================
-- SUPPLIER ORDER PARTS
-- ============================================================

CREATE TABLE IF NOT EXISTS supplier_order_parts (
    order_id INTEGER NOT NULL,
    part_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    substitute_part TEXT,
    warranty_impact TEXT,

    PRIMARY KEY (order_id, part_id),

    FOREIGN KEY (order_id)
        REFERENCES supplier_orders(order_id)
        ON DELETE CASCADE,

    FOREIGN KEY (part_id)
        REFERENCES parts_catalog(part_id)
);

-- ============================================================
-- INSTALLATION STEPS
-- ============================================================

CREATE TABLE IF NOT EXISTS installation_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    part_id INTEGER,
    step_order INTEGER NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    -- pending | in_progress | completed | failed

    dependencies TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id)
        REFERENCES state_graph_runs(run_id)
        ON DELETE CASCADE,

    FOREIGN KEY (part_id)
        REFERENCES parts_catalog(part_id)
);

-- ============================================================
-- SUPPLIER EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS supplier_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    order_id INTEGER,
    event_type TEXT NOT NULL,
    -- shipment_confirmed | delivery_confirmed |
    -- backorder | cancelled | price_changed |
    -- substitute_offered

    payload TEXT,
    status TEXT NOT NULL DEFAULT 'received',
    -- received | processed | failed

    received_at TEXT DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,

    FOREIGN KEY (run_id)
        REFERENCES state_graph_runs(run_id)
        ON DELETE CASCADE,

    FOREIGN KEY (order_id)
        REFERENCES supplier_orders(order_id)
        ON DELETE SET NULL
);

-- ============================================================
-- BUILD PRESETS
-- ============================================================

CREATE TABLE IF NOT EXISTS build_presets (
    preset_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

-- ============================================================
-- BUILD PART REQUIREMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS build_part_requirements (
    preset_key TEXT NOT NULL,
    part_id INTEGER NOT NULL,
    part_name TEXT NOT NULL,
    supplier TEXT NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (preset_key, part_id),

    FOREIGN KEY (preset_key)
        REFERENCES build_presets(preset_key)
        ON DELETE CASCADE
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_build_part_requirements_preset
    ON build_part_requirements(preset_key);

CREATE INDEX IF NOT EXISTS idx_state_checkpoints_run
    ON state_checkpoints(run_id);

CREATE INDEX IF NOT EXISTS idx_hitl_tasks_run
    ON hitl_tasks(run_id);

CREATE INDEX IF NOT EXISTS idx_failure_tickets_run
    ON failure_tickets(run_id);

CREATE INDEX IF NOT EXISTS idx_supplier_orders_run
    ON supplier_orders(run_id);

CREATE INDEX IF NOT EXISTS idx_installation_steps_run
    ON installation_steps(run_id);

CREATE INDEX IF NOT EXISTS idx_supplier_events_run
    ON supplier_events(run_id);