import unittest
import ast
import sys
import os
import importlib
from unittest.mock import MagicMock, patch

# Ensure studio can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestOptimizer(unittest.TestCase):

    def setUp(self):
        # Create a patcher for sys.modules
        self.modules_patcher = patch.dict(sys.modules, {
            "dotenv": MagicMock(),
            "langchain_google_vertexai": MagicMock(),
            "langchain_core": MagicMock(),
            "langchain_core.prompts": MagicMock(),
            "langchain_core.output_parsers": MagicMock(),
        })
        self.modules_patcher.start()

        # Import or reload the module to use the mocked dependencies
        # We need to do this because the module imports these dependencies at top level
        if 'studio.optimizer' in sys.modules:
            import studio.optimizer
            importlib.reload(studio.optimizer)
        else:
            import studio.optimizer

        self.optimizer_module = studio.optimizer

    def tearDown(self):
        self.modules_patcher.stop()
        # Clean up the module from sys.modules so it doesn't persist with mocks
        # This ensures subsequent tests (if any) get a fresh import with real dependencies
        if 'studio.optimizer' in sys.modules:
            del sys.modules['studio.optimizer']

    def test_find_top_level_system_prompt(self):
        code = """
SYSTEM_PROMPT = "This is a system prompt."
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNotNone(node)
        self.assertIsInstance(node, ast.Assign)
        self.assertEqual(node.targets[0].id, "SYSTEM_PROMPT")

    def test_find_top_level_prompt_template(self):
        code = """
PROMPT_TEMPLATE = "This is a prompt template."
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNotNone(node)
        self.assertIsInstance(node, ast.Assign)
        self.assertEqual(node.targets[0].id, "PROMPT_TEMPLATE")

    def test_find_multiline_string(self):
        code = """
SYSTEM_PROMPT = \"\"\"
This is a multiline
system prompt.
\"\"\"
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNotNone(node)
        self.assertIsInstance(node, ast.Assign)
        # Check value if possible, but mainly checking node type
        if hasattr(node.value, 'value'): # Python 3.8+
             val = node.value.value
        elif hasattr(node.value, 's'): # Python < 3.8
             val = node.value.s
        else:
             val = None
        self.assertIn("multiline", val)

    def test_find_f_string(self):
        code = """
var = "variable"
SYSTEM_PROMPT = f"This is an f-string with {var}."
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNotNone(node)
        self.assertIsInstance(node, ast.Assign)
        self.assertIsInstance(node.value, ast.JoinedStr)

    def test_prefers_top_level_over_nested(self):
        code = """
def func():
    SYSTEM_PROMPT = "nested"

SYSTEM_PROMPT = "top-level"
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNotNone(node)

        # Extract value to confirm
        if isinstance(node.value, ast.Constant):
            val = node.value.value
        elif isinstance(node.value, ast.Str):
            val = node.value.s
        else:
            val = None

        self.assertEqual(val, "top-level")

    def test_returns_none_if_not_found(self):
        code = """
OTHER_VAR = "something else"
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNone(node)

    def test_returns_none_on_syntax_error(self):
        code = """
This is not valid python code
"""
        node = self.optimizer_module.find_system_prompt_node(code)
        self.assertIsNone(node)

if __name__ == '__main__':
    unittest.main()
