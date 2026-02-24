"""
studio/utils/jules_client.py
----------------------------
The "Hand" Interface for the AI Agent Studio.
Defines the standard protocol for the Studio to control an AI Employee (Google Jules).

Key Features:
1. Protocol Definition: Abstract Interface for any AI Employee.
2. Concrete Implementation: GitHub API wrapper for Google Jules.
3. Constraint Injection: Automatically formats tasks to enforce studio rules.

Dependencies:
- PyGithub (pip install PyGithub)
- pydantic
"""

import logging
from typing import Protocol, List, Dict, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, SecretStr

try:
    from github import Github, Repository, Issue, PullRequest
    from github.GithubException import GithubException
except ImportError:
    # Fail gracefully if dependency is missing (Scaffolding mode)
    Github = None

logger = logging.getLogger("studio.utils.jules_client")

# --- SECTION 1: Data Models ( The Nerve Signals ) ---

class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class TaskPayload(BaseModel):
    """
    The strict instruction set sent to the Hand.
    """
    task_id: str = Field(..., description="Internal tracking ID (e.g., TKT-101)")
    intent: str = Field(..., description="What needs to be done (User Story)")
    context_files: Dict[str, str] = Field(default_factory=dict, description="File paths and brief context/snippets")
    relevant_logs: Optional[str] = Field(None, description="The 'Event Horizon' logs")
    constraints: List[str] = Field(default_factory=list, description="Constitutional rules (e.g., TDD)")
    priority: TaskPriority = TaskPriority.MEDIUM

class WorkStatus(BaseModel):
    """
    The sensory feedback from the Hand.
    """
    tracking_id: str
    status: Literal["QUEUED", "WORKING", "REVIEW_READY", "COMPLETED", "BLOCKED"]
    linked_pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    last_commit_hash: Optional[str] = None
    diff_stat: str = "+0/-0"
    raw_diff: Optional[str] = None # For Entropy Calculation

# --- SECTION 2: The Interface Protocol ( Dependency Inversion ) ---

class AIEmployeeClient(Protocol):
    """
    The Abstract Base Class for any AI Coder.
    The Engineer Subgraph depends on THIS, not on 'Jules' specifically.
    """

    def dispatch_task(self, payload: TaskPayload) -> str:
        """
        Assignable Task.
        Returns: External Tracking ID (e.g., GitHub Issue Number).
        """
        ...

    def get_status(self, external_id: str) -> WorkStatus:
        """
        Check if the 'Hand' is done moving.
        """
        ...

    def post_feedback(self, external_id: str, feedback: str, is_error: bool = False) -> bool:
        """
        Slap the Hand (Correction) or Guide it.
        """
        ...

# --- SECTION 3: Concrete Implementation ( Google Jules ) ---

