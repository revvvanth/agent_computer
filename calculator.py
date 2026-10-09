"""Bounded arithmetic shared by structured and computer arms; no Python eval."""
import ast
import json
import math
import operator
import sys


def calculate(expression: str) -> float:
    if len(expression) > 200:
        raise ValueError('Expression too long')
    tree = ast.parse(expression, mode='eval')
    if len(list(ast.walk(tree))) > 60:
        raise ValueError('Expression too complex')
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = float(node.value)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            result = operations[type(node.op)](visit(node.left), visit(node.right))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        else:
            raise ValueError('Only numeric + - * / and parentheses are allowed')
        if not math.isfinite(result) or abs(result) > 1e12:
            raise ValueError('Result outside numeric bounds')
        return result

    return visit(tree.body)


if __name__ == '__main__':
    print(json.dumps({'expression': sys.argv[1], 'value': calculate(sys.argv[1])}))
