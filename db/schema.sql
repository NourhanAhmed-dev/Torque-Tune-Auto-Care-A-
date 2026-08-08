PRAGMA foreign_keys = ON;

CREATE TABLE clients (
    client_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    address TEXT
);

CREATE TABLE technicians (
    tech_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    tech_phone TEXT NOT NULL UNIQUE,
    specialization TEXT
);

CREATE TABLE vehicles (
    vehicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    license_plate TEXT,
    vin TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE TABLE appointments (
    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_date TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL,
    tech_id INTEGER NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (tech_id) REFERENCES technicians(tech_id)
);

CREATE TABLE tuning_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL,
    tech_id INTEGER NOT NULL,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (tech_id) REFERENCES technicians(tech_id)
);

CREATE TABLE parts_catalog (
    part_id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,
    part_name TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    price REAL DEFAULT 0,
    FOREIGN KEY (log_id) REFERENCES tuning_logs(log_id)
);

CREATE TABLE invoices (
    invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_amount REAL NOT NULL,
    payment TEXT NOT NULL,
    client_id INTEGER NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE TABLE IF NOT EXISTS episodic_memories (
    memory_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 1,
    reason TEXT,
    vehicle_id INTEGER,
    client_id INTEGER,
    tech_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (tech_id) REFERENCES technicians(tech_id)
);

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
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
);

CREATE TABLE IF NOT EXISTS routing_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_excerpt TEXT,
    decision TEXT NOT NULL,            -- 'episodic' | 'forget'
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);