# Memory Module

## Overview

The Memory Module is responsible for managing conversational memory for the Torque Tune Auto Care MCP Server.

It simulates an AI memory system by storing conversations, identifying important information, promoting memories into long-term storage, and organizing knowledge for future retrieval.

---

## Features

- Short-Term Memory
- Scratchpad
- Memory Router
- Episodic Memory Store
- Semantic Memory Store
- Consolidation Engine
- Logging System
- Configuration Management
- Automated Unit Tests

---

## Folder Structure

```
memory/
│
├── config.py
├── models.py
├── utils.py
├── short_term.py
├── scratchpad.py
├── router.py
├── episodic_store.py
├── semantic_store.py
├── consolidation.py
├── db_adapter.py
├── memory_manager.py
│
├── storage/
│   ├── episodic.json
│   └── semantic.json
│
├── logs/
│
└── tests/
    ├── test_short_term.py
    ├── test_router.py
    ├── test_episodic.py
    ├── test_semantic.py
    ├── test_consolidation.py
    └── test_memory_manager.py
```

---

## Memory Flow

```
User Message
      │
      ▼
Short-Term Memory
      │
      ▼
Memory Router
      │
      ▼
Episodic Memory
      │
      ▼
Consolidation Engine
      │
      ▼
Semantic Memory
```

---

## Components

### Short-Term Memory

Stores the latest conversation messages in a fixed-size queue.

### Scratchpad

Stores temporary notes and intermediate reasoning.

### Memory Router

Evaluates each message using:
- Keywords
- Metadata
- Message role
- Message length

Only important messages are promoted to Episodic Memory.

### Episodic Memory

Stores important events such as:
- Client preferences
- Vehicle information
- Appointments
- Repair history
- Technician notes

### Semantic Memory

Stores long-term facts extracted from episodic memories.

### Consolidation Engine

Transfers important episodic memories into semantic memory.

---

## Logging

The module records routing and consolidation events inside the `logs/` folder.

---

## Configuration

Configuration values are managed through `config.py`, including:
- Maximum short-term memory size
- Importance threshold
- Logging options

---

## Running the Tests

Run all tests using:

```bash
python -m unittest discover memory/tests
```

Expected output:

```
Ran 31 tests

OK
```

---

## Technologies Used

- Python
- unittest
- dataclasses
- logging
- pathlib
- JSON

---

## Authors

Torque Tune Auto Care Team

Memory Module developed by Habiba Elsayed.