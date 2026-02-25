import logging
from typing import Dict, Any, List
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from studio.utils.prompts import fetch_system_prompt, update_system_prompt
from studio.memory import RetrospectiveReport, ProcessOptimization
from studio.utils.sandbox import OptimizerSandbox

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
        Enforces ACL containment protocol and uses Sandboxed execution for writes.
        """
        from studio.utils.acl import verify_write_permission
        from studio.utils.prompts import PROMPTS_JSON

        logger.info(f"Optimizer: Applying optimizations from report {report.sprint_id}...")

        # Enforce ACL on the prompt registry file itself
        verify_write_permission(PROMPTS_JSON)

        # Initialize the sandbox for this optimization cycle
        sandbox = None
        try:
            logger.info("Optimizer: Initializing OptimizerSandbox for secure write operations...")
            sandbox = OptimizerSandbox()
        except Exception as e:
            logger.warning(f"Optimizer: Failed to initialize Docker sandbox: {e}. Falling back to ACL-only host execution.")

        for opt in report.optimizations:
            registry_key = self._get_registry_key(opt.target_role)

            # Additional safety: ensure registry_key doesn't contain path traversal
            if ".." in registry_key or "/" in registry_key:
                 # If someone tries to use a path as a role name, we block it
                 logger.error(f"Optimizer: ACL Violation - Malicious role name detected: {registry_key}")
                 raise PermissionError(f"Malicious role name detected: {registry_key}")

            current_prompt = fetch_system_prompt(registry_key)

            logger.info(f"Optimizer: Updating prompt for {opt.target_role} ({registry_key})...")
            new_prompt = self._rewrite_prompt(current_prompt, opt)

            if new_prompt:
                if sandbox:
                    self._update_system_prompt_sandboxed(sandbox, registry_key, new_prompt)
                else:
                    update_system_prompt(registry_key, new_prompt)
            else:
                logger.warning(f"Optimizer: Failed to rewrite prompt for {opt.target_role}.")

        if sandbox:
            sandbox.teardown()

    def _update_system_prompt_sandboxed(self, sandbox: OptimizerSandbox, role: str, new_prompt: str):
        """
        Executes the prompt update inside the restricted OptimizerSandbox.
        """
        logger.info(f"Optimizer: Executing sandboxed write for role: {role}")

        # We use a base64 encoded string to safely pass the prompt content to the container
        import base64
        encoded_prompt = base64.b64encode(new_prompt.encode('utf-8')).decode('utf-8')

        # Python script to run inside the container
        # Note: /app/product/prompts/prompts.json is mounted RW from host product/prompts/prompts.json
        py_script = f"""
import json, os, base64
path = '/app/product/prompts/prompts.json'
role = '{role}'
content = base64.b64decode('{encoded_prompt}').decode('utf-8')
data = {{}}
if os.path.exists(path):
    with open(path, 'r') as f:
        data = json.load(f)
data[role] = content
with open(path, 'w') as f:
    json.dump(data, f, indent=4)
"""
        result = sandbox.run_command(f"python3 -c \"{py_script}\"")
        if result.exit_code != 0:
            logger.error(f"Optimizer: Sandboxed write failed: {result.stderr}")
            # Fallback to host write if sandbox failed but we have ACL
            update_system_prompt(role, new_prompt)

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
