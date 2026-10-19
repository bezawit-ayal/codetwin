const source = document.querySelector("#source");
const output = document.querySelector("#output");
const notes = document.querySelector("#notes");
const message = document.querySelector("#message");
const button = document.querySelector("#translate");
const editPythonButton = document.querySelector("#edit-python");
const pythonAIDialog = document.querySelector("#python-ai-dialog");
const closePythonAIButton = document.querySelector("#close-python-ai");
const submitPythonEditButton = document.querySelector("#submit-python-edit");
const pythonInstruction = document.querySelector("#python-instruction");
const pythonEditMessage = document.querySelector("#python-edit-message");
const offlineButton = document.querySelector("#translate-offline");
const checkButton = document.querySelector("#check");
const checkMessage = document.querySelector("#check-message");
const checkResults = document.querySelector("#check-results");
const testCasesInput = document.querySelector("#test-cases");
const suggestTestsButton = document.querySelector("#suggest-tests");
const suggestionMessage = document.querySelector("#suggestion-message");
const functionNameInput = document.querySelector("#function-name");
let suggestionContext = null;

function currentSuggestionContext() {
  return JSON.stringify({
    source: source.value,
    translated: output.textContent.trim(),
    functionName: functionNameInput.value.trim(),
  });
}

function invalidateSuggestions() {
  if (suggestionContext && currentSuggestionContext() !== suggestionContext) {
    suggestionContext = null;
    suggestionMessage.textContent = "The code or function name changed. These inputs may be out of date; suggest fresh inputs to update them.";
  }
}

[source, output, functionNameInput].forEach((field) => field.addEventListener("input", invalidateSuggestions));

suggestTestsButton.addEventListener("click", async () => {
  const sourceCode = source.value.trim();
  const translatedCode = output.textContent.trim();
  const functionName = functionNameInput.value.trim();
  const requestContext = currentSuggestionContext();
  if (!sourceCode || !translatedCode || translatedCode === "Your translated code will appear here.") {
    suggestionMessage.textContent = "Add Python code and translate it before asking for suggested inputs.";
    return;
  }
  suggestTestsButton.disabled = true;
  suggestTestsButton.querySelector("span").textContent = "Suggesting…";
  suggestionMessage.textContent = "Asking AI for useful inputs based on both functions…";
  try {
    const response = await fetch("/api/suggest-tests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_code: sourceCode,
        translated_code: translatedCode,
        function_name: functionName,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not suggest test inputs.");
    if (currentSuggestionContext() !== requestContext) {
      suggestionContext = null;
      suggestionMessage.textContent = "The code changed while suggestions were being prepared. Suggest again to get inputs for the latest code.";
      return;
    }
    testCasesInput.value = JSON.stringify(result.test_cases, null, 2);
    suggestionContext = requestContext;
    suggestionMessage.textContent = `${result.explanation} Review the inputs, then run the behavior check.`;
  } catch (error) {
    suggestionMessage.textContent = error.message;
  } finally {
    suggestTestsButton.disabled = false;
    suggestTestsButton.querySelector("span").textContent = "Suggest test inputs";
  }
});

editPythonButton.addEventListener("click", () => {
  pythonEditMessage.textContent = "The AI will use your current Python code as context.";
  pythonAIDialog.showModal();
  pythonInstruction.focus();
});

closePythonAIButton.addEventListener("click", () => pythonAIDialog.close());

submitPythonEditButton.addEventListener("click", async () => {
  const instruction = pythonInstruction.value.trim();
  if (!instruction) {
    pythonEditMessage.textContent = "Write a request for the Python code you want.";
    return;
  }
  submitPythonEditButton.disabled = true;
  submitPythonEditButton.querySelector("span").textContent = "Writing Python…";
  pythonEditMessage.textContent = "Asking the configured model to update your Python code…";
  try {
    const response = await fetch("/api/edit/python", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_code: source.value, instruction }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Python edit failed.");
    source.value = result.python_code;
    invalidateSuggestions();
    pythonInstruction.value = "";
    pythonAIDialog.close();
    pythonEditMessage.textContent = result.explanation || "Python code updated. Review it before translating.";
  } catch (error) {
    pythonEditMessage.textContent = error.message;
  } finally {
    submitPythonEditButton.disabled = false;
    submitPythonEditButton.querySelector("span").textContent = "Write Python code";
  }
});

button.addEventListener("click", async () => {
  const sourceCode = source.value.trim();
  if (!sourceCode) {
    message.textContent = "Add a Python function first.";
    return;
  }
  button.disabled = true;
  button.querySelector("span").textContent = "Translating…";
  message.textContent = "Sending your function to the configured model…";
  output.textContent = "Working on your translation…";
  invalidateSuggestions();
  try {
    const response = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_code: sourceCode }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Translation failed.");
    output.textContent = result.translated_code;
    invalidateSuggestions();
    notes.textContent = result.explanation;
    message.textContent = "Translation ready. Review it before using it.";
  } catch (error) {
    output.textContent = "Your translation will appear here.";
    invalidateSuggestions();
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Translate code";
  }
});

