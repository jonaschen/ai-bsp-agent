import os
from typing import Literal, List
from pydantic import BaseModel
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

# AGENTS.md Sec 5.1: Every agent script MUST define its system prompt as a top-level variable.
SYSTEM_PROMPT_MAD_SAD_GLAD = """
You are the Scrum Master performing a 'Repair Mode' retrospective using the Mad-Sad-Glad format.
The system is experiencing a high failure rate. Analyze the review history and identify impediments.

Format your output as a list of EvolutionTicket objects.
Mad: What is frustrating the team? (e.g., repeating syntax errors)
Sad: What is disappointing? (e.g., low test coverage)
Glad: What is working well? (e.g., fast iteration)

Focus on root causes and actionable improvements.
"""

SYSTEM_PROMPT_START_STOP_CONTINUE = """
You are the Scrum Master performing an 'Optimization Mode' retrospective using the Start-Stop-Continue format.
The system is stable. Analyze the review history to find ways to increase efficiency.

Format your output as a list of EvolutionTicket objects.
Start: What new practices should we adopt?
Stop: What is wasting time and should be stopped?
Continue: What is working well and should be reinforced?
"""

class EvolutionTicket(BaseModel):
    title: str
    type: Literal["PROCESS_IMPROVEMENT", "REFACTORING", "TOOLING"]
    description: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]

class TicketList(BaseModel):
    tickets: List[EvolutionTicket]

class ScrumMasterAgent:
    """
    Scrum Master Agent — The Process Guardian
    Focus: Team Health, Process Efficiency, and Continuous Improvement (Kaizen).
    """
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name
        # model will be initialized in conduct_retrospective to allow for dynamic selection if needed
        # but configured to use gemini-1.5-flash as requested.

    def _calculate_health_metrics(self, history_text: str) -> float:
        """
        Parses "PASS/FAIL" strings to determine failure rate.
        """
        lines = history_text.strip().split("\n")
        total = 0
        failures = 0
        for line in lines:
            if " - PASS" in line or " - FAIL" in line:
                total += 1
                if " - FAIL" in line:
                    failures += 1

        if total == 0:
            return 0.0
        return failures / total

    def _select_retrospective_strategy(self, failure_rate: float) -> str:
        """
        Returns the specific prompt template based on failure rate.
        Case A: > 20% failure -> Mad-Sad-Glad
        Case B: <= 20% failure -> Start-Stop-Continue
        """
        if failure_rate > 0.20:
            return SYSTEM_PROMPT_MAD_SAD_GLAD
        return SYSTEM_PROMPT_START_STOP_CONTINUE

    def conduct_retrospective(self, history_text: str) -> List[EvolutionTicket]:
        """
        The main retrospective logic.
        """
        failure_rate = self._calculate_health_metrics(history_text)
        system_prompt = self._select_retrospective_strategy(failure_rate)

        llm = ChatVertexAI(
            model_name=self.model_name,
            temperature=0.2,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )

        # We want a list of EvolutionTicket
        parser = PydanticOutputParser(pydantic_object=TicketList)

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + "\n{format_instructions}"),
            ("user", "Analyze the following history:\n{history}")
        ])

        chain = prompt | llm | parser

        try:
            result = chain.invoke({
                "history": history_text,
                "format_instructions": parser.get_format_instructions()
            })
            return result.tickets
        except Exception as e:
            # Fallback or empty list on error
            print(f"Error during retrospective: {e}")
            return []

    def get_recommendations(self, history_path: str = "review_history.md") -> List[EvolutionTicket]:
        """
        Primary entry point. Reads file -> Selects Strategy -> Invokes LLM -> Returns objects.
        """
        if not os.path.exists(history_path):
            return []

        with open(history_path, "r") as f:
            history_text = f.read()

        return self.conduct_retrospective(history_text)
