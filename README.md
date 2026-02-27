# Android BSP AI Consultant Team (The Studio)

[![AI Safety](https://img.shields.io/badge/AI-Safety-blue.svg)](https://example.com/ai-safety)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Version:** v5.2.0 (Phase 3: Evolution & Reality)
> **Status:** Research Prototype / Serious AI Systems Engineering
>
> *Note: While the system design targets Phase 3 (v5.2.0), the codebase currently initializes with a "Cold Start" version of v1.0.0 via `main.py`.*

## Project Overview

This repository hosts the **Recursive Cognitive Software Factory** (also known as "The Studio"), a specialized multi-agent system designed to autonomously build, verify, and maintain high-quality software products.

The primary product being built is the **Android BSP Consultant**, an AI agent capable of analyzing Android Kernel logs, performing root cause analysis (RCA), and suggesting fixes for complex embedded systems issues (e.g., Suspend-to-Disk failures).

### 市場定位 | Market Positioning
The **Recursive Cognitive Software Factory** occupies a unique niche between general-purpose autonomous coding agents (like Devin) and domain-specific expert systems. It serves as a **Specialized AI Systems Research Prototype** for:
*   **Autonomous Software Delivery:** Moving beyond code generation to the autonomous management of the entire software lifecycle (Planning, Execution, Governance, Evolution).
*   **Domain-Specific Expertise:** Focusing on the high-stakes, log-intensive environment of Android Board Support Package (BSP) development.
*   **Self-Evolving Systems:** Implementing OPRO (Optimization by PROmpting) to allow the factory to improve its own internal logic based on performance data.

### 為何重要 | Why This Matters
*   **AI Safety & Governance:** By implementing strict **Cognitive Guardrails** (Semantic Entropy) and an **Architect Agent** (Governance), we explore how to build autonomous systems that remain within safe operating boundaries.
*   **Automation at Scale:** Traditional software engineering is bottlenecked by human review. The Studio demonstrates a path toward scaling engineering capacity through hierarchical, multi-agent collaboration.
*   **Autonomous Software Delivery:** The project researches the feasibility of a "Lights-Out" software factory, where the system is the primary engineer and the human acts as a high-level supervisor/approver.

### 當前功能快照 | Current Capability Snapshot
*   **Hierarchical Orchestration:** Uses LangGraph to manage complex state transitions across multiple agent roles.
*   **Autonomous TDD Loop:** Implementation of a strict Red-Green-Refactor cycle with automated testing (`pytest`) and code review.
*   **Self-Optimization (OPRO):** Ability to analyze failure patterns and surgically update agent prompts in `prompts.json` to improve future performance.
*   **Context Slicing & Guardrails:** Prevents context collapse and hallucinations via dynamic file filtering and Semantic Entropy monitoring (Circuit Breaker).
*   **Multi-Specialist BSP RCA:** Specialized agents for Kernel Pathological analysis and Hardware Datasheet correlation.

### 侷限性 | Limitations
*   **Cold Start Latency:** Initial system initialization and state graph setup can be time-intensive.
*   **Environment Specificity:** Currently optimized for Android BSP contexts; adapting to other domains requires significant blueprint and fixture updates.
*   **Deterministic Bottlenecks:** While agents are non-deterministic, the governance layer relies on deterministic tests which may not cover all edge cases in complex system failures.
*   **Model Dependency:** Highly optimized for the Gemini-2.5-Pro / Vertex AI stack; performance on smaller or different models is not yet validated.

---

### GitHub Topics
`ai-systems`, `multi-agent`, `autonomous-software-factory`, `langgraph`, `vertex-ai`, `android-bsp`, `ai-safety`, `opro`, `software-engineering-automation`

---

### Core Philosophy: Factory vs. Product
*   **The Studio (`studio/`):** The "Factory" infrastructure. It contains the Orchestrator, Agents (Architect, Product Owner, Engineer, Scrum Master, Optimizer), and the Governance rules. This is the "meta-level" system that builds the software.
*   **The Product (`product/`):** The output of the Studio. This includes the actual source code, prompts, and configurations for the Android BSP Consultant agent.

## Architecture

The system operates as a **Hierarchical State Machine** orchestrated by LangGraph, with strict **Context Slicing** and **Cognitive Guardrails**.

### The Agent Team
1.  **Orchestrator (The Executive):**
    *   Operates the High-Level Lifecycle (Plan -> Execute -> Review) via LangGraph.
    *   Enforces **Context Slicing** to isolate agents from irrelevant data.
    *   Monitors **Semantic Entropy** to prevent "hallucinations" or cognitive tunneling.
    *   Routes intents via **Intent Router** (Coding vs. Interactive Guide).
2.  **Product Owner (Strategy):**
    *   Translates `PRODUCT_BLUEPRINT.md` into a dependency-aware Directed Acyclic Graph (DAG) of tickets.
    *   Maintains the Product Backlog.
3.  **Engineer (Execution):**
    *   Jules Proxy: Manages asynchronous execution of coding tasks via remote workers using `JulesGitHubClient`.
    *   Implements the "Micro-Loop": Dispatch -> Watch -> Monitor (Entropy) -> Verify -> Feedback.
    *   Operates within a isolated **Docker Sandbox**.
4.  **Architect (Governance):**
    *   Reviews full source code against `AGENTS.md` (The Constitution) using `studio/agents/architect.py`.
    *   Enforces SOLID principles and security standards.
5.  **QA Verifier (Verification):**
    *   Implemented as a node within the Engineer Subgraph (`studio/subgraphs/engineer.py`).
    *   Runs deterministic tests (`pytest`) in a `DockerSandbox`.
    *   *(Note: `studio/qa_agent.py` exists as a standalone utility).*
6.  **Scrum Master (Review):**
    *   Analyzes sprint logs to identify process bottlenecks.
    *   Triggers the **Optimizer** for OPRO.
7.  **Optimizer (Evolution):**
    *   Implements **OPRO (Optimization by PROmpting)**.
    *   Surgically patches agent prompts in `prompts.json` to fix recurring behavioral failures.

### Key Features
*   **Optimization by PROmpting (OPRO):** The system self-corrects its own instructions (`prompts.json`) based on retrospective analysis, allowing it to "learn" from mistakes.
*   **Interactive Debugging (SOP Guide):** A logical subgraph (within the Orchestrator) for handling "No-Log" scenarios where the user needs guidance to extract data before analysis can begin.
*   **Semantic Entropy Guardrail:** Uses `VertexFlashJudge` to measure the uncertainty of agent outputs. If entropy (SE) exceeds 7.0, the "Circuit Breaker" triggers to prevent compounding errors and "Cognitive Tunneling".
*   **Context Slicing:** Dynamically filters the file system and logs presented to each agent (Event Horizon), ensuring they only see what is relevant to their current task to prevent context collapse.
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
│   ├── bsp_agent/          # Core logic of the product (Supervisor, Core state).
│   ├── prompts/            # Product prompts (optimized by Scrum Master).
│   ├── schemas.py          # Agent Persona Contracts & Case File definitions.
│   └── __init__.py         # Package initialization.
├── studio/                 # The Factory: The AI Software Studio.
│   ├── agents/             # Agent implementations (Architect, PO, Scrum Master, Optimizer).
│   ├── subgraphs/          # Subgraph definitions (Engineer).
│   ├── memory.py           # Pydantic models and State definitions.
│   ├── orchestrator.py     # Main runtime logic and StateGraph definition.
│   ├── manager.py          # State persistence and management.
│   ├── review_agent.py     # Review utility (Alternative/Legacy).
│   ├── qa_agent.py         # QA utility (Standalone).
│   ├── optimizer.py        # Legacy Optimizer script.
│   ├── rules.md            # Long-term Memory: Best practices & patterns.
│   └── utils/              # Utilities (Entropy Math, Sandbox, Patching, Prompts).
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


### Running the Factory
``bash
# To start the Docker daemon (the engine) before you try to apply group permissions or interact with it.
sudo systemctl start docker 
# Logging into a new shell session where your primary group ID is temporarily changed to the docker group.
newgrp docker
# Activate the Python virtual environment.
source venv/bin/activate
# Execute the production entry point.
PYTHONPATH=. python main.py run
```

## License

This project is licensed under the **MIT License**.

- **SPDX Identifier:** [MIT](https://opensource.org/licenses/MIT)
- **License Text:** See the [LICENSE](LICENSE) file in this repository for full details.
