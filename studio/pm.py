from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

# AGENTS.md Sec 5.1: Every agent script MUST define its system prompt as a top-level variable.
SYSTEM_PROMPT = """
You are the Product Manager for an Android BSP Analysis Studio.
Your input is a User Request and the current PRODUCT_BLUEPRINT.md.
Your output is a JSON Specification.

NEGATIVE CONSTRAINT: You must NEVER suggest Python libraries, code snippets, or architectural patterns. You only define behavior and outcomes.

The JSON MUST have the following keys:
- feature_title: A short, descriptive title for the feature.
- user_story: A standard user story format (As a..., I want..., so that...).
- acceptance_criteria: A list of specific, testable requirements.
"""

class ProductManager:
    """
    Product Manager (PM) — The Strategist
    Triggers Product Pipeline.
    Validates output against PRODUCT_BLUEPRINT.md.
    """

    def __init__(self, model_name="gemini-1.5-flash"):
        # Section 10 of AGENTS.md: MUST use langchain_google_vertexai.ChatVertexAI
        self.llm = ChatVertexAI(model_name=model_name, temperature=0)
        self.parser = JsonOutputParser()

    def analyze_request(self, request: str) -> dict:
        """
        Translates vague user requests into structured Product Specifications.
        Reads PRODUCT_BLUEPRINT.md for context.
        """
        blueprint_path = "PRODUCT_BLUEPRINT.md"
        blueprint_content = ""

        # AGENTS.md Sec 6: PM validates output against PRODUCT_BLUEPRINT.md.
        # It must read it to understand the current state.
        try:
            with open(blueprint_path, "r") as f:
                blueprint_content = f.read()
        except FileNotFoundError:
            blueprint_content = "# Product Blueprint\nNo blueprint found."

        prompt = f"USER REQUEST:\n{request}\n\nPRODUCT_BLUEPRINT.md:\n{blueprint_content}"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]

        # Invoke the LLM
        response = self.llm.invoke(messages)

        # Parse and return JSON
        # If the LLM returns a string with markdown blocks, JsonOutputParser handles it.
        result = self.parser.parse(response.content)
        return result
