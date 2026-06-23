# J.A.R.V.I.S. OS — Configuration Guide

This guide details the configurable settings in the security engine.

---

## 1. File Location
All security policies and resource classifications are defined declaratively in:
[security_config.json](file:///e:/J.A.R.V.I.S/core/security_config.json)

---

## 2. Parameter Definitions

### `developer_mode` (boolean)
- `true`: Bypasses confirmation prompts for LOW, MEDIUM, and HIGH risk tasks. CRITICAL remains blocked.
- `false`: Normal strict policy enforcement.

### `protected_folders` (array of strings)
Absolute directory paths that trigger **CRITICAL** risk escalation if any write/delete/access is attempted:
```json
"protected_folders": [
  "C:\\Windows",
  "C:\\Program Files",
  "C:\\ProgramData"
]
```

### `protected_files` (array of strings)
File name substrings that trigger **CRITICAL** risk escalation (e.g. key stores, database files):
```json
"protected_files": [
  "id_rsa",
  "credentials",
  "jarvis_memory.db"
]
```

### `dangerous_commands` (array of regex strings)
Regex patterns checked against shell commands during execution inspection. Escalate command risk to **CRITICAL**:
```json
"dangerous_commands": [
  "rm\\s+-rf",
  "del\\s+/f\\s+/s",
  "shutdown\\s+-[sr]",
  "format\\s+[a-zA-Z]:",
  "reg\\s+delete"
]
```

### `tool_risks` (object mapping tool_name -> risk_level)
Assigns default risk classifications to Universal Tools:
```json
"tool_risks": {
  "read_file": "LOW",
  "write_file": "MEDIUM",
  "delete_file": "HIGH",
  "execute_command": "HIGH"
}
```
*Supported Risk Levels:* `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

### `policies` (object mapping risk_level -> action)
Determines action rules for each risk level:
```json
"policies": {
  "LOW": "ALLOW",
  "MEDIUM": "REQUIRE_CONFIRMATION",
  "HIGH": "REQUIRE_CONFIRMATION",
  "CRITICAL": "REQUIRE_CONFIRMATION"
}
```
*Supported Actions:* `ALLOW`, `REQUIRE_CONFIRMATION`, `DENY`.

### `approval_timeout_seconds` (integer)
The lifespan of generated approval tokens before they expire (default `300` seconds).
```json
"approval_timeout_seconds": 300
```
