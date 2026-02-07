# Android BSP Consultant Agent Team

## Project Overview
This repository hosts the code for the **Android BSP AI Consultant Team**, a specialized multi-agent system designed to analyze Android Kernel logs, perform root cause analysis (RCA), and suggest fixes for complex embedded systems issues (e.g., Suspend-to-Disk failures).

## Architecture
* **Governance:** Defined in `AGENTS.md` (The Studio/Builder Constitution).
* **Specification:** Defined in `PRODUCT_BLUEPRINT.md` (The Product Spec).
* **Core Logic:** Located in `bsp_agent/` (Python package).

## Development Protocol
1.  **Strict TDD:** No feature code without a failing test.
2.  **Schema First:** All agent interfaces must be defined in Pydantic models before implementation.
3.  **HIL Simulation:** We use "Consultancy Mode" (Log Analysis) as the MVP. No physical hardware actuation yet.

## Quick Start
1.  Install dependencies: `pip install -r requirements.txt`
2.  Run tests: `pytest tests/`
