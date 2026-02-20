import pytest
import os
import shutil
import unittest.mock
from unittest.mock import MagicMock
from studio.utils.patching import apply_virtual_patch

def test_apply_patch_success():
    files = {"hello.py": "print('hello')\n"}
    diff = """--- a/hello.py
+++ b/hello.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
    # Check if patch command exists, otherwise skip
    if not shutil.which("patch"):
        pytest.skip("patch command not found")

    result = apply_virtual_patch(files, diff)
    assert result["hello.py"] == "print('world')\n"

def test_apply_patch_empty():
    files = {"hello.py": "print('hello')\n"}
    diff = ""
    result = apply_virtual_patch(files, diff)
    assert result == files

def test_apply_patch_create_file():
    files = {"existing.py": "pass\n"}
    diff = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1 @@
+print('new')
"""
    if not shutil.which("patch"):
        pytest.skip("patch command not found")

    result = apply_virtual_patch(files, diff)
    assert result["existing.py"] == "pass\n"
    assert "new_file.py" in result
    assert result["new_file.py"] == "print('new')\n"

def test_apply_patch_delete_file():
    files = {"to_delete.py": "delete me\n", "keep.py": "keep me\n"}
    diff = """--- a/to_delete.py
+++ /dev/null
@@ -1 +0,0 @@
-delete me
"""
    if not shutil.which("patch"):
        pytest.skip("patch command not found")

    result = apply_virtual_patch(files, diff)
    assert "to_delete.py" not in result
    assert result["keep.py"] == "keep me\n"

def test_apply_patch_subdir():
    files = {"subdir/file.py": "original\n"}
    diff = """--- a/subdir/file.py
+++ b/subdir/file.py
@@ -1 +1 @@
-original
+patched
"""
    if not shutil.which("patch"):
        pytest.skip("patch command not found")

    result = apply_virtual_patch(files, diff)
    assert result["subdir/file.py"] == "patched\n"

def test_apply_patch_failure():
    files = {"bad.py": "content"}
    diff = "some invalid diff"

    # Mock subprocess.run to simulate patch command failure
    with unittest.mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="patch failed")

        with pytest.raises(RuntimeError) as excinfo:
            apply_virtual_patch(files, diff)

        assert "Failed to apply patch" in str(excinfo.value)
        # Should have tried twice (-p1 then -p0)
        assert mock_run.call_count == 2

def test_patch_command_not_found():
    files = {"file.py": "content"}
    diff = "diff"

    with unittest.mock.patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError

        with pytest.raises(RuntimeError) as excinfo:
            apply_virtual_patch(files, diff)

        assert "patch command not found" in str(excinfo.value)

def test_apply_patch_p0_fallback():
    files = {"file.py": "content"}
    diff = "diff"

    with unittest.mock.patch("subprocess.run") as mock_run:
        # First call (-p1) fails, second call (-p0) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="hunk failed"),
            MagicMock(returncode=0)
        ]

        # Since we mock success but don't actually modify files on disk (mocked subprocess),
        # the result will be the original files. This is expected in this mock scenario.
        # We are testing the fallback logic here.
        apply_virtual_patch(files, diff)

        assert mock_run.call_count == 2
        # Check second call arguments
        args, kwargs = mock_run.call_args_list[1]
        cmd = args[0]
        assert "-p0" in cmd
