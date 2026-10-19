# CodeTwin codebase guide

This guide describes CodeTwin itself: the browser interface, the Python API, the offline translator, and the project support files. The backend is written in Python. The browser interface uses HTML, CSS, and JavaScript.

## Start with the request flow

```text
Browser (index.html + app.js)
        │ HTTP request
        ▼
Python API (main.py)
        ├── AI provider for AI translation, Python editing, and test suggestions
        ├── offline_translator.py for local Python → JavaScript translation
        └── Docker containers for behavior checks
```

For example, clicking **Translate offline** runs this path:

1. `app.js` reads the Python editor and sends it to `/api/translate/offline`.
2. `main.py` validates the request and calls `translate_python_to_javascript`.
3. `offline_translator.py` parses the Python source into an abstract syntax tree (AST), converts supported nodes, and returns JavaScript.
4. `main.py` returns JSON; `app.js` puts the JavaScript and explanation on the page.

## Project files

### `app/main.py` — Python web server and API

This is the main backend file. It creates the FastAPI application, defines request/response shapes, implements each API route, calls the configured AI provider, and runs the behavior checker.

- **Imports and app setup:** loads Python libraries, FastAPI, Pydantic, and the offline translator. `ROOT` points to the `app` directory. The `static` mount makes the browser files available to the page.
- **Request and response models:** classes such as `TranslationRequest`, `PythonEditRequest`, `CheckRequest`, and `TestCase` describe what the API accepts. `Field(...)` sets limits and required fields; FastAPI returns a validation error when a request does not match.
- **`_positional_arg_limits`:** reads the Python function signature with `ast` and finds the minimum and maximum number of positional arguments.
- **`_validate_suggested_cases`:** rejects AI test suggestions when the requested function cannot be found, requires unsupported keyword-only inputs, or a suggested case has an invalid argument count.
- **`_run_in_container`:** sends submitted code and test inputs to a short-lived Docker container. The Python runner executes the source function; the JavaScript runner uses Node's `vm`. Both produce JSON results. Docker is configured without network access and with resource limits. Python `print()` output is captured so it cannot corrupt the result JSON.
- **`GET /`:** serves `static/index.html`.
- **`GET /api/health`:** returns a small status response so a caller can tell whether the backend is running.
- **`POST /api/translate`:** checks the supported language direction, sends the Python code to the configured OpenAI-compatible model, and returns JavaScript plus an explanation.
- **`POST /api/edit/python`:** sends the current Python source and the user's instruction to the model; returns the complete revised Python source.
- **`POST /api/suggest-tests`:** asks the model for four JSON test cases, then checks their shape and argument counts before returning them.
- **`POST /api/translate/offline`:** calls the local AST translator. It does not call the AI provider.
- **`POST /api/check`:** runs Python and JavaScript with the same arguments, compares the JSON results case by case, and reports matches and differences.

The provider API key, URL, and model name are read from environment variables on the server. They are not sent to the browser.

### `app/offline_translator.py` — local Python-to-JavaScript converter

This file translates a supported subset of Python without an AI service.

- **`UnsupportedSyntax`:** the translator's clear error type for Python constructs it does not support.
- **`_BINOPS` and `_CMPOPS`:** maps Python arithmetic and comparison operators to their JavaScript spelling.
- **`_unsupported`:** creates an error that identifies a syntax node the converter cannot handle.
- **`_expr`:** converts expression nodes such as constants, variable names, arithmetic, comparisons, function calls, f-strings, and list/dictionary expressions.
- **`_assigned_names`:** gathers names assigned inside a function so they can be declared in JavaScript.
- **`_suite`:** converts statements such as `return`, assignment, `if`, and loops, while adding JavaScript braces and indentation.
- **`translate_python_to_javascript`:** parses the complete source, checks for supported top-level functions, and assembles the final JavaScript.

This is intentionally a small converter. If it encounters syntax outside its supported set, it raises `UnsupportedSyntax` instead of pretending that it translated the code.

