# J.A.R.V.I.S. OS — Plugin & Extension Architecture Guide

This document describes the design, API, lifecycle, and security model of the J.A.R.V.I.S. Plugin and Extension Architecture (introduced in Sprint 8).

---

## 1. High-Level Architecture

The Plugin & Extension Architecture allows J.A.R.V.I.S. to be extended dynamically without modifying its core codebase. Plugins can contribute:
1. **Dynamic Tools**: Enrolled into the Universal Tool Framework.
2. **Dynamic Agents**: Registered into the Router for task delegation.
3. **Workflow Templates**: Preserved goal plans for specific tasks.

### Architecture Component Map
```
              +----------------------------+
              |       PluginManager        |
              +--------------+-------------+
                             | 1. Discovers & Resolves (Top-Sort Kahn's)
                             v
              +--------------+-------------+
              |    PluginSecurityVisitor   | (AST Static Sandbox)
              +--------------+-------------+
                             | 2. Static Safety Validation Passes
                             v
              +--------------+-------------+
              |     BasePlugin Class       | (Dynamic Import & Instantiation)
              +--------------+-------------+
                             | 3. Triggers lifecycle hooks
                             v
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
+---------------+    +---------------+    +---------------+
| Custom Tools  |    | Custom Agents |    | Workflow Temp |
| (ToolRegistry)|    | (ExtRegistry) |    | (ExtRegistry) |
+---------------+    +---------------+    +---------------+
```

---

## 2. Plugin Manifest (`manifest.json`)

Every plugin must define a `manifest.json` file in its root directory containing metadata, dependency constraints, and permissions:

```json
{
  "id": "weather_plugin",
  "name": "Weather Plugin",
  "version": "1.0.0",
  "api_version": "v1",
  "description": "Adds weather commands and info tools.",
  "author": "J.A.R.V.I.S. Team",
  "license": "MIT",
  "category": "Weather",
  "entry_point": "plugin.py",
  "permissions_requested": ["read_file"],
  "supported_platforms": ["windows", "linux", "mac"],
  "dependencies": {
    "helper_plugin": ">=1.0.0"
  },
  "default_configuration": {
    "default_location": "New York",
    "temp_scale": "Celsius"
  }
}
```

### Manifest Specifications:
* **`id`** (Required): Unique identifier.
* **`api_version`** (Required): Targets core API compatibility (currently `v1`).
* **`entry_point`** (Required): Relative Python source path (usually `plugin.py`).
* **`permissions_requested`**: System tools the plugin is authorized to invoke (e.g. `read_file`, `execute_command`).
* **`supported_platforms`**: List of platforms (`windows`, `linux`, `mac`). Verified against `sys.platform`.
* **`dependencies`**: Mapping of plugin dependencies and version constraints (supports `>=` and `==`).

---

## 3. Plugin SDK Classes

The SDK defined in `core/plugins/sdk.py` offers sandboxed helper utilities:

### `BasePlugin`
All plugins must inherit from `BasePlugin`. It acts as the receiver for lifecycle event hooks:
* `on_install()`: Invoked once when first detected by the core database registry.
* `on_update()`: Triggered when the loaded version changes relative to the database record.
* `on_enable()`: Invoked when the plugin is turned ON (register tools and agents here).
* `on_disable()`: Invoked when the plugin is turned OFF (unregister/clean up here).
* `on_startup()`: Invoked on system startup for enabled plugins.
* `on_shutdown()`: Invoked during system shutdown.

### `PluginContext`
Contains context-specific components:
* `config`: Config wrapper loading `config.json` with fallback defaults.
* `storage`: Persistent key-value storage backed by `storage.json`.
* `logger`: Isolated logger matching logs to the plugin's ID.

---

## 4. Extension Points

Plugins hook into three key extension interfaces during `on_enable()`:

### A. Registering Custom Tools
Define a class inheriting from `BaseTool` (from `tools.base`) and register it using the global `tool_registry`:
```python
from tools.registry import tool_registry

class GetWeatherTool(BaseTool):
    name: str = "get_weather"
    description: str = "Retrieves weather info."
    # ...

# Inside Plugin.on_enable():
self.weather_tool = GetWeatherTool()
tool_registry.register(self.weather_tool)
```

### B. Registering Custom Agents
Register an agent class (defining a `process_message(self, msg, sid)` method) via `extension_registry`:
```python
from core.plugins.registry import extension_registry

class WeatherAgent:
    description = "Answers questions about the weather."
    def process_message(self, msg, sid):
        return "The weather is sunny, sir."

# Inside Plugin.on_enable():
self.agent = WeatherAgent()
extension_registry.register_agent("WeatherAgent", self.agent)
```

### C. Registering Workflow Templates
Preserve pre-planned task sequences for specific goals:
```python
from core.plugins.registry import extension_registry, WorkflowTemplate

# Inside Plugin.on_enable():
self.template = WorkflowTemplate(
    name="WeatherWorkflow",
    pattern="get weather report",
    tasks=[{
        "id": "t1",
        "description": "Fetch weather metrics",
        "assigned_agent": "WeatherAgent",
        "assigned_tool": "get_weather",
        "args": {"location": "London"}
    }]
)
extension_registry.register_workflow_template(self.template)
```

---

## 5. Security & Sandbox Engine

The architecture incorporates two safety layers to enforce sandboxing:

### Static Analysis Safety Check (AST Visitor)
Before a plugin's code is imported, `PluginSecurityVisitor` performs static AST checks on all `.py` files in the folder:
* Forbidden modules like `ctypes` are blocked.
* Use of `eval` or `exec` triggers sandbox violations.
* System modules (`subprocess`, network engines like `socket` or `requests`) are blocked unless the plugin manifest explicitly requests corresponding permissions (e.g. `execute_command`, `web_search`).
* Direct imports of database engines or core files like `memory.database` are forbidden.

### Runtime Permission Enforcement
When a plugin tool is executed:
1. `tools/registry.py` intercepts the call, identifying the calling plugin using the contextvar `active_plugin_id_var`.
2. The `PermissionEngine` intercepts the request.
3. If the tool is not contributed by the executing plugin and the permission isn't declared in the manifest's `permissions_requested`, the action raises a `PermissionDeniedError`.

---

## 6. SQLite Database Schema

The plugin registry persists plugin states in `plugins_registry`:

```sql
CREATE TABLE IF NOT EXISTS plugins_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    api_version TEXT NOT NULL,
    status TEXT NOT NULL,         -- ENABLED, DISABLED, ERROR
    load_time REAL,
    error_message TEXT,
    manifest TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
