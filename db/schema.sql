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