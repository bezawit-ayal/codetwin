"""Small CodeTwin API and static frontend host."""

from pathlib import Path
import ast
import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.offline_translator import UnsupportedSyntax, translate_python_to_javascript


ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
app = FastAPI(title="CodeTwin", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class TranslationRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=20_000)
    source_language: str = "python"
    target_language: str = "javascript"


class TranslationResponse(BaseModel):
    translated_code: str
    explanation: str


class PythonEditRequest(BaseModel):
    source_code: str = Field(default="", max_length=20_000)
    instruction: str = Field(min_length=1, max_length=2_000)


class PythonEditResponse(BaseModel):
    python_code: str
    explanation: str


class TestCase(BaseModel):
    args: list = Field(default_factory=list, max_length=20)


class CheckRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=20_000)
    translated_code: str = Field(min_length=1, max_length=20_000)
    function_name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    test_cases: list[TestCase] = Field(min_length=1, max_length=20)


class TestInputSuggestionRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=20_000)
    translated_code: str = Field(min_length=1, max_length=20_000)
    function_name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class TestInputSuggestionResponse(BaseModel):
    test_cases: list[TestCase] = Field(min_length=4, max_length=4)
    explanation: str


def _positional_arg_limits(source: str, function_name: str) -> tuple[int, int] | None:
    """Return required and maximum positional argument counts for a function, when known."""
    try:
        module = ast.parse(source)
    except SyntaxError:
        return None
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            positional = [*node.args.posonlyargs, *node.args.args]
            if node.args.vararg:
                return None
            required = len(positional) - len(node.args.defaults)
            return required, len(positional)
    return None


def _validate_suggested_cases(source: str, function_name: str, cases: list[TestCase]) -> None:
    """Reject generated cases that cannot call the requested Python function."""
    try:
        module = ast.parse(source)
    except SyntaxError as error:
        raise HTTPException(422, "Fix the Python syntax before suggesting test inputs.") from error

    function = next(
        (node for node in module.body
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name),
        None,
    )
    if function is None:
        raise HTTPException(422, f"Could not find a top-level Python function named '{function_name}'.")

    args = function.args
    required_keyword_only = [
        name for name, default in zip(args.kwonlyargs, args.kw_defaults) if default is None
    ]
    if required_keyword_only:
        raise HTTPException(
            422,
            "This function requires keyword-only inputs, which the behavior-check form does not support yet.",
        )

    positional = [*args.posonlyargs, *args.args]
    required = len(positional) - len(args.defaults)
    maximum = 20 if args.vararg else len(positional)
    for index, case in enumerate(cases, start=1):
        if not required <= len(case.args) <= maximum:
            expected = f"at least {required}" if args.vararg else f"between {required} and {maximum}"
            raise HTTPException(
                502,
                f"The AI suggested invalid inputs for case {index}: '{function_name}' needs {expected} positional arguments. Try again or enter inputs manually.",
            )
        try:
            json.dumps(case.args, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                502,
                f"The AI suggested a non-JSON input in case {index}. Try again or enter inputs manually.",
            ) from error


