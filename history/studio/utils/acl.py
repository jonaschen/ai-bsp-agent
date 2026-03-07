import os
from pathlib import Path

def verify_write_permission(target_path: str):
    """
    Enforces the Containment Protocol (AGENTS.md Section 4).
    Only allows writes to product/prompts/ directory.
    """
    # Convert to absolute path to prevent traversal attacks
    abs_target = Path(target_path).resolve()
    allowed_base = Path("product/prompts").resolve()

    # Check if allowed_base is a parent of abs_target
    # Use relative_to to safely check if target is within base
    try:
        abs_target.relative_to(allowed_base)
    except ValueError:
        # relative_to raises ValueError if it's not a subpath
        raise PermissionError(f"ACL Violation: Optimizer cannot write to {target_path}. Access restricted to {allowed_base}")

def is_path_allowed(target_path: str) -> bool:
    """Check if path is allowed without raising exception."""
    try:
        verify_write_permission(target_path)
        return True
    except PermissionError:
        return False
