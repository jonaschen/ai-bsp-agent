import logging
from typing import Dict, Any, List
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from studio.utils.prompts import fetch_system_prompt, update_system_prompt
from studio.memory import RetrospectiveReport, ProcessOptimization

logger = logging.getLogger("studio.agents.optimizer")

class OptimizerAgent:
    """
    The Optimizer Agent (The Surgeon).
    Implements OPRO (Optimization by PROmpting).
    It reads RetrospectiveReports and updates agent system prompts.
    """
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.llm = ChatVertexAI(
            model_name=model_name,
            temperature=0.1,  # Precise and conservative updates
            max_output_tokens=4096
        )

        # Mapping from Scrum Master role names to prompt registry keys
        self.role_mapping = {
            "The Engineer": "engineer",
            "Engineer": "engineer",
            "The Architect": "architect",
            "Architect": "architect",
            "The Product Owner": "product_owner",
            "Product Owner": "product_owner",
            "The Scrum Master": "scrum_master",
            "Scrum Master": "scrum_master"
        }

    def _get_registry_key(self, role_name: str) -> str:
        """Maps a role name to its registry key."""
        return self.role_mapping.get(role_name, role_name.lower().replace(" ", "_"))

    def apply_optimizations(self, report: RetrospectiveReport):
        """
        Iterates through the optimizations in the report and updates the prompts.
        """
        logger.info(f"Optimizer: Applying optimizations from report {report.sprint_id}...")
        for opt in report.optimizations:
            registry_key = self._get_registry_key(opt.target_role)
            current_prompt = fetch_system_prompt(registry_key)

            logger.info(f"Optimizer: Updating prompt for {opt.target_role} ({registry_key})...")
            new_prompt = self._rewrite_prompt(current_prompt, opt)

            if new_prompt:
                update_system_prompt(registry_key, new_prompt)
            else:
                logger.warning(f"Optimizer: Failed to rewrite prompt for {opt.target_role}.")

    def _rewrite_prompt(self, current_prompt: str, optimization: ProcessOptimization) -> str:
        """
        Uses meta-prompting to integrate a new rule into the existing prompt.
        """
        meta_prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an AI Prompt Engineer specializing in OPRO (Optimization by PROmpting).
            Your goal is to integrate a NEW RULE into an existing AI System Prompt.

            **CRITICAL CONSTRAINTS:**
            1. Preserve the core identity and existing instructions of the agent.
            2. Integrate the NEW RULE organically into the appropriate section.
            3. Do NOT just append the rule at the end if it can be merged with existing rules.
            4. Keep the output clean and concise.
            5. Output ONLY the updated prompt text.
            """),
            ("user", """
            **EXISTING PROMPT:**
            {current_prompt}

            **NEW RULE TO INTEGRATE:**
            Issue Detected: {issue_detected}
            Suggested Update: {suggested_prompt_update}

            **UPDATED PROMPT:**
            """)
        ])

        chain = meta_prompt | self.llm | StrOutputParser()

        try:
            new_prompt = chain.invoke({
                "current_prompt": current_prompt,
                "issue_detected": optimization.issue_detected,
                "suggested_prompt_update": optimization.suggested_prompt_update
            })
            return new_prompt.strip()
        except Exception as e:
            logger.error(f"Optimizer failed to rewrite prompt: {e}")
            return None