def _run_in_container(language: str, code: str, function_name: str, cases: list[dict]) -> list[dict]:
    """Run submitted code in a short-lived, resource-limited Docker container."""
    if language == "python":
        image = "python:3.12-slim"
        runner = r'''import contextlib, io, json, sys
payload = json.load(sys.stdin)
protocol_stdout = sys.stdout
out = []
try:
    scope = {"__builtins__": __builtins__}
    # User code may print while loading or running. Keep that output separate
    # so it cannot corrupt the JSON response consumed by the API.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        exec(compile(payload["code"], "<codetwin>", "exec"), scope, scope)
        fn = scope[payload["function_name"]]
        for case in payload["test_cases"]:
            try:
                value = fn(*case.get("args", []), **case.get("kwargs", {}))
                json.dumps(value, ensure_ascii=False, allow_nan=False)
                out.append({"ok": True, "value": value})
            except Exception as exc:
                out.append({"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:300]})
except Exception as exc:
    error = type(exc).__name__ + ": " + str(exc)[:300]
    out = [{"ok": False, "error": error} for _ in payload["test_cases"]]
protocol_stdout.write(json.dumps(out, ensure_ascii=False, allow_nan=False))
'''
        command = ["docker", "run", "--rm", "-i", "--network", "none", "--read-only",
                   "--memory=128m", "--cpus=0.5", "--pids-limit=32", "--cap-drop=ALL",
                   "--security-opt=no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                   image, "python", "-I", "-c", runner]
    else:
        image = "node:22-slim"
        runner = r'''const fs = require("fs");
const vm = require("vm");
const p = JSON.parse(fs.readFileSync(0, "utf8"));
const ctx = vm.createContext({});
const results = [];
try {
  new vm.Script(p.code, {filename: "<codetwin>"}).runInContext(ctx, {timeout: 1000});
  const camelCaseName = p.function_name.replace(/_([a-zA-Z0-9])/g, (_, char) => char.toUpperCase());
  const fn = ctx[p.function_name] || ctx[camelCaseName];
  if (typeof fn !== "function") throw new Error("Function not found: " + p.function_name);
  for (const c of p.test_cases) {
    try {
      const value = fn(...(c.args || []));
      if (value && typeof value.then === "function") throw new Error("Async functions are not supported yet");
      JSON.stringify(value);
      results.push({ok: true, value: value === undefined ? null : value});
    } catch (e) { results.push({ok: false, error: String(e).slice(0, 300)}); }
  }
} catch (e) { for (let i = 0; i < p.test_cases.length; i++) results.push({ok: false, error: String(e).slice(0, 300)}); }
process.stdout.write(JSON.stringify(results));
'''
        command = ["docker", "run", "--rm", "-i", "--network", "none", "--read-only",
                   "--memory=128m", "--cpus=0.5", "--pids-limit=32", "--cap-drop=ALL",
                   "--security-opt=no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                   image, "node", "-e", runner]

    payload = json.dumps({"code": code, "function_name": function_name, "test_cases": cases})
    try:
        completed = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=12)
    except FileNotFoundError as error:
        raise HTTPException(503, "Docker is required for behavior checks. Install and start Docker Desktop.") from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, f"The {language} code exceeded its 12-second time limit.") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-600:] or "Docker runner failed."
        raise HTTPException(502, detail)
    try:
        results = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise HTTPException(502, f"The {language} runner returned invalid output.") from error
    if not isinstance(results, list) or len(results) != len(cases):
        raise HTTPException(502, f"The {language} runner returned an unexpected result.")
    return results


@app.get("/")
def home() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "codetwin"}


