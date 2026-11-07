from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from fractions import Fraction

# Only equations that end in a concrete numeric result are checked. This is
# deliberately conservative: it is better to miss a complicated formula than
# to flag ordinary prose.
_ALLOWED_EXPRESSION = re.compile(r"[0-9.+\-*/()\s]+$")
_RESULT = re.compile(r"\s*(-?\d+(?:\.\d+)?)(?![0-9]|\.[0-9])")

_TRANSLATION = str.maketrans(
    {
        "＝": "=",
        "＋": "+",
        "－": "-",
        "＊": "*",
        "×": "*",
        "✕": "*",
        "╳": "*",
        "÷": "/",
        "／": "/",
        "−": "-",
        "–": "-",
        "—": "-",
        "（": "(",
        "）": ")",
    }
)

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


@dataclass(frozen=True)
class MathIssue:
    """A wrong calculation found in one paragraph."""

    expression: str
    given: str
    expected: str

    @property
    def message(self) -> str:
        return f"# 计算有误：{self.expression} = {self.given}，正确结果应为 {self.expected}。"


def find_math_issues(text: str) -> list[MathIssue]:
    normalized = text.translate(_TRANSLATION).replace("\u00a0", " ")
    issues: list[MathIssue] = []
    seen: set[tuple[str, str]] = set()

    for equal_sign in re.finditer(r"=", normalized):
        expression = _expression_before(normalized, equal_sign.start())
        if expression is None:
            continue

        result_match = _RESULT.match(normalized, equal_sign.end())
        if result_match is None:
            continue

        given = result_match.group(1)
        expected = _evaluate(expression)
        if expected is None or expected == _fraction(given):
            continue

        key = (expression, given)
        if key in seen:
            continue
        seen.add(key)
        issues.append(
            MathIssue(
                expression=_pretty_expression(expression),
                given=given.replace("-", "−"),
                expected=_format_fraction(expected),
            )
        )

    return issues


def _expression_before(text: str, equal_index: int) -> str | None:
    match = _ALLOWED_EXPRESSION.search(text[:equal_index])
    if match is None:
        return None

    raw = match.group()
    expression = raw.strip()
    if not expression or len(expression) > 160:
        return None
    if not any(operator in expression for operator in "+-*/"):
        return None

    # Reject matches that begin in the middle of a number such as 1,000+2.
    lead = len(raw) - len(raw.lstrip())
    before_index = match.start() + lead - 1
    if before_index >= 0:
        previous = text[before_index]
        if previous.isascii() and (previous.isalnum() or previous in "._,"):
            return None

    return expression


def _evaluate(expression: str) -> Fraction | None:
    try:
        tree = ast.parse(expression, mode="eval")
        return _eval_node(tree.body, depth=0)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _eval_node(node: ast.AST, depth: int) -> Fraction:
    if depth > 30:
        raise ValueError("expression is too deeply nested")

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand, depth + 1)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        operation = _BIN_OPS.get(type(node.op))
        if operation is None:
            raise ValueError("unsupported operator")
        left = _eval_node(node.left, depth + 1)
        right = _eval_node(node.right, depth + 1)
        return operation(left, right)
    raise ValueError("unsupported expression")


def _fraction(value: str) -> Fraction:
    if "." in value:
        return Fraction(value)
    return Fraction(int(value), 1)


def _format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator).replace("-", "−")
    return f"{value.numerator}/{value.denominator}".replace("-", "−")


def _pretty_expression(expression: str) -> str:
    expression = expression.replace("*", " × ").replace("/", " ÷ ")
    return re.sub(r"\s+", " ", expression).strip()
