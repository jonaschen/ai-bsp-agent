import json
import logging
import os

logger = logging.getLogger("studio.utils.prompts")

DEFAULT_PROMPTS = {
    "engineer": """You are a senior software engineer.
Your task is to implement the requested feature or fix the bug described.
Follow TDD principles: Red -> Green -> Refactor.
"""
}

# Backward Compatibility
ENGINEER_SYSTEM_PROMPT = DEFAULT_PROMPTS["engineer"]

DEFAULT_PROMPTS.update({
    "architect": """You are the Architect Agent.
Your goal is to ensure the codebase follows the defined constitution and architectural standards.
""",
    "product_owner": """You are the Product Owner.
Your goal is to manage the product backlog and ensure requirements are clear.
""",
    "scrum_master": """You are the Scrum Master.
Your goal is to optimize the studio processes and improve agent performance.
"""
})

PROMPTS_JSON = "prompts.json"

def fetch_system_prompt(role: str) -> str:
    """
    Fetches the system prompt for a given role.
    Learned (prompts.json) > Default (DEFAULT_PROMPTS).
    """
    prompts = {}
    if os.path.exists(PROMPTS_JSON):
        try:
            with open(PROMPTS_JSON, "r") as f:
                prompts = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load prompts from {PROMPTS_JSON}: {e}. Falling back to defaults.")
            prompts = {}

    return prompts.get(role, DEFAULT_PROMPTS.get(role, "You are a helpful AI assistant."))

def update_system_prompt(role: str, new_prompt: str):
    """
    Updates the system prompt for a given role and persists it to prompts.json.
    """
    prompts = {}
    if os.path.exists(PROMPTS_JSON):
        try:
            with open(PROMPTS_JSON, "r") as f:
                prompts = json.load(f)
        except (json.JSONDecodeError, IOError):
            prompts = {}

    prompts[role] = new_prompt

    try:
        with open(PROMPTS_JSON, "w") as f:
            json.dump(prompts, f, indent=4)
        logger.info(f"Updated system prompt for {role} and saved to {PROMPTS_JSON}.")
    except IOError as e:
        logger.error(f"Failed to save prompts to {PROMPTS_JSON}: {e}")