class JulesGitHubClient:
    """
    The Concrete Muscle that talks to Google Jules via GitHub Issues/PRs.
    """

    def __init__(self, github_token: SecretStr, repo_name: str, jules_username: str = "google-jules"):
        if not Github:
            raise ImportError("PyGithub is required. Run `pip install PyGithub`.")

        self.gh = Github(github_token.get_secret_value())
        self.repo_name = repo_name
        self.jules_username = jules_username
        self._repo_cache: Optional[Repository.Repository] = None

    @property
    def repo(self) -> Repository.Repository:
        """Lazy load the repo object."""
        if not self._repo_cache:
            try:
                self._repo_cache = self.gh.get_repo(self.repo_name)
            except GithubException as e:
                logger.error(f"Failed to access repo {self.repo_name}: {e}")
                raise
        return self._repo_cache

    def dispatch_task(self, payload: TaskPayload) -> str:
        """
        Converts the internal Studio Task into a GitHub Issue formatted for Jules.
        """
        logger.info(f"Dispatching Task {payload.task_id} to Jules...")

        # 1. Construct the Prompt (The Body)
        # We use strict formatting to ensure Jules pays attention to constraints.
        body = self._construct_issue_body(payload)

        # 2. Create the Issue
        try:
            issue = self.repo.create_issue(
                title=f"[Studio Task] {payload.intent} ({payload.task_id})",
                body=body,
                labels=["ai-studio", f"priority:{payload.priority.value.lower()}", "jules"]
            )
            logger.info(f"Task dispatched. Issue #{issue.number} created.")
            return str(issue.number)

        except GithubException as e:
            logger.error(f"Failed to create issue for task {payload.task_id}: {e}")
            raise

    def get_status(self, external_id: str) -> WorkStatus:
        """
        Polls the Issue to see if Jules has opened a PR.
        """
        issue_number = int(external_id)
        try:
            # 1. Get the Issue
            issue = self.repo.get_issue(issue_number)

            # 2. Check for Linked PRs
            # GitHub usually links PRs in the timeline or via specific events.
            # A robust way is to search for PRs referencing this issue.
            pr = self._find_linked_pr(issue)

            if not pr:
                # Still working or queued
                return WorkStatus(
                    tracking_id=external_id,
                    status="WORKING" if issue.state == "open" else "BLOCKED"
                )

            # 3. If PR exists, get its details
            # We assume if a PR is open, it's ready for review (by us/Orchestrator)
            status_map = {
                "open": "REVIEW_READY",
                "closed": "COMPLETED", # Merged or closed
            }

            # Fetch the diff for Entropy Calculation
            # Note: For massive diffs, we might need to truncate or fetch file-by-file
            diff_files = list(pr.get_files())

            diff_parts = []
            for f in diff_files:
                if not f.patch:
                    continue

                # Fix malformed patches from GitHub (missing leading spaces on context lines)
                fixed_patch = []
                for line in f.patch.splitlines():
                    if line.startswith(('+', '-', '@@', '\\', ' ')):
                        fixed_patch.append(line)
                    elif not line:
                        fixed_patch.append(' ')
                    else:
                        fixed_patch.append(' ' + line)

                patch_content = "\n".join(fixed_patch) + "\n"
                diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{patch_content}")

            diff_text = "".join(diff_parts)

            return WorkStatus(
                tracking_id=external_id,
                status=status_map.get(pr.state, "WORKING"),
                linked_pr_number=pr.number,
                pr_url=pr.html_url,
                last_commit_hash=pr.head.sha,
                diff_stat=f"+{pr.additions}/-{pr.deletions}",
                raw_diff=diff_text
            )

        except GithubException as e:
            logger.error(f"Failed to get status for issue #{issue_number}: {e}")
            # Return a 'Blocked' status rather than crashing
            return WorkStatus(tracking_id=external_id, status="BLOCKED")

    def post_feedback(self, external_id: str, feedback: str, is_error: bool = False) -> bool:
        """
        Posts a comment on the PR (if available) or falls back to the Issue.
        Explicitly tags Jules for visibility.
        """
        try:
            issue_number = int(external_id)
            issue = self.repo.get_issue(issue_number)

            # 1. Detect if a linked PR exists
            pr = self._find_linked_pr(issue)

            # 2. Construct comment body with explicit tagging
            # Use a newline after the tag for better Markdown rendering
            prefix = "### ❌ QA Verification Failed" if is_error else "### ℹ️ Studio Guidance"
            comment_body = f"@{self.jules_username}\n{prefix}\n\n{feedback}"

            # 3. Post the comment
            if pr:
                # PullRequest objects use create_issue_comment for top-level comments
                pr.create_issue_comment(comment_body)
                location = f"PR #{pr.number}"
            else:
                issue.create_comment(comment_body)
                location = f"Issue #{issue_number}"

            logger.info(f"Posted feedback to {location}")
            return True

        except GithubException as e:
            logger.error(f"Failed to post feedback to #{external_id}: {e}")
            return False

    def review_pr(self, pr_number: int, event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"], body: str = "") -> bool:
        """
        Submits a formal GitHub Pull Request review.

        Args:
            pr_number: The PR number to review.
            event: One of "APPROVE", "REQUEST_CHANGES", or "COMMENT".
            body: The review body / summary text.

        Returns:
            True on success, False on failure.
        """
        try:
            pr = self.repo.get_pull(pr_number)
            pr.create_review(body=body, event=event)
            logger.info(f"Submitted PR review ({event}) on PR #{pr_number}")
            return True
        except GithubException as e:
            logger.error(f"GitHub error while reviewing PR #{pr_number}: {e}")
            return False

    def merge_pr(self, pr_number: int) -> bool:
        """
        Merges the specified Pull Request.
        """
        try:
            pr = self.repo.get_pull(pr_number)
            if pr.merged:
                logger.info(f"PR #{pr_number} is already merged.")
                return True

            status = pr.merge(merge_method="merge")
            if status.merged:
                logger.info(f"Successfully merged PR #{pr_number}")
                return True
            else:
                logger.error(f"Failed to merge PR #{pr_number}: {status.message}")
                return False

        except GithubException as e:
            logger.error(f"GitHub error while merging PR #{pr_number}: {e}")
            return False

    def get_open_prs(self, label: Optional[str] = None, author: Optional[str] = None) -> List[PullRequest.PullRequest]:
        """
        Lists all open Pull Requests, optionally filtered by label and author.
        """
        try:
            pulls = self.repo.get_pulls(state='open', sort='created', direction='desc')
            filtered_pulls = []

            for pr in pulls:
                # Filter by author
                if author and pr.user.login != author:
                    continue

                # Filter by label
                if label:
                    labels = [l.name for l in pr.labels]
                    if label not in labels:
                        continue

                filtered_pulls.append(pr)

            return filtered_pulls
        except GithubException as e:
            logger.error(f"Failed to list open PRs: {e}")
            return []

    def get_file_content(self, path: str, ref: Optional[str] = None) -> str:
        """
        Fetches the full content of a file at a specific ref/branch.
        """
        try:
            content = self.repo.get_contents(path, ref=ref)
            return content.decoded_content.decode('utf-8')
        except GithubException as e:
            logger.error(f"Failed to get content for {path} at {ref}: {e}")
            raise

    # --- Internal Helpers ---

    def _construct_issue_body(self, payload: TaskPayload) -> str:
        """
        Formats the prompt for the AI Employee.
        """
        # Markdown template optimized for Code Agents
        return f"""
@{self.jules_username} **Action Required**

### 🎯 Intent
{payload.intent}

### 📂 Context
* **Task ID:** `{payload.task_id}`
* **Focus Files:**
{self._format_file_list(payload.context_files)}

### 📜 Constraints (MUST FOLLOW)
{self._format_constraints(payload.constraints)}

### 🔍 Relevant Logs / Evidence
```text
{payload.relevant_logs or "No logs provided."}

```

---

*Generated by AI Agent Studio (Orchestrator)*
"""

    def _format_file_list(self, files: Dict[str, str]) -> str:
        if not files: return "_No specific files identified._"
        return "\n".join([f"- `{path}`: {desc}" for path, desc in files.items()])

    def _format_constraints(self, constraints: List[str]) -> str:
        if not constraints: return "_No specific constraints._"
        return "\n".join([f"- [ ] {c}" for c in constraints])

    def _find_linked_pr(self, issue: Issue.Issue) -> Optional[PullRequest.PullRequest]:
        """
        Heuristic to find a PR linked to the issue.
        Jules typically auto-links them.
        """
        # Strategy 1: Check Timeline for 'Cross-referenced' events
        timeline = issue.get_timeline()
        for event in timeline:
            if event.event == "cross-referenced" and event.source and event.source.issue:
                # If the source is a PR (Pull Requests are Issues in GitHub API)
                if event.source.issue.pull_request:
                    return event.source.issue.as_pull_request()
        return None
