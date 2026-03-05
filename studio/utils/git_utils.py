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

    # 4. Force synchronization with origin (Hard Reset)
    # This ensures local branch perfectly mirrors origin, avoiding "Checkout Trap"
    try:
        subprocess.run(["git", "reset", "--hard", f"origin/{branch_name}"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git reset --hard origin/{branch_name} failed: {e}")
        raise

    # 5. Clean untracked files
    try:
        subprocess.run(["git", "clean", "-fd"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git clean -fd failed: {e}")
        raise

def sync_main_branch():
    """
    Synchronizes the local main branch with the remote origin.
    Executes: git stash && git checkout main && git fetch origin main && git reset --hard origin/main && git clean -fd
    """
    logger.info("Synchronizing local workspace with main branch.")

    # 0. Stash local changes
    try:
        subprocess.run(["git", "stash"], check=False)
    except Exception as e:
        logger.warning(f"Git stash failed: {e}")

    # 1. Checkout main
    try:
        subprocess.run(["git", "checkout", "main"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git checkout main failed: {e}")
        raise

    # 2. Fetch from origin main
    try:
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git fetch origin main failed: {e}")
        raise

    # 3. Force synchronization with origin/main
    try:
        subprocess.run(["git", "reset", "--hard", "origin/main"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git reset --hard origin/main failed: {e}")
        raise

    # 4. Clean untracked files
    try:
        subprocess.run(["git", "clean", "-fd"], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git clean -fd failed: {e}")
        raise
