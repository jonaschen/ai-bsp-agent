import pytest
import os
from studio.utils.patching import apply_virtual_patch, extract_affected_files

def test_extract_affected_files():
    diff = """--- a/product/schemas.py
+++ b/product/schemas.py
@@ -1,1 +1,1 @@
-old
+new
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,1 @@
+content
"""
    files = extract_affected_files(diff)
    assert "product/schemas.py" in files
    assert "new_file.py" in files
    assert len(files) == 2

def test_apply_patch_with_git_prefixes():
    files = {"product/schemas.py": "line1\nline2\nline3\nline4\nline5\n"}
    # Simplified diff
    diff = """--- a/product/schemas.py
+++ b/product/schemas.py
@@ -2,1 +2,1 @@
-line2
+line2-patched
"""
    patched = apply_virtual_patch(files, diff)
    assert "product/schemas.py" in patched
    assert patched["product/schemas.py"] == "line1\nline2-patched\nline3\nline4\nline5\n"

def test_apply_patch_new_file():
    files = {}
    diff = """--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,1 @@
+new content
"""
    patched = apply_virtual_patch(files, diff)
    assert "new_file.py" in patched
    assert patched["new_file.py"] == "new content\n"

def test_apply_patch_new_file_no_dev_null():
    files = {}
    diff = """--- a/brand_new.py
+++ b/brand_new.py
@@ -0,0 +1,1 @@
+brand new content
"""
    # This often happens in generated diffs
    patched = apply_virtual_patch(files, diff)
    assert "brand_new.py" in patched
    assert patched["brand_new.py"] == "brand new content\n"

def test_apply_patch_multiple_files():
    files = {"file1.py": "old1\n"}
    diff = """--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,1 @@
-old1
+new1
--- /dev/null
+++ b/file2.py
@@ -0,0 +1,1 @@
+new2
"""
    patched = apply_virtual_patch(files, diff)
    assert patched["file1.py"] == "new1\n"
    assert patched["file2.py"] == "new2\n"

def test_apply_patch_realistic_git_diff():
    files = {"existing.py": "print('hello')\n"}
    diff = """diff --git a/existing.py b/existing.py
index 1234567..890abcd 100644
--- a/existing.py
+++ b/existing.py
@@ -1,1 +1,1 @@
-print('hello')
+print('world')
diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,1 @@
+new file
"""
    patched = apply_virtual_patch(files, diff)
    assert patched["existing.py"] == "print('world')\n"
    assert "new_file.py" in patched
    assert patched["new_file.py"] == "new file\n"

def test_apply_patch_missing_space_in_context():
    files = {"app.py": "line1\nline2\nline3\n"}
    # The 'line1' and 'line3' are context lines but missing their leading space
    # (they don't start with +, -, @@, \, or space)
    diff = """--- a/app.py
+++ b/app.py
@@ -1,3 +1,3 @@
line1
-line2
+line2-new
line3
"""
    patched = apply_virtual_patch(files, diff)
    assert patched["app.py"] == "line1\nline2-new\nline3\n"
