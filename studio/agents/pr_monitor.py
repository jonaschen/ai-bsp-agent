import logging
from typing import List, Optional, Dict
from studio.utils.jules_client import JulesGitHubClient
from studio.review_agent import ReviewAgent
from studio.agents.architect import ArchitectAgent
from studio.utils.sandbox import DockerSandbox
from studio.utils.patching import apply_virtual_patch
from studio.config import get_settings
from github.PullRequest import PullRequest

logger = logging.getLogger("studio.agents.pr_monitor")

class PRMonitorAgent:
    def __init__(self, client: Optional[JulesGitHubClient] = None):
        settings = get_settings()
        self.client = client or JulesGitHubClient(
            github_token=settings.github_token,
            repo_name=settings.github_repository,
            jules_username=settings.jules_username
        )
        self.review_agent = ReviewAgent()
        self.architect_agent = ArchitectAgent()
        self.monitor_label = settings.monitor_label
        self.monitor_author = settings.monitor_author

    async def list_eligible_prs(self) -> List[PullRequest]:
        """
        Fetches open PRs and filters them based on settings.
        """
        return self.client.get_open_prs(label=self.monitor_label, author=self.monitor_author)

    async def _fetch_and_patch_files(self, pr: PullRequest) -> Dict[str, str]:
        """
        Identifies affected files and applies PR diff to their base content.
        """
        diff_files = list(pr.get_files())
        patched_files = {}

        # We need a unified diff to use apply_virtual_patch
        # In a real scenario, we'd use the diff from the PR
        # For simplicity, we'll fetch base content and apply the patch from PullRequestFile

        files_to_patch = {}
        full_diff = ""

        for f in diff_files:
            if not f.patch:
                continue

            # Construct a unified diff part for this file
            file_diff = f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch}\n"
            full_diff += file_diff

            try:
                # Fetch original content from base branch
                base_content = self.client.get_file_content(f.filename, ref=pr.base.sha)
                files_to_patch[f.filename] = base_content
            except Exception as e:
                logger.warning(f"Could not fetch base content for {f.filename}: {e}. Assuming new file.")
                files_to_patch[f.filename] = ""

        if not full_diff:
            return {}

        return apply_virtual_patch(files_to_patch, full_diff)

    async def _run_qa(self, patched_files: Dict[str, str]) -> bool:
        """
        Executes tests in the DockerSandbox.
        """
        if not patched_files:
            return True # Nothing to test

        sandbox = None
        try:
            sandbox = DockerSandbox()
            if not sandbox.setup_workspace(patched_files):
                logger.error("Failed to setup sandbox workspace")
                return False

            # Identify tests (heuristic)
            test_files = [f for f in patched_files.keys() if "test" in f and f.endswith(".py")]
            target = " ".join(test_files) if test_files else "tests/"

            # Run dependencies if requirements.txt exists
            if "requirements.txt" in patched_files:
                sandbox.run_command("pip install -r requirements.txt")

            sandbox.install_dependencies(["pytest", "mock"])

            test_result = sandbox.run_pytest(target)
            return test_result.passed
        except Exception as e:
            logger.error(f"QA Verification failed with error: {e}")
            return False
        finally:
            if sandbox:
                sandbox.teardown()

    async def _run_reviews(self, patched_files: Dict[str, str], pr: PullRequest) -> (bool, str):
        """
        Performs semantic and structural reviews.
        Returns (success, feedback).
        """
        # 1. Semantic Review (ReviewAgent)
        # Fetch full diff for ReviewAgent
        # Note: PyGithub doesn't have a direct get_diff() on PullRequest object that returns a string easily
        # We'll use the one we constructed or fetch it from GitHub if possible.
        # For now, let's use the Constructed one from _fetch_and_patch_files or just a dummy if needed.
        # Actually, let's fetch it via raw URL or similar if needed, but for MVP we'll use a summary.

        # Heuristic: Fetch diff via repo.get_pull(pr.number).get_files() and reconstruct
        diff_parts = []
        for f in pr.get_files():
            if f.patch:
                diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch}\n")
        full_diff = "".join(diff_parts)

        review_summary = self.review_agent.analyze(full_diff)
        if review_summary.status == "FAILED":
            return False, f"Semantic Review Failed: {review_summary.root_cause}\nSuggested Fix: {review_summary.suggested_fix}"

        # 2. Architectural Review (ArchitectAgent)
        ticket_context = f"PR #{pr.number}: {pr.title}"
        for filepath, content in patched_files.items():
            if not filepath.endswith(".py"):
                continue
            verdict = self.architect_agent.review_code(filepath, content, ticket_context)
            if verdict.status in ["REJECTED", "NEEDS_REFACTOR"]:
                violations = "\n".join([f"- {v.description} (Fix: {v.suggested_fix})" for v in verdict.violations])
                return False, f"Architectural Review Failed in {filepath}:\n{violations}"

        return True, "All reviews passed."

    async def run_once(self):
        """
        Main loop: Find PRs, Review them, and Merge or Feedback.
        """
        eligible_prs = await self.list_eligible_prs()
        logger.info(f"Found {len(eligible_prs)} eligible PRs for monitoring.")

        for pr in eligible_prs:
            logger.info(f"Starting automated review for PR #{pr.number}")

            try:
                # 1. Fetch and Patch
                patched_files = await self._fetch_and_patch_files(pr)

                # 2. QA Check
                qa_passed = await self._run_qa(patched_files)
                if not qa_passed:
                    self.client.review_pr(pr.number, event="REQUEST_CHANGES", body="Automated QA failed. Please check the logs.")
                    continue

                # 3. Semantic & Architectural Reviews
                reviews_passed, feedback = await self._run_reviews(patched_files, pr)
                if not reviews_passed:
                    self.client.review_pr(pr.number, event="REQUEST_CHANGES", body=feedback)
                    continue

                # 4. Success - Approve and Merge
                logger.info(f"PR #{pr.number} passed all checks. Approving and Merging.")
                self.client.review_pr(pr.number, event="APPROVE", body="All automated checks passed (QA, Semantic, Architectural). Merging.")
                self.client.merge_pr(pr.number)

            except Exception as e:
                logger.error(f"Failed to process PR #{pr.number}: {e}", exc_info=True)

async def run_pr_monitor():
    """
    Helper to run the monitor once from the orchestrator.
    """
    agent = PRMonitorAgent()
    await agent.run_once()