### `app/static/index.html` — page structure

Defines the visible page: the Python editor, JavaScript output panel, translation buttons, function name, test input editor, behavior-check results, and the **Ask AI** dialog. Element IDs such as `source`, `output`, and `check` are the hooks that `app.js` uses. The page loads `styles.css` for appearance and `app.js` for interaction.

### `app/static/app.js` — browser behavior

Connects buttons and text fields to the backend API.

- At the top, `document.querySelector(...)` finds the page elements and keeps references to them.
- **Suggestion context functions** remember which Python, JavaScript, and function name the test suggestions were made for. When those change, the UI marks the suggestions as potentially outdated. It also ignores a suggestion response if the code changed while the model was responding.
- The **Suggest test inputs** click handler sends the current code to `/api/suggest-tests`, then fills in the returned cases and explanation.
- The **Ask AI** handlers open the dialog and submit the user's Python-writing instruction to `/api/edit/python`.
- The **Translate with AI** handler calls `/api/translate` and displays the result or a readable error.
- The **Translate offline** handler calls `/api/translate/offline`.
- The **Run behavior checks** handler parses the JSON inputs, calls `/api/check`, and builds one result row per case. Each row says whether the Python and JavaScript results matched.

The browser code uses `textContent` when it displays generated output and errors so returned text is shown as text, not interpreted as page HTML.

### `app/static/styles.css` — visual design

Contains the colors, typography, layout, buttons, editors, result styles, dialog, and mobile layout. The `:root` variables near the start define shared colors. The final `@media` rule rearranges the page for narrow screens.

### `app/__init__.py` — Python package marker

Marks `app` as a Python package so modules can import each other using paths such as `app.offline_translator`.

### `benchmarks/python_to_javascript.json` — hand-checked examples

Stores small Python functions, expected JavaScript, behavior-check arguments, and expected outputs. The known `str(True)` versus `String(true)` mismatch is intentionally recorded to show a real Python/JavaScript difference.

### `benchmarks/README.md` — benchmark instructions

Explains how to review the benchmark: translate each example, compare its output, run its cases, and record translation quality separately from behavior results.

### `requirements.txt` — Python dependencies

Lists the packages installed for the server: FastAPI for HTTP routes, Uvicorn to run the server, and Pydantic for request validation.

### `README.md` — setup and run instructions

Explains what CodeTwin does, how to configure an AI provider, how to start the local server, and which features require Docker or provider settings.

### `PROJECT_PLAN.md` — scope and roadmap

Records the product goal, first-release limits, development stages, architecture notes, and quality measures. It helps keep the project focused on Python-to-JavaScript migration while the core workflow improves.

### `.env.example` — configuration example

Shows the names of environment variables the server expects. It is a template; actual private credentials belong in local environment settings and should not be committed.

### `.gitignore` — files Git should leave untracked

Lists generated or private items to leave out of version control, including the virtual environment, Python cache files, `.env`, and build outputs.

## The four main user actions

| User action | Browser handler | Backend route | Main implementation |
| --- | --- | --- | --- |
| Translate with AI | `app.js` translation handler | `/api/translate` | Model request in `main.py` |
| Translate offline | `app.js` offline handler | `/api/translate/offline` | `translate_python_to_javascript` |
| Suggest inputs | `app.js` suggestion handler | `/api/suggest-tests` | Model response and signature validation in `main.py` |
| Compare behavior | `app.js` check handler | `/api/check` | `_run_in_container` and result comparison in `main.py` |

## A good way to study it

1. Start with `app/static/index.html` to see which controls exist.
2. Follow one button's event handler in `app/static/app.js`.
3. Find the matching route in `app/main.py`.
4. Follow the route to the helper or translator it calls.
5. Check `benchmarks/python_to_javascript.json` for a small example of expected behavior.

The project currently contains a generated `.venv` folder as well. It holds installed Python packages, not CodeTwin's own source, so it is not included in this guide.
