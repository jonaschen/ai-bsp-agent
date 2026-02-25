import os
import re
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from studio.utils.sandbox import OptimizerSandbox

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class OptimizerAgent:
    """
    The Evolver Agent.
    Implements OPRO (Optimization by PROmpting).
    It reads failure logs and optimizes the SYSTEM_PROMPT of other agents.
    Adheres to SOLID: Focuses solely on prompt optimization (SRP).
    """
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN not found.")
        
        # Use a high-reasoning model for meta-prompting
        self.llm = ChatVertexAI(
            model_name="gemini-2.5-pro",
            temperature=0.4, # Slightly creative to find better prompts
            max_output_tokens=8192
        )
        
        self.history_path = "studio/review_history.md"

    def apply_prompt_update(self, target_file_path: str, new_content: str):
        """
        Writes the optimized prompt content to the product prompts directory.
        Enforces ACL containment protocol and uses Sandboxed execution for writes.
        """
        from studio.utils.acl import verify_write_permission

        # In legacy mode, we might be passed a path like 'studio/agents/engineer.py'
        # We redirect these to 'product/prompts/'
        original_path = Path(target_file_path)
        candidate_dir = Path("product/prompts")
        candidate_path = candidate_dir / original_path.name

        # ENFORCE ACL
        verify_write_permission(str(candidate_path))

        # Initialize the sandbox for this update
        sandbox = None
        try:
            self.logger.info("Optimizer: Initializing OptimizerSandbox for secure write operation...")
            sandbox = OptimizerSandbox()
        except Exception as e:
            self.logger.warning(f"Optimizer: Failed to initialize Docker sandbox: {e}. Falling back to ACL-only host execution.")

        if sandbox:
            self._apply_prompt_update_sandboxed(sandbox, original_path.name, new_content)
            sandbox.teardown()
        else:
            # Fallback to direct host write with ACL protection
            os.makedirs(candidate_dir, exist_ok=True)
            candidate_path.write_text(new_content)

        # Log for the Manager/Reviewer
        self.logger.info(
            f"Candidate written to product/prompts/{original_path.name}. Waiting for Reviewer verification."
        )

    def _apply_prompt_update_sandboxed(self, sandbox: OptimizerSandbox, filename: str, content: str):
        """
        Executes the prompt update inside the restricted OptimizerSandbox.
        """
        self.logger.info(f"Optimizer: Executing sandboxed write for file: {filename}")

        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        # Path in container (mounted RW from host product/prompts/)
        path = f"/app/product/prompts/{filename}"

        py_script = f"""
import base64
path = '{path}'
content = base64.b64decode('{encoded_content}').decode('utf-8')
with open(path, 'w') as f:
    f.write(content)
"""
        result = sandbox.run_command(f"python3 -c \"{py_script}\"")
        if result.exit_code != 0:
            self.logger.error(f"Optimizer: Sandboxed write failed: {result.stderr}")
            # Fallback to host write
            candidate_path = Path("product/prompts") / filename
            candidate_path.write_text(content)

    def analyze_failures(self, target_file: str) -> str:
        """
        Reads the review history to find failures related to the target file.
        """
        if not os.path.exists(self.history_path):
            return "No history available."
            
        with open(self.history_path, "r") as f:
            history = f.read()
            
        # Simple filter: In a real system, this would use LLM to extract relevant context
        # For now, we assume the history contains relevant keywords (like filename)
        # Rudimentary filter to get last few KBs of history
        return history[-5000:] 

    def optimize_prompt(self, target_file_path: str):
        """
        Reads the target python file, extracts the SYSTEM_PROMPT, 
        and generates an optimized version based on failure history.
        """
        logging.info(f"🧬 Optimizing prompt for: {target_file_path}")
        
        if not os.path.exists(target_file_path):
            logging.error(f"Target file {target_file_path} not found.")
            return

        with open(target_file_path, "r") as f:
            code_content = f.read()

        # 1. Extract current prompt using Regex (Assumes CAPITALIZED_VAR = """)
        # Looking for variable assignment like: SYSTEM_PROMPT = """...""" or PROMPT = f"""..."""
        # This regex looks for a variable name in ALL_CAPS followed by triple quotes
        match = re.search(r'([A-Z_]+_PROMPT)\s*=\s*(f?\"\"\".*?\"\"\")', code_content, re.DOTALL)
        
        if not match:
            logging.warning(f"No optimization target (SYSTEM_PROMPT) found in {target_file_path}. Skipping.")
            return

        var_name = match.group(1)
        current_prompt = match.group(2)
        
        # 2. Get Failure Context
        failure_context = self.analyze_failures(target_file_path)
        
        # 3. Meta-Prompting (OPRO)
        opro_prompt = """
        You are an AI Optimization Engineer implementing OPRO (Optimization by PROmpting).
        
        Your Goal: Optimize the System Prompt for an AI Agent to prevent future failures.
        
        === TARGET AGENT SOURCE ===
        File: {filename}
        Variable: {var_name}
        Current Content:
        {current_prompt}
        
        === FAILURE HISTORY & FEEDBACK ===
        {failure_context}
        
        === INSTRUCTIONS ===
        1. Analyze why the current prompt failed based on the history (e.g., hallucinations, JSON errors).
        2. Generate a NEW, IMPROVED prompt that addresses these specific edge cases.
        3. Maintain the original intent but strengthen the constraints.
        4. Apply SOLID principles: ensure the prompt focuses on the agent's Single Responsibility.
        
        Output ONLY the new python code block for the variable assignment. 
        Example: 
        {var_name} = \"\"\"
        New optimized content...
        \"\"\"
        """
        
        chain = ChatPromptTemplate.from_template(opro_prompt) | self.llm | StrOutputParser()
        
        optimized_assignment = chain.invoke({
            "filename": target_file_path,
            "var_name": var_name,
            "current_prompt": current_prompt,
            "failure_context": failure_context
        })
        
        # Clean up Markdown formatting if present
        optimized_assignment = optimized_assignment.replace("```python", "").replace("```", "").strip()
        
        # 4. Apply the Patch (Surgical Replacement)
        if optimized_assignment and var_name in optimized_assignment:
            new_code_content = code_content.replace(match.group(0), optimized_assignment)
            
            self.apply_prompt_update(target_file_path, new_code_content)

            self.logger.info(f"✅ Created candidate for {target_file_path}")
            # In Level 5, we would now trigger a git commit or PR creation here.
            # For now, we assume the user/Manager triggers the commit loop.
        else:
            logging.error("Optimization failed to produce valid code.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m studio.optimizer <target_file_path>")
        sys.exit(1)
        
    optimizer = OptimizerAgent()
    optimizer.optimize_prompt(sys.argv[1])