@app.post("/api/translate", response_model=TranslationResponse)
def translate(request: TranslationRequest) -> TranslationResponse:
    if (request.source_language.lower(), request.target_language.lower()) != (
        "python",
        "javascript",
    ):
        raise HTTPException(400, "The first version supports Python → JavaScript only.")

    api_key = os.getenv("CODETWIN_API_KEY")
    base_url = os.getenv("CODETWIN_BASE_URL", "").rstrip("/")
    model = os.getenv("CODETWIN_MODEL")
    if not api_key or not base_url or not model:
        raise HTTPException(
            503,
            "Translation is not configured yet. Set CODETWIN_API_KEY, "
            "CODETWIN_BASE_URL, and CODETWIN_MODEL on the backend.",
        )

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "developer",
                "content": (
                    "You are a source-code translator. Translate the user's complete Python "
                    "function into equivalent JavaScript. Do not return Python or omit the "
                    "function. Format the JavaScript as readable multi-line code: put each "
                    "statement on its own line, place block contents on separate lines, and "
                    "indent nested blocks with four spaces. Never collapse a function into "
                    "one long line. Return exactly a JSON object with two string properties: "
                    '"translated_code" (the complete JavaScript function) and "explanation" '
                    "(a brief note). Example format: "
                    '{"translated_code":"function f(x) {\\n    return x;\\n}",'
                    '"explanation":"Direct translation."}'
                ),
            },
            {
                "role": "user",
                "content": "Translate this Python function to JavaScript:\n\n" + request.source_code,
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "codetwin_translation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "translated_code": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["translated_code", "explanation"],
                    "additionalProperties": False,
                },
            },
        },
    }
    endpoint = f"{base_url}/chat/completions"
    http_request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return TranslationResponse(**parsed)
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8", errors="replace")
            parsed_error = json.loads(body)
            detail = parsed_error.get("error", {}).get("message", body)
        except (ValueError, AttributeError):
            detail = "The provider returned an error without details."
        detail = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[API key hidden]", str(detail))[:500]
        logger.warning("Translation provider returned HTTP %s: %s", error.code, detail)
        raise HTTPException(502, f"Translation provider returned HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        logger.warning("Could not reach the configured translation provider: %s", error)
        raise HTTPException(502, "Could not reach the configured translation provider.") from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(502, "The translation provider returned an unexpected response.") from error


@app.post("/api/edit/python", response_model=PythonEditResponse)
def edit_python(request: PythonEditRequest) -> PythonEditResponse:
    api_key = os.getenv("CODETWIN_API_KEY")
    base_url = os.getenv("CODETWIN_BASE_URL", "").rstrip("/")
    model = os.getenv("CODETWIN_MODEL")
    if not api_key or not base_url or not model:
        raise HTTPException(
            503,
            "AI editing is not configured yet. Set CODETWIN_API_KEY, "
            "CODETWIN_BASE_URL, and CODETWIN_MODEL on the backend.",
        )

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "developer",
                "content": (
                    "You are a Python coding assistant. Follow the user's instruction to create "
                    "or edit Python code. Return the complete resulting Python source, not a "
                    "patch or Markdown code fence. Preserve existing behavior and function "
                    "names unless the instruction asks to change them. Use readable multi-line "
                    "Python with four spaces per indentation level; do not collapse the code "
                    "into one long line. Return exactly a JSON "
                    'object with string properties "python_code" and "explanation".'
                ),
            },
            {
                "role": "user",
                "content": (
                    "Current Python source (may be empty):\n"
                    "```python\n" + request.source_code + "\n```\n\n"
                    "Requested change:\n" + request.instruction
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "codetwin_python_edit",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "python_code": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["python_code", "explanation"],
                    "additionalProperties": False,
                },
            },
        },
    }
    endpoint = f"{base_url}/chat/completions"
    http_request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return PythonEditResponse(**parsed)
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8", errors="replace")
            parsed_error = json.loads(body)
            detail = parsed_error.get("error", {}).get("message", body)
        except (ValueError, AttributeError):
            detail = "The provider returned an error without details."
        detail = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[API key hidden]", str(detail))[:500]
        logger.warning("Python edit provider returned HTTP %s: %s", error.code, detail)
        raise HTTPException(502, f"AI editor provider returned HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        logger.warning("Could not reach the configured Python edit provider: %s", error)
        raise HTTPException(502, "Could not reach the configured AI editor provider.") from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(502, "The AI editor returned an unexpected response.") from error


@app.post("/api/suggest-tests", response_model=TestInputSuggestionResponse)
def suggest_test_inputs(request: TestInputSuggestionRequest) -> TestInputSuggestionResponse:
    api_key = os.getenv("CODETWIN_API_KEY")
    base_url = os.getenv("CODETWIN_BASE_URL", "").rstrip("/")
    model = os.getenv("CODETWIN_MODEL")
    if not api_key or not base_url or not model:
        raise HTTPException(
            503,
            "AI test suggestions are not configured yet. Set CODETWIN_API_KEY, "
            "CODETWIN_BASE_URL, and CODETWIN_MODEL on the backend.",
        )

    argument_limits = _positional_arg_limits(request.source_code, request.function_name)
    args_schema: dict = {"type": "array", "items": {}}
    if argument_limits:
        args_schema["minItems"], args_schema["maxItems"] = argument_limits

    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 300,
        "messages": [
            {
                "role": "developer",
                "content": (
                    "You suggest beginner-friendly behavior-check inputs for a Python function "
                    "and its JavaScript translation. Return exactly 4 varied, JSON-serializable "
                    "cases that fit the function's positional arguments. Include typical inputs and, "
                    "when appropriate for the argument types, empty, zero, negative, boundary, "
                    "or unusual string values. Each case must be an object with an args array, for example "
                    '{"args":["Ada"]}. Return exactly a JSON object with "test_cases" as an '
                    'array of four such objects and "explanation" as a short note. Do not include '
                    "expected outputs, kwargs, code, or Markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Target function name: " + request.function_name + "\n"
                    "Python function:\n```python\n" + request.source_code + "\n```\n\n"
                    "Translated JavaScript function:\n```javascript\n" + request.translated_code + "\n```"
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "codetwin_test_input_suggestions",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "test_cases": {
                            "type": "array",
                            "minItems": 4,
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "args": args_schema,
                                },
                                "required": ["args"],
                                "additionalProperties": False,
                            },
                        },
                        "explanation": {"type": "string"},
                    },
                    "required": ["test_cases", "explanation"],
                    "additionalProperties": False,
                },
            },
        },
    }
    endpoint = f"{base_url}/chat/completions"
    http_request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        cases = [TestCase.model_validate(case) for case in parsed["test_cases"]]
        if len(cases) != 4:
            raise HTTPException(
                502,
                "The AI must suggest exactly four test cases. Try again or enter inputs manually.",
            )
        _validate_suggested_cases(request.source_code, request.function_name, cases)
        return TestInputSuggestionResponse(
            test_cases=cases,
            explanation=parsed["explanation"],
        )
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8", errors="replace")
            parsed_error = json.loads(body)
            detail = parsed_error.get("error", {}).get("message", body)
        except (ValueError, AttributeError):
            detail = "The provider returned an error without details."
        detail = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[API key hidden]", str(detail))[:500]
        logger.warning("Test suggestion provider returned HTTP %s: %s", error.code, detail)
        raise HTTPException(502, f"AI test suggestion provider returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        logger.warning("Could not reach the configured test suggestion provider: %s", error)
        raise HTTPException(502, "Could not reach the configured AI test suggestion provider.") from error
    except TimeoutError as error:
        logger.warning("Configured test suggestion provider timed out: %s", error)
        raise HTTPException(504, "AI test suggestions took too long. Try again or enter cases manually.") from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(
            502,
            "The AI returned test inputs in an invalid format. Try again or enter the cases manually.",
        ) from error


@app.post("/api/translate/offline", response_model=TranslationResponse)
def translate_offline(request: TranslationRequest) -> TranslationResponse:
    if (request.source_language.lower(), request.target_language.lower()) != ("python", "javascript"):
        raise HTTPException(400, "Offline mode supports Python → JavaScript only.")
    try:
        javascript = translate_python_to_javascript(request.source_code)
    except UnsupportedSyntax as error:
        raise HTTPException(422, str(error)) from error
    return TranslationResponse(
        translated_code=javascript,
        explanation=(
            "Translated locally without an AI service. Offline mode supports a limited set of "
            "functions, assignments, returns, conditions, loops, and simple expressions. "
            "Review the translation because Python and JavaScript semantics differ."
        ),
    )


@app.post("/api/check")
def check_behavior(request: CheckRequest) -> dict:
    cases = [case.model_dump() for case in request.test_cases]
    python_results = _run_in_container("python", request.source_code, request.function_name, cases)
    javascript_results = _run_in_container("javascript", request.translated_code, request.function_name, cases)
    checks = []
    for index, (python_result, javascript_result) in enumerate(zip(python_results, javascript_results), start=1):
        same = python_result == javascript_result
        checks.append({
            "case": index,
            "passed": same,
            "python": python_result,
            "javascript": javascript_result,
        })
    passed = sum(check["passed"] for check in checks)
    return {
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "message": f"Outputs matched for {passed} of {len(checks)} supplied test cases.",
        "caveat": "This checks only the supplied inputs; it does not prove full program equivalence.",
    }
