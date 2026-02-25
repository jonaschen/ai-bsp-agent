import os
import json
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from langchain_google_vertexai import ChatVertexAI
from studio.utils.prompts import fetch_system_prompt, update_system_prompt, DEFAULT_PROMPTS, PROMPTS_JSON
from studio.agents.optimizer import OptimizerAgent
from studio.memory import RetrospectiveReport, ProcessOptimization

@pytest.fixture(autouse=True)
def cleanup_prompts_json():
    # Ensure directory exists for tests
    os.makedirs(os.path.dirname(PROMPTS_JSON), exist_ok=True)
    if os.path.exists(PROMPTS_JSON):
        os.remove(PROMPTS_JSON)
    yield
    if os.path.exists(PROMPTS_JSON):
        os.remove(PROMPTS_JSON)

def test_prompts_default_fallback():
    # When prompts.json is missing, it should return default
    prompt = fetch_system_prompt("engineer")
    assert prompt == DEFAULT_PROMPTS["engineer"]

def test_prompts_learned_priority():
    # When prompts.json exists, it should return learned prompt
    learned = {"engineer": "You are a specialized AI engineer."}
    with open(PROMPTS_JSON, "w") as f:
        json.dump(learned, f)

    prompt = fetch_system_prompt("engineer")
    assert prompt == learned["engineer"]

def test_prompts_corruption_fallback():
    # When prompts.json is corrupted, it should return default
    with open(PROMPTS_JSON, "w") as f:
        f.write("corrupted json")

    prompt = fetch_system_prompt("engineer")
    assert prompt == DEFAULT_PROMPTS["engineer"]

def test_prompts_update_and_persistence():
    # Should update and persist to prompts.json
    new_prompt = "New prompt content"
    update_system_prompt("engineer", new_prompt)

    with open(PROMPTS_JSON, "r") as f:
        data = json.load(f)
    assert data["engineer"] == new_prompt

    assert fetch_system_prompt("engineer") == new_prompt

@patch("studio.agents.optimizer.ChatVertexAI")
def test_optimizer_apply_optimizations(mock_chat):
    # Mock LLM response
    mock_llm = MagicMock(spec=ChatVertexAI)
    mock_chat.return_value = mock_llm

    # Mock the return value of the LLM
    mock_llm.invoke.return_value = AIMessage(content="REWRITTEN PROMPT")

    report = RetrospectiveReport(
        sprint_id="SPRINT-1",
        success_rate=0.5,
        avg_entropy_score=2.0,
        key_bottlenecks=["Testing"],
        optimizations=[
            ProcessOptimization(
                target_role="The Engineer",
                issue_detected="Too slow",
                suggested_prompt_update="Be faster",
                expected_impact="High"
            )
        ]
    )

    optimizer = OptimizerAgent()
    optimizer.apply_optimizations(report)

    # Check if prompt was updated (the role "The Engineer" should map to "engineer")
    assert fetch_system_prompt("engineer") == "REWRITTEN PROMPT"
