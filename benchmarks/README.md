# Python → JavaScript starter benchmark

`python_to_javascript.json` is a small, hand-checked baseline for the offline translator. It covers arithmetic, conditionals, loops, built-ins, and formatted strings. Each case records its source, expected translation, and behavior-check inputs and outputs.

## How to use it

For each case:

1. Translate the Python source with offline mode.
2. Compare the generated JavaScript with `expected_translation` after normalizing only line endings. Keep meaningful formatting and syntax differences visible for review.
3. Run the listed `test_cases` through the behavior checker and compare both language results with `expected_outputs`.
4. Record translation completion, exact-output match, and per-case behavior results separately. A passing behavior check covers only those inputs; it does not establish equivalence.

The `string-conversion` case documents a known semantic mismatch: JavaScript `String(true)` returns `"true"`, while Python `str(True)` returns `"True"`. It is included to ensure the benchmark surfaces a real gap instead of treating every supported syntax form as behavior-preserving. Preserve this case until the translator handles the difference, then update its expected translation and remove the known-difference note with a reviewed change.

This is an initial baseline, not a broad language-conformance suite. Add cases when a syntax feature is intentionally added or a user-visible mismatch is found. Expected outputs and translations should be reviewed by a person familiar with both languages.
