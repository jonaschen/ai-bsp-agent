import os
import logging
import json
from typing import List, Optional, Dict
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage
from studio.utils.jules_client import JulesGitHubClient
from studio.config import get_settings

logger = logging.getLogger("studio.agents.codebase_analyzer")

SYSTEM_PROMPT = """
You are a Senior Software Quality Engineer and Architect.
Your task is to analyze the provided source code for:
1. **Code Quality Issues**: Redundancy, complexity, poor naming, lack of comments.
2. **Architectural Violations**: Violations of SOLID, patterns in rules.md, or prohibited imports.
3. **Tech Debt**: TODOs, FIXMEs, deprecated patterns.
4. **Security**: Hardcoded secrets, unsafe practices.

=== PROJECT RULES (studio/rules.md) ===
{rules_content}

=== SOURCE CODE ({file_path}) ===
{file_content}

=== INSTRUCTIONS ===
Return a JSON list of objects. Each object should have:
{{
    "type": "TECH_DEBT" | "VIOLATION" | "QUALITY" | "SECURITY",
    "file": "{file_path}",
    "description": "Clear and actionable description of the issue.",
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
}}

If no issues are found, return an empty list [].
Output raw JSON only. Do not use Markdown formatting.
"""

class CodebaseAnalyzerAgent:
    def __init__(self, client: Optional[JulesGitHubClient] = None):
        settings = get_settings()
        self.client = client or JulesGitHubClient(
            github_token=settings.github_token,
            repo_name=settings.github_repository,
            jules_username=settings.jules_username
        )

        project_id = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"

        if project_id:
            self.llm = ChatVertexAI(
                model_name="gemini-1.5-pro",
                project=project_id,
                location=location,
                temperature=0.1,
                max_output_tokens=8192
            )
        else:
            logger.warning("PROJECT_ID not set. LLM capabilities will be disabled.")
            self.llm = None

    async def run_scan(self, directory: str = "."):
        """
        Scans the repository and creates GitHub issues for found problems.
        """
        rules_content = self._load_rules()
        all_issues = []

        for root, dirs, files in os.walk(directory):
            # Prune directories
            dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "node_modules", "dist", "build", "venv", ".pyenv"]]

            for file in files:
                if not self._is_relevant_file(file):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    if not content.strip():
                        continue

                    # Filter out very large files to avoid token limits
                    if len(content) > 100000:
                        logger.warning(f"File {file_path} is too large, skipping.")
                        continue

                    issues = await self._analyze_file(file_path, content, rules_content)
                    all_issues.extend(issues)
                except Exception as e:
                    logger.error(f"Error analyzing {file_path}: {e}")

        # Publish issues
        for issue in all_issues:
            await self._publish_issue(issue)

    def _load_rules(self) -> str:
        rules_path = os.path.join(os.getcwd(), 'studio', 'rules.md')
        if os.path.exists(rules_path):
            with open(rules_path, 'r') as f:
                return f.read()
        return "No specific rules found."

    def _is_relevant_file(self, filename: str) -> bool:
        extensions = ['.py', '.md', '.yml', '.yaml', '.json', '.c', '.h', '.cpp', '.ini', '.toml']
        return any(filename.endswith(ext) for ext in extensions)

    async def _analyze_file(self, file_path: str, content: str, rules_content: str) -> List[Dict]:
        if not self.llm:
            return []

        prompt = SYSTEM_PROMPT.format(
            rules_content=rules_content,
            file_path=file_path,
            file_content=content
        )

        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            raw_content = response.content

            # Simple JSON cleaning
            cleaned = raw_content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            elif cleaned.startswith("```"):
                 cleaned = cleaned[3:]
                 if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]

            return json.loads(cleaned.strip())
        except Exception as e:
            logger.error(f"LLM analysis failed for {file_path}: {e}")
            return []

    async def _publish_issue(self, issue: Dict):
        title = f"[{issue['type']}] {issue['severity']}: Issue in {issue['file']}"
        body = f"**Description**: {issue['description']}\n\n**File**: {issue['file']}\n**Severity**: {issue['severity']}\n**Type**: {issue['type']}"

        try:
            # Check for existing open issues with same title to avoid duplicates
            # (Basic check, could be improved)
            # For MVP, we'll just create it.
            if hasattr(self.client, 'create_issue'):
                self.client.create_issue(title=title, body=body, labels=[issue['type'].lower(), "automated-scan"])
            else:
                # Fallback if create_issue doesn't exist yet
                logger.warning("JulesGitHubClient.create_issue not implemented. Falling back to logging.")
                logger.info(f"WOULD CREATE ISSUE: {title}\n{body}")

            logger.info(f"Processed issue: {title}")
        except Exception as e:
            logger.error(f"Failed to create issue for {issue['file']}: {e}")
