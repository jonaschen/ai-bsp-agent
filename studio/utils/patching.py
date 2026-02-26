"""
studio/utils/patching.py
------------------------
Utilities for applying virtual patches (diffs) to files.
Used by the QA Agent to prepare the sandbox environment.
"""

import os
import io
import tempfile
import subprocess
import logging
from typing import Dict, List, Optional
from unidiff import PatchSet

logger = logging.getLogger("studio.utils.patching")

def extract_affected_files(diff_content: str) -> List[str]:
    """
    Extracts all unique file paths mentioned in a unified diff.
    Supports both standard and git-style diffs.
    """
    affected_files = set()
    try:
        # unidiff is robust for standard unified diffs
        patch_set = PatchSet(io.StringIO(diff_content))
        for patched_file in patch_set:
            # .path automatically handles a/ and b/ prefixes
            path = patched_file.path
            if path and path != "/dev/null":
                affected_files.add(path)
    except Exception as e:
        logger.warning(f"unidiff failed to extract affected files, falling back to manual regex: {e}")
        for line in diff_content.splitlines():
            # Unified diff headers: --- a/path/to/file or +++ b/path/to/file
            if line.startswith("--- ") or line.startswith("+++ "):
                # Extract path, removing '--- ' or '+++ '
                path = line[4:].split('\t')[0].strip()

                # Skip special markers
                if path in ["/dev/null", ""]:
                    continue

                # Strip git-style prefixes (a/ or b/)
                if (path.startswith("a/") or path.startswith("b/")) and len(path) > 2:
                    path = path[2:]

                affected_files.add(path)

    return sorted(list(affected_files))

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

    # 1. Initialize any files mentioned in the diff that aren't in our dictionary
    # This allows the 'patch' command to create new files correctly.
    affected_files = extract_affected_files(diff_content)
    patched_files_workset = files.copy()
    for path in affected_files:
        if path not in patched_files_workset:
            logger.info(f"Initializing new file for patching: {path}")
            patched_files_workset[path] = ""

    # 2. Normalize the diff
    try:
        # Try using unidiff for clean normalization
        patch_set = PatchSet(io.StringIO(diff_content))
        new_diff_parts = []
        for patched_file in patch_set:
            source = patched_file.source_file
            target = patched_file.target_file
            # Strip prefixes for -p0 compatibility
            if source.startswith("a/") and source != "a/": source = source[2:]
            if target.startswith("b/") and target != "b/": target = target[2:]

            new_diff_parts.append(f"--- {source}\n")
            new_diff_parts.append(f"+++ {target}\n")
            for hunk in patched_file:
                hunk_str = str(hunk)
                if not hunk_str.endswith("\n"):
                    hunk_str += "\n"
                new_diff_parts.append(hunk_str)
        diff_content = "".join(new_diff_parts)
        logger.info("Normalized diff using unidiff.")
    except Exception as e:
        logger.warning(f"unidiff failed to normalize diff, using manual fallback: {e}")
        # Manual fallback to fix common LLM issues
        fixed_lines = []
        git_headers = ("diff --git ", "index ", "new file mode ", "deleted file mode ",
                       "old mode ", "new mode ", "similarity index ", "rename from ",
                       "rename to ", "copy from ", "copy to ")

        for line in diff_content.splitlines():
            if line.startswith("--- "):
                # Strip a/ prefix for -p0 compatibility
                path_part = line[4:].split('\t')[0].strip()
                if (path_part.startswith("a/") or path_part.startswith("b/")) and len(path_part) > 2:
                    line = "--- " + path_part[2:]
                fixed_lines.append(line)
            elif line.startswith("+++ "):
                # Strip b/ prefix for -p0 compatibility
                path_part = line[4:].split('\t')[0].strip()
                if (path_part.startswith("a/") or path_part.startswith("b/")) and len(path_part) > 2:
                    line = "+++ " + path_part[2:]
                fixed_lines.append(line)
            elif line.startswith(('+', '-', '@@', '\\', ' ')) or line.startswith(git_headers):
                fixed_lines.append(line)
            elif not line:
                fixed_lines.append(' ')
            else:
                # Likely a context line that lost its leading space
                fixed_lines.append(' ' + line)
        diff_content = "\n".join(fixed_lines) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        # 3. Write original (and initialized empty) files to temp dir
        for filepath, content in patched_files_workset.items():
            full_path = os.path.join(tmpdir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        # 4. Write diff to a file
        patch_path = os.path.join(tmpdir, "changes.patch")
        with open(patch_path, "w", encoding="utf-8") as f:
            f.write(diff_content)

        # 5. Apply patch
        # Since we stripped a/ and b/ prefixes, we use -p0 primarily.
        # We use -E to ensure empty files are removed (e.g. during consolidation).
        cmd = ["patch", "-p0", "-E", "--input", "changes.patch"]

        try:
            result = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=False # We handle errors manually
            )

            if result.returncode != 0:
                logger.warning(f"Patch failed with -p0: {result.stderr or result.stdout}")
                # Fallback to -p1 just in case
                # Keep -E in fallback
                cmd = ["patch", "-p1", "-E", "--input", "changes.patch"]
                result = subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                     logger.error(f"Patch failed with -p1 as well: {result.stderr or result.stdout}")
                     raise RuntimeError(f"Failed to apply patch: {result.stderr or result.stdout}")

            logger.info("Patch applied successfully.")

        except FileNotFoundError:
             raise RuntimeError("patch command not found. Please install patch.")

        # 6. Read back all files
        patched_files_result = {}
        for root, _, filenames in os.walk(tmpdir):
            for filename in filenames:
                if filename == "changes.patch":
                    continue

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, tmpdir)

                with open(abs_path, "r", encoding="utf-8") as f:
                    patched_files_result[rel_path] = f.read()

        return patched_files_result