offlineButton.addEventListener("click", async () => {
  const sourceCode = source.value.trim();
  if (!sourceCode) {
    message.textContent = "Add a Python function first.";
    return;
  }
  offlineButton.disabled = true;
  offlineButton.querySelector("span").textContent = "Translating offline…";
  message.textContent = "Translating locally; no model API is used…";
  try {
    const response = await fetch("/api/translate/offline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_code: sourceCode }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Offline translation failed.");
    output.textContent = result.translated_code;
    invalidateSuggestions();
    notes.textContent = result.explanation;
    message.textContent = "Offline translation ready. Check supported syntax and review the result.";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    offlineButton.disabled = false;
    offlineButton.querySelector("span").textContent = "Translate offline";
  }
});

checkButton.addEventListener("click", async () => {
  let testCases;
  try {
    testCases = JSON.parse(testCasesInput.value);
    if (!Array.isArray(testCases) || testCases.length === 0) throw new Error("Enter a non-empty JSON array of test cases.");
  } catch (error) {
    checkMessage.textContent = error instanceof SyntaxError ? "Test inputs must be valid JSON." : error.message;
    return;
  }
  const translatedCode = output.textContent.trim();
  if (!translatedCode || translatedCode === "Your translated code will appear here.") {
    checkMessage.textContent = "Translate the code first, or paste JavaScript into the translation panel.";
    return;
  }
  checkButton.disabled = true;
  checkButton.querySelector("span").textContent = "Checking…";
  checkMessage.textContent = "Running both functions in isolated containers…";
  checkResults.replaceChildren();
  try {
    const response = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_code: source.value,
        translated_code: translatedCode,
        function_name: document.querySelector("#function-name").value.trim(),
        test_cases: testCases,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Behavior checks failed.");
    checkMessage.textContent = result.message;
    const caveat = document.createElement("p");
    caveat.className = "caveat";
    caveat.textContent = result.caveat;
    checkResults.append(caveat);
    result.checks.forEach((check) => {
      const row = document.createElement("div");
      row.className = `result-row ${check.passed ? "pass" : "fail"}`;
      const title = document.createElement("strong");
      title.textContent = `Case ${check.case} · ${check.passed ? "MATCH" : "DIFFERENT"}`;
      const detail = document.createElement("code");
      detail.textContent = `Python: ${JSON.stringify(check.python)}   JavaScript: ${JSON.stringify(check.javascript)}`;
      row.append(title, detail);
      checkResults.append(row);
    });
  } catch (error) {
    checkMessage.textContent = error.message;
  } finally {
    checkButton.disabled = false;
    checkButton.querySelector("span").textContent = "Run behavior checks";
  }
});
