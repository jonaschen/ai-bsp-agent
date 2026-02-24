"""
studio/agents/codebase_analyzer.py
----------------------------------
The Codebase Analyzer Agent.
Performs repository-wide scans for technical debt, code quality issues,
and architectural violations using ChatVertexAI.
Automatically publishes findings as GitHub issues.
"""

import os
import logging
from typing import List, Dict
import json
from pydantic import BaseModel, Field
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage
from studio.utils.jules_client import JulesGitHubClient, TaskPayload, TaskPriority
from studio.config import get_settings

logger = logging.getLogger("studio.agents.codebase_analyzer")

class FoundIssue(BaseModel):
    title: str = Field(..., description="Actionable title for the issue")
    description: str = Field(..., description="Detailed description of the problem and potential fix")
    priority: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")
    file_path: str = Field(..., description="Path to the file where the issue was found")

class CodebaseAnalysis(BaseModel):
    issues: List[FoundIssue]

class CodebaseAnalyzerAgent:
    def __init__(self, model_name: str = None):
        settings = get_settings()
        self.model_name = model_name or settings.thinking_model
        self.llm = ChatVertexAI(
            model_name=self.model_name,
            temperature=0.2,
            location="global"
        )
        self.client = JulesGitHubClient(
            github_token=settings.github_token,
            repo_name=settings.github_repository,
            jules_username=settings.jules_username
        )

    async def scan_and_report(self, directory: str = ".") -> List[str]:
        """
        Scans the codebase and creates GitHub issues for found problems.
        Returns a list of created issue numbers.
        """
        logger.info(f"Starting codebase scan in {directory}...")

        # 1. Gather file contents (Limited for context window safety)
        codebase_context = []
        for root, dirs, files in os.walk(directory):
            # Skip hidden dirs and common artifacts
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', 'dist', 'build')]

            for file in files:
                if file.endswith(('.py', '.md', '.txt', '.yml', '.yaml', '.json')):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read()
                            # Minimal truncation per file to fit more files
                            codebase_context.append(f"FILE: {path}\nCONTENT:\n{content[:2000]}")
                    except Exception as e:
                        logger.warning(f"Failed to read {path}: {e}")

        full_context = "\n\n".join(codebase_context)
        # Limit total context to approx 100k tokens (rough char estimate)
        if len(full_context) > 400000:
            full_context = full_context[:400000] + "... [TRUNCATED]"

        # 2. Analyze with LLM
        prompt = f"""
        You are a Senior Security and Quality Engineer.
        Review the following codebase context and identify technical debt, bugs, or architectural violations.
        Focus on SOLID principles and Security.

        CODEBASE CONTEXT:
        {full_context}

        INSTRUCTIONS:
        Return a JSON object containing a list of 'issues'.
        Each issue must have: 'title', 'description', 'priority', 'file_path'.

        Output raw JSON only.
        """

        logger.info("Analyzing codebase with LLM...")
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])

        try:
            # Robust parsing (handling potential markdown)
            raw_content = response.content
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.split("```")[1].split("```")[0].strip()

            data = json.loads(raw_content)
            analysis = CodebaseAnalysis.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to parse analysis: {e}. Raw response: {response.content}")
            return []

        # 3. Create Issues
        created_issues = []
        for issue in analysis.issues:
            logger.info(f"Creating issue: {issue.title}")
            try:
                # We use a generic issue creation if available, or dispatch_task
                # JulesGitHubClient.dispatch_task creates a Task Issue.
                # For now we'll use a new create_issue method we'll add to the client.
                if hasattr(self.client, "create_issue"):
                    issue_num = self.client.create_issue(
                        title=issue.title,
                        body=f"{issue.description}\n\n**File:** {issue.file_path}\n**Priority:** {issue.priority}",
                        labels=["technical-debt", f"priority:{issue.priority.lower()}"]
                    )
                else:
                    # Fallback to dispatch_task as it also creates an issue
                    payload = TaskPayload(
                        task_id=f"DEBT-{issue.file_path.replace('/', '-')}",
                        intent=f"{issue.title}: {issue.description}",
                        context_files={issue.file_path: "Source of issue"},
                        priority=TaskPriority(issue.priority.upper()) if issue.priority.upper() in TaskPriority.__members__ else TaskPriority.MEDIUM
                    )
                    issue_num = self.client.dispatch_task(payload)

                created_issues.append(str(issue_num))
            except Exception as e:
                logger.error(f"Failed to create issue {issue.title}: {e}")

        return created_issues
