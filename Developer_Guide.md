# J.A.R.V.I.S. OS — Developer Guide

This guide describes how to work with the Enterprise Permission & Security Engine during development.

---

## 1. Developer Mode

Developer Mode is designed to reduce confirmation prompts for developers during rapid code-test iterations.
- **Config**: Enabled by setting `"developer_mode": true` in `core/security_config.json`.
- **Behavior**: Auto-approves **LOW**, **MEDIUM**, and **HIGH** risk operations immediately.
- **Critical Policy**: **CRITICAL** risks are *never* bypassed, ensuring critical files and systems remain protected.

---

## 2. Adding a New Tool & Setting Risk Profile

When writing a new tool under the Universal Tool Framework:
1. Define the class inheriting from `BaseTool`.
2. Open `core/security_config.json`.
3. Add the tool's name to the `"tool_risks"` object and set its default risk:
   ```json
   "tool_risks": {
     "my_new_tool": "LOW"
   }
   ```
4. If omitted, the tool will default to a risk level of **MEDIUM**.

---

## 3. Developing & Testing

### Running Security Tests
Run the dedicated security unit tests:
```bash
.venv\Scripts\python.exe tests/test_security.py
```

### Mocking Tool Executions in Other Unit Tests
Since tools are wrapped automatically on registration, executing them directly in unit tests outside the Workflow Engine will fail with `ConfirmationRequiredError`.
To prevent this, the engine automatically detects if `unittest` is running and bypasses validations if **no active workflow context is set**. 
In your component tests, simply invoke `tool.execute()` directly. It will execute normally:
```python
def test_my_tool_isolation(self):
    tool = MyTool()
    res = tool.execute(arg="value")
    self.assertEqual(res, "success")
```

### Testing Security Policies Explicitly
If you are writing tests specifically for security rules, set the context variables `active_workflow_id_var` and `active_task_id_var`. This enables the engine's checks and allows you to test confirmation and denial flows:
```python
from core.security import active_workflow_id_var, active_task_id_var

token_wf = active_workflow_id_var.set("WF-TEST")
token_task = active_task_id_var.set("TASK-TEST")
try:
    # Executions here will trigger full validation checks
    tool.execute()
finally:
    active_workflow_id_var.reset(token_wf)
    active_task_id_var.reset(token_task)
```

---

## 4. Developing & Testing Plugins

To build custom tools, agents, or workflow templates for J.A.R.V.I.S. OS:
1. Follow the manifest guidelines and SDK lifecycle methods outlined in the [Plugins Development Guide](file:///e:/J.A.R.V.I.S/PLUGINS.md).
2. Place your plugin folder in the `/plugins/` directory.
3. Test your plugin's lifecycle and sandboxing using the dedicated test suite:
   ```bash
   .venv\Scripts\python.exe -m unittest tests/test_plugins.py
   ```

---

## 5. Utilizing the AI Provider Abstraction Layer

When developing new features, agents, or plugins that require LLM completions, vision capabilities, or embedding generation, do NOT instantiate client libraries (e.g. OpenAI or Gemini SDKs) directly. Instead, import and query the centralized `provider_manager`.

### Basic Conversational Invocation
```python
from core.providers import provider_manager

messages = [
    {"role": "user", "content": "Analyze this code structure."}
]

# The manager handles model selection, system instructions, and routing automatically
response = provider_manager.chat(
    messages=messages,
    task_type="coding"
)
print(response.content)
```

### Vision Processing
```python
from core.providers import provider_manager

response = provider_manager.vision(
    image_data="temp_image.png",
    prompt="Read the text inside this image."
)
print(response.content)
```

### Exception Handling
All exceptions are mapped to a standardized provider hierarchy under `core.providers.exceptions`. Always handle unified errors:
```python
from core.providers.exceptions import AuthenticationError, RateLimitError, ProviderUnavailable

try:
    response = provider_manager.chat(messages=messages)
except RateLimitError:
    # Handle rate-limiting gracefully (e.g., exponential backoff)
    pass
except ProviderUnavailable:
    # Handle entire cloud cluster offline
    pass
```

### Testing Provider Integrations
Use the dedicated provider test suite to run diagnostics and confirm correct exception mappings:
```bash
.venv\Scripts\python.exe -m unittest tests/test_providers.py
```

---

## 6. Developing & Testing Voice Intelligence

When extending J.A.R.V.I.S. with voice interfaces:
1. Refer to the complete manifest guidelines in [VOICE.md](file:///e:/J.A.R.V.I.S/VOICE.md).
2. Invoke Speech-to-Text and Text-to-Speech via the unified provider wrappers:
   - STT: `provider_manager.stt(audio_file_path)`
   - TTS: `provider_manager.tts_speak(text)`
3. Run the voice unit test suite locally to verify pipeline components and mock spoken permissions:
   ```bash
   .venv\Scripts\python.exe -m unittest tests/test_voice.py
   ```
