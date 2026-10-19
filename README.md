# CodeTwin

CodeTwin is a code migration assistant. Its first milestone focuses on translating small, self-contained functions from Python to JavaScript and checking whether both versions behave alike on the same test inputs.

## Current status

This folder is the project home. The initial scaffold contains a small web interface and a backend API. Translation uses an OpenAI-compatible chat completions endpoint configured through environment variables; no model key or provider is included. The first release should report observed test results, not claim that programs are mathematically equivalent.

## Run locally

1. Install Python 3.11 or newer.
2. In this folder, create and activate a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Copy `.env.example` as a reference, then set `CODETWIN_API_KEY`, `CODETWIN_BASE_URL`, and `CODETWIN_MODEL` in your local environment for a compatible provider. The app does not load `.env` automatically yet.
5. Start the app with `uvicorn app.main:app --reload`.
6. Open `http://127.0.0.1:8000`.

The app will serve the frontend, `/api/translate`, `/api/translate/offline`, `/api/edit/python`, `/api/suggest-tests`, and `/api/check`. AI translation, the **Ask AI** Python editor, and **Suggest test inputs** need provider configuration. The Python AI editor follows an instruction to create or revise the source pane; review the result before translating it. Suggested cases are checked against the selected function's positional parameter count, remain editable, and are not run until the developer chooses **Run behavior checks**. The suggestion explanation is marked out of date when either code pane or the function name changes. The **Translate offline** action handles a limited Python syntax subset without an AI service and explains when input is unsupported. Behavior checks require Docker Desktop running; each language version runs in a short-lived container with no network, a read-only filesystem, and resource limits. Keep provider keys private and out of source control. Do not expose this local runner as a public service without a security review.

## Project plan

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the scope, development stages, evaluation plan, and solo-developer guidance. Keep the first supported direction to Python → JavaScript until the checks are useful.

## Learn the codebase

Read [CODEBASE_GUIDE.md](CODEBASE_GUIDE.md) for a file-by-file guide to the Python backend, offline translator, browser interface, behavior checker, and project support files.
