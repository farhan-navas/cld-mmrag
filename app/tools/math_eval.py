# tools/math_eval.py
from __future__ import annotations
import ast
import operator as op
from typing import Union
from tools.models import MathInput, MathOutput

Number = Union[int, float]

OPS_BIN = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}
OPS_UNARY = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}

def _eval(node: ast.AST) -> float:
    # Numeric literal
    if isinstance(node, ast.Constant):
        val = node.value
        if isinstance(val, (int, float)):
            return float(val)
        raise ValueError("Only numeric literals are allowed.")

    # Parentheses
    if isinstance(node, ast.Expression):
        return _eval(node.body)

    # Unary ops: +x, -x
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS_UNARY:
        return float(OPS_UNARY[type(node.op)](_eval(node.operand)))

    # Binary ops: x + y, x * y, etc.
    if isinstance(node, ast.BinOp) and type(node.op) in OPS_BIN:
        left = _eval(node.left)
        right = _eval(node.right)
        return float(OPS_BIN[type(node.op)](left, right))

    # Disallow everything else for safety (Names, Calls, Attrs, etc.)
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")

def math_eval(inp: MathInput) -> MathOutput:
    expr = inp.expression.strip()
    if not expr:
        raise ValueError("Empty expression.")
    tree = ast.parse(expr, mode="eval")
    result = _eval(tree)
    return MathOutput(result=result)