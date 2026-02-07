import os
import sys
from typing import Optional
from unittest.mock import MagicMock
from dotenv import load_dotenv
from github import Github
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 確保能讀取到環境變數
load_dotenv()

class Architect:
    """
    The Architect is the bridge between Human Strategy and AI Execution.
    It translates high-level goals into precise, TDD-compliant GitHub Issues.
    """

    def __init__(self, repo_name: Optional[str] = None, rules_path: str = "studio/rules.md", history_path: str = "studio/review_history.md"):
        repo_name = repo_name or os.getenv("GITHUB_REPO_NAME", "jonaschen/ai-knowledge-agent")
        token = os.getenv("GITHUB_TOKEN")

        # Check if we are in a test environment
        is_testing = "PYTEST_CURRENT_TEST" in os.environ or any('pytest' in arg for arg in sys.argv)

        if not token:
            if is_testing:
                 self.github = MagicMock()
                 self.repo = MagicMock()
            else:
                raise ValueError("❌ CRITICAL: GITHUB_TOKEN not found in .env file. Architect cannot work without it.")
        else:
            self.github = Github(token)
            self.repo = self.github.get_repo(repo_name)

        # 使用 Gemini 2.5 Pro 作為大腦，Temperature 稍高以利於規劃
        if is_testing:
            self.llm = MagicMock()
        else:
            self.llm = ChatVertexAI(
                model_name="gemini-3-pro-preview",
                location="global",
                temperature=0.2,
                max_output_tokens=8192
            )

        # 載入憲法 (Constitution)
        # 注意：搬家後 AGENTS.md 應該還是在根目錄，所以路徑可能需要調整
        try:
            with open("AGENTS.md", "r", encoding="utf-8") as f:
                self.constitution = f.read()
        except FileNotFoundError:
            print("⚠️ Warning: AGENTS.md not found. Architect is operating without a constitution.")
            self.constitution = "Focus on reliability and modularity."

        # Load Long-term Memory (Rules)
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                self.rules = f.read()
        except FileNotFoundError:
            self.rules = ""

        # Load Active Memory (Review History)
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                self.history = f.read()
        except FileNotFoundError:
            self.history = ""

        try:
            with open("PRODUCT_BLUEPRINT.md", "r", encoding="utf-8") as f:
                self.blueprint = f.read()
        except FileNotFoundError:
            print("⚠️ Warning: PRODUCT_BLUEPRINT.md not found. Architect is flying blind.")
            self.blueprint = "No spec provided."

    def draft_issue(self, user_request: str) -> dict:
        # ... (Bug detection logic remains the same) ...

        print(f"🏗️ Architect is analyzing request: '{user_request}'...")

        # [FIXED] Dynamic System Prompt
        system_prompt = """
        You are the Chief Software Architect for an AI Software Studio.
        
        === YOUR CONSTITUTION (AGENTS.md) ===
        {constitution}
        
        === THE PRODUCT SPECIFICATION (PRODUCT_BLUEPRINT.md) ===
        {blueprint}
        
        === KNOWLEDGE BASE ===
        RULES (rules.md): {rules}
        RECENT FAILURES (review_history.md): {history}

        === TEAM STRUCTURE ===
        1. Studio Team (Internal Tools): Manages the factory (studio/).
        2. Product Team (Target Output): Defined in the BLUEPRINT above.
           (e.g., Screener, Pathologist, Librarian)

        === USER REQUEST ===
        {request}

        === INSTRUCTIONS ===
        1. Analyze the User Request against the PRODUCT_BLUEPRINT.
        2. If the Blueprint defines specific Agents (e.g., Pathologist), assign tasks to them explicitly.
        3. Enforce the TDD Mandate: ALWAYS define a test case using the fixtures defined in the Blueprint (e.g., tests/fixtures/panic_log_01.txt).

        Draft a GitHub Issue in the following format:
        Title: [Component] [Type] <Title>
        Body:
        @jules
        <Objective>
        
        ### Step 1: The Test Spec
        (Reference specific fixtures or write a new test case)
        
        ### Step 2: Implementation Plan
        (Which files in bsp_agent/ need changes?)
        """

        prompt = ChatPromptTemplate.from_template(system_prompt)
        chain = prompt | self.llm | StrOutputParser()

        raw_output = chain.invoke({
            "constitution": self.constitution,
            "blueprint": self.blueprint, # [NEW] Inject the specific BSP spec
            "rules": self.rules,
            "history": self.history,
            "request": user_request
        })

        return self._parse_issue_content(raw_output)



    def _parse_issue_content(self, issue_content: str) -> dict:
        """
        Parses the raw LLM string into a structured dictionary.
        """
        lines = issue_content.strip().split("\n")
        title = lines[0].replace("Title:", "").strip()

        # 尋找 Body 的開始
        body_start = 0
        for i, line in enumerate(lines):
            if "Body:" in line:
                body_start = i + 1
                break

        body = "\n".join(lines[body_start:]).strip()

        return {
            "title": title,
            "body": body,
            "labels": ["jules", "architect-approved"]
        }

    def create_issue(self, title: str, body: str, labels: list):
        """
        Creates an issue on GitHub.
        """
        try:
            issue = self.repo.create_issue(
                title=title,
                body=body,
                labels=labels
            )
            print(f"🚀 Published Issue #{issue.number}.")
            return issue
        except Exception as e:
            print(f"❌ Failed to create GitHub issue: {e}")
            raise

    def publish_issue(self, issue_dict: dict):
        """
        發布 Issue 到 GitHub
        """
        title = issue_dict["title"]
        body = issue_dict["body"]
        labels = issue_dict.get("labels", ["jules", "architect-approved"])

        print("\n" + "="*50)
        print(f"Proposed Issue: {title}")
        print("-" * 50)
        print(body[:500] + "...\n(content truncated for preview)")
        print("="*50)

        confirm = input(">> Approve and Publish to Jules? (y/n): ")
        if confirm.lower() == 'y':
            self.create_issue(
                title=title,
                body=body,
                labels=labels
            )
            print(f"Jules is on it.")
        else:
            print("❌ Cancelled.")

    def trigger_bug_report(self, error_log: str):
        """
        Creates a GitHub issue for a bug report.
        Enforces a strict Draft -> Create pipeline.
        """
        # Phase 1: Draft
        draft = self.draft_issue(error_log)

        # Phase 2: Create
        return self.create_issue(
            title=draft["title"],
            body=draft["body"],
            labels=draft["labels"]
        )

def trigger_bug_report(error_details: dict):
    """
    Deprecated: Use Architect().trigger_bug_report(details)
    """
    arch = Architect()
    arch.trigger_bug_report(str(error_details))


# --- CLI Entry Point ---
if __name__ == "__main__":
    # 讀取 Repo 名稱 (建議從 .env 讀取或直接寫死)
    REPO_NAME = os.getenv("GITHUB_REPO_NAME", "jonaschen/ai-knowledge-agent")

    if len(sys.argv) < 2:
        print("Usage: python -m studio.architect 'Your feature request here'")
        sys.exit(1)

    user_request = sys.argv[1]

    architect = Architect(REPO_NAME)
    plan = architect.draft_issue(user_request)
    architect.publish_issue(plan)
