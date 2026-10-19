"""A deliberately small, syntax-based Python-to-JavaScript translator.

This module never executes submitted code. Unsupported Python constructs fail
with a readable message instead of silently producing misleading JavaScript.
"""

import ast


class UnsupportedSyntax(ValueError):
    """Raised when the input uses syntax outside the offline subset."""


_BINOPS = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
}
_CMPOPS = {
    ast.Eq: "===",
    ast.NotEq: "!==",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}


def _unsupported(node: ast.AST) -> UnsupportedSyntax:
    return UnsupportedSyntax(f"Offline translation does not support Python {type(node).__name__} yet.")


def _expr(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "null"
        if node.value is True:
            return "true"
        if node.value is False:
            return "false"
        if isinstance(node.value, (str, int, float)):
            import json

            return json.dumps(node.value, ensure_ascii=False)
        raise _unsupported(node)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, (ast.List, ast.Tuple)):
        return "[" + ", ".join(_expr(item) for item in node.elts) + "]"
    if isinstance(node, ast.Dict):
        pairs = []
        for key, value in zip(node.keys, node.values):
            if key is None:
                raise _unsupported(node)
            pairs.append(f"[{_expr(key)}]: {_expr(value)}")
        return "({" + ", ".join(pairs) + "})"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.FloorDiv):
            return f"Math.floor(({_expr(node.left)}) / ({_expr(node.right)}))"
        operator = _BINOPS.get(type(node.op))
        if operator is None:
            raise _unsupported(node.op)
        return f"({_expr(node.left)} {operator} {_expr(node.right)})"
    if isinstance(node, ast.UnaryOp):
        operator = {ast.UAdd: "+", ast.USub: "-", ast.Not: "!"}.get(type(node.op))
        if operator is None:
            raise _unsupported(node.op)
        return f"({operator}{_expr(node.operand)})"
    if isinstance(node, ast.BoolOp):
        operator = "&&" if isinstance(node.op, ast.And) else "||" if isinstance(node.op, ast.Or) else None
        if operator is None:
            raise _unsupported(node.op)
        return "(" + f" {operator} ".join(_expr(value) for value in node.values) + ")"
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise _unsupported(node)
        operator = _CMPOPS.get(type(node.ops[0]))
        if operator is None:
            raise _unsupported(node.ops[0])
        return f"({_expr(node.left)} {operator} {_expr(node.comparators[0])})"
    if isinstance(node, ast.IfExp):
        return f"({_expr(node.test)} ? {_expr(node.body)} : {_expr(node.orelse)})"
    if isinstance(node, ast.Subscript):
        return f"{_expr(node.value)}[{_expr(node.slice)}]"
    if isinstance(node, ast.Slice):
        raise _unsupported(node)
    if isinstance(node, ast.Attribute):
        return f"{_expr(node.value)}.{node.attr}"
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${"))
            elif isinstance(value, ast.FormattedValue):
                parts.append("${" + _expr(value.value) + "}")
            else:
                raise _unsupported(value)
        return "`" + "".join(parts) + "`"
    if isinstance(node, ast.Call):
        if node.keywords:
            raise _unsupported(node)
        if isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1:
            return f"({_expr(node.args[0])}.length)"
        target = {"str": "String", "int": "Number", "float": "Number", "bool": "Boolean", "print": "console.log"}.get(
            node.func.id if isinstance(node.func, ast.Name) else ""
        )
        if isinstance(node.func, ast.Name) and node.func.id == "range":
            raise _unsupported(node)
        function = target or _expr(node.func)
        return f"{function}({', '.join(_expr(arg) for arg in node.args)})"
    raise _unsupported(node)


def _assigned_names(function: ast.FunctionDef) -> list[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and node is not function:
            raise _unsupported(node)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    raise _unsupported(target)
                names.add(target.id)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if not isinstance(node.target, ast.Name):
                raise _unsupported(node.target)
            names.add(node.target.id)
    arguments = {arg.arg for arg in function.args.args}
    return sorted(names - arguments)


def _suite(statements: list[ast.stmt], indent: int, declared: set[str]) -> list[str]:
    output: list[str] = []
    pad = "    " * indent
    for statement in statements:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            continue  # Function or module docstring.
        if isinstance(statement, ast.Return):
            output.append(pad + ("return;" if statement.value is None else f"return {_expr(statement.value)};"))
        elif isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                raise _unsupported(statement)
            target = statement.targets[0]
            output.append(pad + f"{target.id} = {_expr(statement.value)};")
        elif isinstance(statement, ast.AnnAssign):
            if statement.value is not None:
                output.append(pad + f"{statement.target.id} = {_expr(statement.value)};")
        elif isinstance(statement, ast.AugAssign):
            operator = _BINOPS.get(type(statement.op))
            if operator is None:
                raise _unsupported(statement.op)
            if isinstance(statement.op, ast.FloorDiv):
                output.append(pad + f"{statement.target.id} = Math.floor({statement.target.id} / {_expr(statement.value)});")
            else:
                output.append(pad + f"{statement.target.id} {operator}= {_expr(statement.value)};")
        elif isinstance(statement, ast.If):
            output.append(pad + f"if ({_expr(statement.test)}) {{")
            output.extend(_suite(statement.body, indent + 1, declared))
            if statement.orelse:
                output.append(pad + "} else {")
                output.extend(_suite(statement.orelse, indent + 1, declared))
            output.append(pad + "}")
        elif isinstance(statement, ast.For):
            if not isinstance(statement.target, ast.Name):
                raise _unsupported(statement.target)
            if isinstance(statement.iter, ast.Call) and isinstance(statement.iter.func, ast.Name) and statement.iter.func.id == "range":
                args = statement.iter.args
                if not 1 <= len(args) <= 3 or statement.iter.keywords:
                    raise _unsupported(statement.iter)
                start = "0" if len(args) == 1 else _expr(args[0])
                stop = _expr(args[0]) if len(args) == 1 else _expr(args[1])
                step_node = args[2] if len(args) == 3 else None
                step_value = 1
                if step_node:
                    if isinstance(step_node, ast.Constant) and isinstance(step_node.value, int):
                        step_value = step_node.value
                    elif isinstance(step_node, ast.UnaryOp) and isinstance(step_node.op, ast.USub) and isinstance(step_node.operand, ast.Constant) and isinstance(step_node.operand.value, int):
                        step_value = -step_node.operand.value
                    else:
                        raise UnsupportedSyntax("Offline range loops need an integer step literal.")
                if step_value == 0:
                    raise UnsupportedSyntax("Offline range loops do not allow a zero step.")
                increment = f"{statement.target.id} += {step_value}" if step_value > 0 else f"{statement.target.id} -= {-step_value}"
                comparator = "<" if step_value > 0 else ">"
                output.append(pad + f"for (let {statement.target.id} = {start}; {statement.target.id} {comparator} {stop}; {increment}) {{")
            else:
                output.append(pad + f"for (const {statement.target.id} of {_expr(statement.iter)}) {{")
            output.extend(_suite(statement.body, indent + 1, declared))
            output.append(pad + "}")
            if statement.orelse:
                raise _unsupported(statement)
        elif isinstance(statement, ast.While):
            output.append(pad + f"while ({_expr(statement.test)}) {{")
            output.extend(_suite(statement.body, indent + 1, declared))
            output.append(pad + "}")
            if statement.orelse:
                raise _unsupported(statement)
        elif isinstance(statement, ast.Expr):
            output.append(pad + f"{_expr(statement.value)};")
        elif isinstance(statement, ast.Pass):
            continue
        elif isinstance(statement, ast.Break):
            output.append(pad + "break;")
        elif isinstance(statement, ast.Continue):
            output.append(pad + "continue;")
        else:
            raise _unsupported(statement)
    return output


def translate_python_to_javascript(source: str) -> str:
    """Translate a supported subset of Python function syntax into JavaScript."""
    try:
        module = ast.parse(source)
    except SyntaxError as error:
        raise UnsupportedSyntax(f"Python syntax error on line {error.lineno}: {error.msg}") from error
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
    if not functions or len(functions) != len(module.body):
        raise UnsupportedSyntax("Offline mode currently accepts only top-level Python function definitions.")

    rendered: list[str] = []
    for function in functions:
        if function.decorator_list or function.args.defaults or function.args.kw_defaults or function.args.posonlyargs or function.args.kwonlyargs or function.args.vararg or function.args.kwarg:
            raise _unsupported(function)
        params = [arg.arg for arg in function.args.args]
        declared = set(_assigned_names(function))
        body: list[str] = []
        if declared:
            body.append("    let " + ", ".join(declared) + ";")
        body.extend(_suite(function.body, 1, declared))
        if not body:
            body.append("    // Empty function body")
        rendered.append(f"function {function.name}({', '.join(params)}) {{\n" + "\n".join(body) + "\n}")
    return "\n\n".join(rendered)
