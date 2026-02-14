# Android BSP AI Consultant Team (The Studio)

> **Version:** v5.2.0 (Phase 2: Cognitive Awakening)
> **Status:** Active Development / Simulation

## Project Overview

This repository hosts the **Recursive Cognitive Software Factory** (also known as "The Studio"), a specialized multi-agent system designed to autonomously build, verify, and maintain high-quality software products.

The primary product being built is the **Android BSP Consultant**, an AI agent capable of analyzing Android Kernel logs, performing root cause analysis (RCA), and suggesting fixes for complex embedded systems issues (e.g., Suspend-to-Disk failures).

### Core Philosophy: Factory vs. Product
*   **The Studio (`studio/`):** The "Factory" infrastructure. It contains the Orchestrator, Agents (Architect, Product Owner, Engineer, Scrum Master), and the Governance rules. This is the "meta-level" system that builds the software.
*   **The Product (`product/`):** The output of the Studio. This includes the actual source code, prompts, and configurations for the Android BSP Consultant agent.

## Architecture

The system operates as a **Hierarchical State Machine** orchestrated by LangGraph, with strict **Context Slicing** and **Cognitive Guardrails**.

### The Agent Team
1.  **Orchestrator (The Executive):**
    *   Manages the global state (`studio_state.json`) and routes tasks.
    *   Enforces **Context Slicing** to isolate agents from irrelevant data.
    *   Monitors **Semantic Entropy** to prevent "hallucinations" or cognitive tunneling.
2.  **Product Owner (Strategy):**
    *   Reads `PRODUCT_BLUEPRINT.md` and generates development tickets (User Stories).
    *   Maintains the Product Backlog.
3.  **Engineer (Execution):**
    *   Implements code and fixes based on tickets.
    *   Operates within a sandboxed environment (`_workspace/`).
4.  **Architect (Governance):**
    *   Reviews all code and prompts against `AGENTS.md` (The Constitution).
    *   Enforces SOLID principles and security standards.
5.  **QA Agent (Verification):**
    *   Runs deterministic tests (`pytest`) and semantic similarity checks.
6.  **Scrum Master (Optimization):**
    *   Analyzes sprint logs to identify process bottlenecks.
    *   Suggests optimizations to the Studio's prompts or workflows (OPRO).

### Key Features
*   **Semantic Entropy Guardrail:** Uses `VertexFlashJudge` to measure the uncertainty of agent outputs. If entropy exceeds a threshold, the "Circuit Breaker" triggers to prevent compounding errors.
*   **Context Slicing:** Dynamically filters the file system and logs presented to each agent, ensuring they only see what is relevant to their current task.
*   **Evolution Safety Levels (ESL):**
    *   **ESL-1 (Product):** Automatic evolution of the product (prompts/code) via the Optimizer.
    *   **ESL-2 (Studio):** Manual review required for changes to the Studio's core logic or `AGENTS.md`.
*   **Docker Sandbox:** All code execution and verification happen in isolated Docker containers to ensure safety and reproducibility.

## Repository Structure

```
.
├── AGENTS.md               # The Constitution: Rules and Governance for all agents.
├── PRODUCT_BLUEPRINT.md    # The Product Spec: What the Studio is building.
├── README.md               # This file.
├── product/                # The Output: The Android BSP Consultant Agent code/prompts.
│   ├── bsp_agent/          # Core logic of the product.
│   └── prompts/            # Product prompts (optimized by Scrum Master).
├── studio/                 # The Factory: The AI Software Studio.
│   ├── agents/             # Agent implementations (Architect, PO, Scrum Master, etc.).
│   ├── memory.py           # Pydantic models and State definitions.
│   ├── orchestrator.py     # Main runtime logic and StateGraph definition.
│   ├── manager.py          # State persistence and management.
│   └── utils/              # Utilities (Entropy Math, Sandbox, Patching).
└── tests/                  # Test suite and Simulations.
    └── phase2_simulation.py # End-to-end simulation of the Studio workflow.
```

## Getting Started

### Prerequisites
*   Python 3.10+
*   Docker (for sandboxing)
*   Google Cloud Vertex AI Credentials (configured in environment)

### Installation
```bash
pip install -r requirements.txt
```

### Running the Simulation
To verify the full autonomous loop (Strategy -> Execution -> Governance -> Optimization), run the Phase 2 Simulation.

**Setup Process:**
1.  Ensure dependencies are installed: `pip install -r requirements.txt`
2.  The simulation automatically mocks Google Cloud environment variables (e.g., `GOOGLE_CLOUD_PROJECT`), so no external API keys are required for this specific script.

**Execution:**
```bash
PYTHONPATH=. python tests/phase2_simulation.py
```
*Note: The simulation uses mocks for Vertex AI to run without incurring costs.*

### Running the Integration Heartbeat
The Integration Heartbeat Test (the "Defibrillator") verifies the end-to-end connectivity between the **Orchestrator**, **Engineer Subgraph**, and **Memory** layers using mocked external IO.

**Execution:**
```bash
PYTHONPATH=. python tests/integration_heartbeat.py
```

### Running Tests
Execute the full test suite using `pytest`:

```bash
PYTHONPATH=. pytest tests/
```

## License
[License Information Here]
