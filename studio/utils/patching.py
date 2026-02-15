"""
studio/utils/patching.py
------------------------
Utilities for applying virtual patches (diffs) to files.
Used by the QA Agent to prepare the sandbox environment.
"""

import os
import tempfile
import subprocess
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("studio.utils.patching")

def apply_virtual_patch(files: Dict[str, str], diff_content: str) -> Dict[str, str]:
    """
    Applies a unified diff to a set of files in memory.

    Args:
        files: A dictionary of {filepath: content}.
        diff_content: The unified diff string.

    Returns:
        A dictionary of {filepath: patched_content}.
    """
    if not diff_content.strip():
        return files.copy()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Write original files to temp dir
        for filepath, content in files.items():
            # Ensure directory structure exists
            full_path = os.path.join(tmpdir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        # 2. Write diff to a file
        patch_path = os.path.join(tmpdir, "changes.patch")
        with open(patch_path, "w", encoding="utf-8") as f:
            f.write(diff_content)

        # 3. Apply patch
        # We try -p1 first (standard for git diffs a/file b/file)
        cmd = ["patch", "-p1", "--input", "changes.patch"]

        try:
            result = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=False # We handle errors manually
            )

            if result.returncode != 0:
                logger.warning(f"Patch failed with -p1: {result.stderr or result.stdout}")
                # Fallback? Maybe -p0?
                cmd[1] = "-p0"
                result = subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                     logger.error(f"Patch failed with -p0 as well: {result.stderr or result.stdout}")
                     raise RuntimeError(f"Failed to apply patch: {result.stderr or result.stdout}")

            logger.info("Patch applied successfully.")

        except FileNotFoundError:
             raise RuntimeError("patch command not found. Please install patch.")

        # 4. Read back all files
        patched_files = {}
        for root, _, filenames in os.walk(tmpdir):
            for filename in filenames:
                if filename == "changes.patch":
                    continue

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, tmpdir)

                with open(abs_path, "r", encoding="utf-8") as f:
                    patched_files[rel_path] = f.read()

        return patched_files
