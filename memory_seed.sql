PRAGMA foreign_keys = ON;

-- ============================================
-- EPISODIC MEMORIES
-- ============================================

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

-- ============================================
-- SEMANTIC FACTS
-- ============================================

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

-- ============================================
-- ROUTING LOG
-- ============================================

CREATE TABLE IF NOT EXISTS routing_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_excerpt TEXT,
    decision TEXT NOT NULL,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- MEMORY SEED DATA
-- Uses EXISTING clients / vehicles / technicians
-- ============================================

INSERT OR IGNORE INTO episodic_memories
(memory_id, content, importance, reason, vehicle_id, client_id, tech_id)
VALUES
(
    'memory_001',
    'Ahmed Ali brought his BMW 320i for ECU Stage 1 tuning.',
    5,
    'Important vehicle service event.',
    1,
    1,
    1
),
(
    'memory_002',
    'Ahmed Ali owns both a BMW 320i and an Audi A4.',
    4,
    'Useful long-term client and vehicle information.',
    2,
    1,
    NULL
),
(
    'memory_003',
    'Mohamed Samir owns a Mercedes C200 that received performance-related service.',
    4,
    'Relevant vehicle service history.',
    3,
    2,
    2
);

-- ============================================
-- SEMANTIC FACTS
-- ============================================

INSERT OR IGNORE INTO semantic_facts
(
    fact_id,
    fact,
    category,
    version,
    active,
    source_episode,
    client_id,
    vehicle_id
)
VALUES
(
    'fact_001',
    'Ahmed Ali owns a BMW 320i 2021.',
    'vehicle_ownership',
    1,
    1,
    'memory_001',
    1,
    1
),
(
    'fact_002',
    'Ahmed Ali owns an Audi A4 2020.',
    'vehicle_ownership',
    1,
    1,
    'memory_002',
    1,
    2
),
(
    'fact_003',
    'BMW 320i received an ECU Stage 1 tune.',
    'service_history',
    1,
    1,
    'memory_001',
    1,
    1
),
(
    'fact_004',
    'Mahmoud Salem specializes in performance tuning.',
    'technician_specialization',
    1,
    1,
    NULL,
    NULL,
    NULL
);

-- ============================================
-- ROUTING LOG
-- ============================================

INSERT INTO routing_log
(item_excerpt, decision, reason)
VALUES
(
    'Ahmed Ali brought his BMW for ECU Stage 1 tuning.',
    'episodic',
    'Important service event worth retaining as episodic memory.'
),
(
    'Client asked about the current opening hours.',
    'forget',
    'Temporary information with no long-term memory value.'
),
(
    'Ahmed Ali owns a BMW 320i.',
    'episodic',
    'Relevant client and vehicle information.'
),
(
    'BMW 320i received ECU Stage 1 tuning.',
    'episodic',
    'Useful service history for future interactions.'
);