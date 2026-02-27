import subprocess
import logging

logger = logging.getLogger("studio.utils.git_utils")

def checkout_pr_branch(branch_name: str):
    """
    Safely stashes local changes, fetches the latest remote branches,
    and checks out the target branch.
    """
    logger.info(f"Checking out PR branch: {branch_name}")

    # 1. Stash any local changes (ignore failure if nothing to stash)
    try:
        subprocess.run(["git", "stash"], check=False)
    except Exception as e:
        logger.warning(f"Git stash failed (likely nothing to stash): {e}")

    # 2. Fetch from origin
    try:
        subprocess.run(["git", "fetch", "origin"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git fetch origin failed: {e}")
        raise

    # 3. Checkout the target branch
    try:
        subprocess.run(["git", "checkout", branch_name], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git checkout {branch_name} failed: {e}")
        raise

def sync_main_branch():
    """
    Synchronizes the local main branch with the remote origin.
    Executes: git checkout main && git pull origin main
    """
    logger.info("Synchronizing local workspace with main branch.")

    # 1. Checkout main
    try:
        subprocess.run(["git", "checkout", "main"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git checkout main failed: {e}")
        raise

    # 2. Pull from origin main (with rebase to avoid merge conflicts in automated flow)
    try:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git pull origin main failed: {e}")
        raise
