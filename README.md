# Android BSP AI Consultant Team (The Studio)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Version:** v5.2.0 (Phase 3: Evolution & Reality)
> **Status:** Research Prototype / Serious AI Systems Engineering
>
> *Note: While the system design targets Phase 3 (v5.2.0), the codebase currently initializes with a "Cold Start" version of v1.0.0 via `main.py`.*

## Project Overview

This repository hosts the **Android BSP Diagnostic Expert** (also known as "The Studio"), a specialized multi-agent system designed to autonomously build, verify, and maintain high-quality software products.

The primary product being built is the **Android BSP Consultant**, an AI agent capable of analyzing Android Kernel logs, performing root cause analysis (RCA), and suggesting fixes for complex embedded systems issues (e.g., Suspend-to-Disk failures).

### 市場定位 | Market Positioning
The **Android BSP Diagnostic Expert** occupies a unique niche by utilizing the Anthropic Tool-Use / Agent Skill paradigm. It serves as a **Specialized AI Systems Research Prototype** for:
*   **Domain-Specific Expertise:** Focusing on the high-stakes, log-intensive environment of Android Board Support Package (BSP) development.
*   **Deterministic Reasoning:** Replacing error-prone AI code generation with deterministic, human-authored Python tools that provide ground truth for the reasoning LLM.

### 為何重要 | Why This Matters
*   **Accuracy over Autonomy:** By enforcing strict tool use, we prevent LLM hallucinations regarding hardware state and register calculations.
*   **Automation at Scale:** The Studio demonstrates a path toward scaling engineering capacity through expert agent collaboration.
*   **Autonomous Software Delivery:** The project researches the feasibility of a "Lights-Out" software factory, where the system is the primary engineer and the human acts as a high-level supervisor/approver.

### 當前功能快照 | Current Capability Snapshot
*   **Skill-Based Architecture:** Uses a reasoning LLM paired with deterministic Python tools (Skills).
*   **Multi-Specialist BSP RCA:** Specialized analysis for NULL pointer dereferences and watchdog hard lockups during suspend.
*   **Deterministic Execution:** Strict separation of reasoning (LLM) and data extraction (Python Tools).

### 侷限性 | Limitations
*   **Cold Start Latency:** Initial system initialization and state graph setup can be time-intensive.
*   **Environment Specificity:** Currently optimized for Android BSP contexts; adapting to other domains requires significant blueprint and fixture updates.
*   **Deterministic Bottlenecks:** While agents are non-deterministic, the governance layer relies on deterministic tests which may not cover all edge cases in complex system failures.
*   **Model Dependency:** Highly optimized for the Gemini-2.5-Pro / Vertex AI stack; performance on smaller or different models is not yet validated.

---

### GitHub Topics
`ai-systems`, `multi-agent`, `autonomous-software-factory`, `langgraph`, `vertex-ai`, `android-bsp`, `ai-safety`, `opro`, `software-engineering-automation`

---

## Architecture

The system operates as a **Skill-Based Expert Agent** using the Anthropic Tool-Use paradigm. It consists of three main layers:

### The Agent Team / Layers
1.  **The Brain (The Reasoning Engine):**
    *   A streamlined LangGraph or direct LLM loop.
    *   Understands the user's intent, selects appropriate Tools, and formats the final RCA report.
    *   **Constraint:** The Brain never performs complex calculations directly; it delegates to Tools.
2.  **The Skill Registry (The Tools):**
    *   Pure Python functions located in the `skills/` directory.
    *   Deterministic, human-written scripts that extract the truth (e.g., parsing logs, checking thresholds).
    *   Every tool has a strict Pydantic schema for inputs and outputs.
3.  **The Knowledge Base:**
    *   Markdown files (e.g., `SKILL.md`) containing deep architectural knowledge.
    *   Uses progressive disclosure to feed the LLM context only when needed.

## Repository Structure


```
.
├── AGENTS.md               # The Constitution: Rules and Governance for all agents.
├── PRODUCT_BLUEPRINT.md    # The Product Spec: What the Agent is built to diagnose.
├── README.md               # This file.
├── product/                # Core logic of the product.
│   ├── bsp_agent/          # Supervisor and Agent definitions.
│   ├── schemas/            # Agent Persona Contracts & Case File definitions.
│   └── __init__.py         # Package initialization.
├── skills/                 # The Skill Registry: Deterministic Python tools.
├── studio/                 # Utility scripts and test frameworks (legacy).
└── tests/                  # Test suite and Simulations.
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
```bash
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
