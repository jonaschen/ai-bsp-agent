import ast
import sys

def check_unused_imports(filepath):
    with open(filepath, "r") as f:
        tree = ast.parse(f.read())

    used_names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        # Note: In type hints like `List[Optional[int]]`, `Optional` is a Name node in AST.

    if 'Optional' in used_names:
        print("Optional is USED.")
    else:
        print("Optional is NOT used.")

if __name__ == "__main__":
    check_unused_imports(sys.argv[1])
