# CodeTwin

CodeTwin translates small Python functions into JavaScript, then compares both versions using the same test inputs.

> CodeTwin is an early prototype. It supports Python → JavaScript. Passing tests do not prove that two programs are equivalent.

## What it can do

- Translate code with an AI provider such as Ollama running locally.
- Translate a limited set of Python syntax without AI.
- Ask AI to write or edit a Python function and suggest test inputs.
- Run both functions with the same inputs and show where their results differ.

## Run on Windows

You need Python 3.11 or newer. Docker Desktop is needed for behavior checks. Ollama is optional and can provide AI locally.

Clone this repository, then open **Command Prompt** in the new `codetwin` folder:

```bat
git clone https://github.com/bezawit-ayal/codetwin.git
cd codetwin
```

Create a Python environment and install CodeTwin's dependencies:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

### Use AI with Ollama

Install and open [Ollama for Windows](https://ollama.com/download/windows). In Command Prompt, download the model:

```bat
ollama pull qwen2.5-coder:3b
```

Set the Ollama connection and start CodeTwin:

```bat
set "CODETWIN_BASE_URL=http://localhost:11434/v1"
set "CODETWIN_API_KEY=ollama"
set "CODETWIN_MODEL=qwen2.5-coder:3b"
python -m uvicorn app.main:app --reload
```

Keep this window open. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. The settings above last only for this Command Prompt window. For another compatible AI provider, use that provider's base URL, API key, and model.

### Use offline translation

You do not need an AI provider for **Translate offline**. If CodeTwin is already running, choose **Translate offline**. Otherwise, open Command Prompt in the project folder, activate the environment, and start the app:

```bat
.venv\Scripts\activate.bat
python -m uvicorn app.main:app --reload
```

Offline translation supports only a limited set of Python syntax.

## Check behavior

Start Docker Desktop, then choose **Run behavior checks** in CodeTwin. It runs both functions in separate Docker containers and compares their results for the inputs you supplied. Docker may download the required images the first time.

The results show what happened for those test inputs only; they do not guarantee that the programs behave identically in every situation.

## Current limits

- Python → JavaScript only.
- Small, self-contained functions, not full projects.
- AI features need a configured provider.
- Behavior checks need Docker Desktop.

## Feedback

Found a problem or have an idea? Open an issue on this repository. Include a small code example and steps to reproduce it.

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the project roadmap.
