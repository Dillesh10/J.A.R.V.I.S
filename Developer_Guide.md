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
