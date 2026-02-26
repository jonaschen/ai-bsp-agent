import pytest
import os
from studio.utils.patching import apply_virtual_patch, extract_affected_files

def test_apply_patch_delete_file_fails_without_E():
    files = {"product/schemas/__init__.py": "content\n"}
    # A complete deletion hunk
    diff = """--- a/product/schemas/__init__.py
+++ /dev/null
@@ -1,1 +0,0 @@
-content
"""
    patched = apply_virtual_patch(files, diff)
    # Without -E, patch usually leaves the file there empty.
    # If it's there, then it failed our 'virtual' deletion.
    assert "product/schemas/__init__.py" not in patched, "File should have been deleted"

if __name__ == "__main__":
    try:
        test_apply_patch_delete_file_fails_without_E()
        print("Test PASSED (File WAS deleted)")
    except AssertionError as e:
        print(f"Test FAILED: {e}")
    except Exception as e:
        print(f"Error: {e}")
