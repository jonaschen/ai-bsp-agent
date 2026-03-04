import unittest
from unittest.mock import patch, mock_open
from io import StringIO
import ast

from verify_unused import check_unused_imports

class TestVerifyUnused(unittest.TestCase):
    def test_optional_is_used(self):
        code = '''
from typing import Optional

def func(x: Optional[int]) -> None:
    pass
'''
        with patch('builtins.open', mock_open(read_data=code)):
            with patch('sys.stdout', new=StringIO()) as fake_out:
                check_unused_imports('dummy_path.py')
                self.assertEqual(fake_out.getvalue().strip(), "Optional is USED.")

    def test_optional_is_not_used(self):
        code = '''
from typing import Optional

def func(x: int) -> None:
    pass
'''
        with patch('builtins.open', mock_open(read_data=code)):
            with patch('sys.stdout', new=StringIO()) as fake_out:
                check_unused_imports('dummy_path.py')
                self.assertEqual(fake_out.getvalue().strip(), "Optional is NOT used.")

    def test_optional_used_in_assignment(self):
        code = '''
from typing import Optional

MyOpt = Optional[str]
'''
        with patch('builtins.open', mock_open(read_data=code)):
            with patch('sys.stdout', new=StringIO()) as fake_out:
                check_unused_imports('dummy_path.py')
                self.assertEqual(fake_out.getvalue().strip(), "Optional is USED.")

    def test_syntax_error(self):
        code = '''
from typing import Optional
def func(x: int
    pass
'''
        with patch('builtins.open', mock_open(read_data=code)):
            with self.assertRaises(SyntaxError):
                check_unused_imports('dummy_path.py')

if __name__ == '__main__':
    unittest.main()
