# CodeTwin project plan

## Product goal

Help a developer migrate a small function from one language to another, understand the translation, and see evidence about whether its behavior is preserved.

## First release scope

- Direction: Python → JavaScript.
- Input: one small, self-contained function and optional plain JSON test cases.
- Output: translated JavaScript, a short explanation, and test results when execution is added.
- Initial checks: syntax validation and deterministic input/output comparisons.
- A limited offline Python → JavaScript translator is available for common function syntax; unsupported syntax returns an explanation.
- Explicit limitation: passing tests are evidence for the tested inputs, not proof of equivalence.
- Out of scope at first: full repositories, multiple language pairs, model training, accounts, billing, and unrestricted execution of user code.

## Development stages

1. **Foundation:** source tree, one-page interface, backend health endpoint, and a documented provider configuration. (Scaffolded.)
2. **Translation:** call a configured model, require structured output, and handle missing configuration, timeouts, and provider errors clearly. (Scaffolded; requires provider settings.)
3. **Review:** show source and target side by side, with an explanation and editable output. (Scaffolded.)
4. **Behavior checks:** define a test case format, run both versions in isolated containers with time and resource limits, and compare JSON-compatible results. (Implemented in the local app; requires Docker Desktop.)
5. **Evaluation:** maintain a small hand-checked benchmark of representative functions, edge cases, expected translations, and expected outputs. (Starter benchmark added in `benchmarks/`; it records a known Python/JavaScript string-conversion mismatch.)
6. **Hardening:** improve error reporting, privacy controls, safe execution, and deployment documentation before inviting broader use.

## Suggested architecture

- Browser UI: source editor, target selector (initially Python → JavaScript only), optional test-case editor, translation and result panes.
- Python API: request validation, translation-provider adapter, and later a validation/execution service.
- Provider adapter: configurable base URL, model, and API key from environment variables; never put secrets in browser code.
- Offline translator: a small AST-based subset converter for common functions that does not execute submitted code or require a model API.
- Validation: syntax checks first; execute only in an isolated sandbox once designed and reviewed.

## Quality measures

- Translation completion rate on the hand-checked benchmark.
- Syntax-valid output rate.
- Pass rate for paired test cases.
- Clear reporting of failed cases and model/provider errors.
- Track all metrics by language pair and code feature; do not collapse them into an unsupported single similarity percentage.

## Solo developer schedule (rough estimate)

- A first demo: a few weeks if already comfortable with Python and basic web development.
- A useful narrow MVP: roughly 1–3 months of part-time work, depending on experience and available hours.
- A dependable multi-language product: many more months, because translation coverage, evaluation, and safe execution grow in difficulty.

These are planning ranges, not deadlines. Build and evaluate one narrow capability before adding more languages.

## AI tools that can help

- A coding assistant such as Codex can help explain code, implement small scoped changes, review errors, and draft examples. Keep changes in this project folder and verify behavior yourself.
- An existing language-model API can power translation; compare providers on a fixed benchmark before choosing one. Keep its API key on the backend.
- An editor with code completion can speed up routine work, but it does not replace tests or safe execution.

## Project continuity

This folder is the canonical project workspace. `PROJECT_PLAN.md` records the agreed scope and roadmap so work can continue from this folder in later sessions.
