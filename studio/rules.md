# AI Studio Design Patterns & Best Practices

This file serves as the **Long-term Memory** for the development team.
It contains universal patterns derived from past failures recorded in `review_history.md`.

> **Rule of Thumb:** Before implementing complex logic, check if a pattern here applies.

---

## 1. Testing Patterns (TDD)

### 1.1 Pydantic Model Mocking (The "Agentic Loop" Preventer)
* **Context:** LangChain uses Pydantic v2 heavily for data structures (e.g., `Generation`, `AIMessage`).
* **Problem:** Passing `MagicMock` objects to Pydantic fields (e.g., `Generation(text=mock_obj)`) causes `pydantic_core.ValidationError` because strict type checking rejects the Mock object.
* **Consequence:** This often leads to infinite **Agentic Loops** where the AI tries to fix the logic but fails to fix the test setup.
* **Solution:** Always use **concrete types (literals)** for Pydantic fields in tests. Do NOT mock the data container itself if it validates types.

**Code Example:**
```python
# ❌ BAD (Will fail validation)
mock_content = MagicMock()
result = Generation(text=mock_content) 

# ✅ GOOD (Passes validation)
result = Generation(text="actual string content")
```


### 1.2 External API Mocking

* **Rule:** Never let unit tests hit real APIs (Google Books, Tavily).
* **Pattern:** Use `unittest.mock.patch` for all network calls.
* **Safety Net:** Tests requiring real network access must be marked with `@pytest.mark.integration`.

---

## 2. Architecture Patterns

### 2.1 The "Fallback" Pattern

* **Context:** Critical dependencies (like Google Books API) have rate limits.
* **Rule:** Primary data sources MUST have a secondary fallback implemented within the same node or function.
* **Example:** ```python
try:
return GoogleBooks.search(query)
except RateLimitError:
return Tavily.search(query)


---

## 3. Coding Standards

* **Environment Variables:** Always load via `dotenv.load_dotenv()` at the entry point (if `__name__ == "__main__":`).
* **Type Hinting:** Use Python 3.10+ type hints (`list[str] | None`) for clarity.


---
## 4. Cognitive Governance Patterns (The "Sanity" Checks)
**Goal:** Prevent AI agents from entering "Cognitive Tunneling" (loops) or "Hallucination" states.

### 4.1 The Cognitive Tunneling Breaker
* **Context:** Agents running long-term tasks often get stuck in repetitive loops, executing valid but useless actions (e.g., repeatedly searching the same keyword).

* **Rule:** Agents MUST implement Trajectory Similarity Checks.

* **Constraint:**

  If an agent's last 3 actions have a cosine similarity > 0.9 (i.e., doing the same thing with slightly different words), force a "Stop & Reflect" interrupt.

  Agents MUST log their "Thought Trace" to enable this analysis.

### 4.2 Semantic Entropy Guardrail
* **Context:** When an agent hallucinates or is unsure, its output uncertainty (Semantic Entropy) spikes.

* **Rule:** If Semantic Entropy > 2.0 (or confidence score < 0.3), reject the output immediately.

* **Action:**

  * **Trigger Fallback:** Escalate to a more capable model (e.g., Gemini 1.5 Pro) or pause for human clarification.

  * **Do Not Guess:** It is better to fail and ask for help than to proceed with low confidence.

## 5. Architectural Constraints (The "Scaling" Laws)
Goal: Prevent "Error Amplification" where one agent's mistake cascades through the system.

### 5.1 Centralized Orchestration Mandate
* **Context:** Decentralized multi-agent systems amplify errors by up to 17.2x. Centralized systems restrict this to 4.4x.

* **Rule:** No agent shall act autonomously without a Manager or Planner node validating its output.

* **Pattern:** Follow the Planner-Worker-Verifier hierarchy. The Worker writes code, but only the Planner/Manager has the authority to merge or deploy it.

### 5.2 Tool Specialization Limit
* **Context:** Coordination efficiency drops significantly when an agent has access to too many tools (cognitive overload).

* **Rule: Specialization over Generalization.**

* **Constraint:**

  * No single agent shall have access to more than 16 tools.

  * **Micro-Agents:** Instead of one "Super Coder", split responsibilities into micro-agents:

    * GitAgent (only git operations)

    * LinterAgent (only static analysis)

    * SQLAgent (only database queries)

### 5.3 Vendor Lock-in Enforcement (Google Vertex AI)
* **Context:** We enforce a unified model stack to simplify IAM and billing.
* **Rule:** Codebases must not import unauthorized LLM providers.
* **Prohibited Imports:**
    * `import openai`
    * `from langchain_openai ...`
    * `from langchain_anthropic ...`
* **Authorized Import:**
    * `from langchain_google_vertexai import ChatVertexAI`
* **Configuration:** All agents must initialize models using `project` and `location` from environment variables, not hardcoded strings.
  
## 6. Agile Process Patterns (Team Health)
**Goal:** Ensure the team improves how it works (Process), not just what it builds (Product).

### 6.1 Context-Aware Retrospectives
* **Context:** Using the same retrospective format every time leads to stagnation. The format must match the team's current situation.

* **Rule:** The Scrum Master MUST select the format based on System Status:

  * **Case A:** High Failure Rate / Crash (Repair Mode)

     * **Format:** Mad-Sad-Glad.

     * **Focus:** Emotional health and root cause analysis of the failure.

  * **Case B:** Stable but Stagnant (Optimization Mode)

     * **Format:** Start-Stop-Continue.

     * **Focus:** Efficiency, removing waste, and new experiments.

### 6.2 The Definition of Done (DoD)
* **Context:** Agents often claim a task is complete when code is generated, not when it is verified.

* **Rule:** No Ticket or Issue is considered "Done" until:

1. **Code Compiles:** No syntax errors.

2. **Tests Pass:** The "Green Bar" is achieved in the QA Agent pipeline.

3. **Linting Clean:** No new violations of flake8 or rules.md introduced.

4. **No Hallucinations:** All external libraries used must be verified to exist.
