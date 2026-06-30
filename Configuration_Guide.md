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

---

## 3. AI Provider Configuration
All provider configurations, task routing rules, and fallback priorities are defined in:
[providers_config.json](file:///e:/J.A.R.V.I.S/core/providers_config.json)

### `providers` (object)
Defines parameters for individual provider APIs:
- `api_key`: API connection token (automatically resolved from environment variables if omitted).
- `base_url`: Target REST endpoint (customizable for OpenRouter or Ollama local instances).
- `model_name`: Default fallback model ID for this provider.
- `timeout` / `retries`: Connection limits.
- `temperature` / `max_tokens`: Default LLM sampling parameters.

### `routing` (object)
Maps task categories to specific providers and models:
```json
"routing": {
  "simple_conversation": {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free"},
  "vision": {"provider": "gemini", "model": "gemini-2.5-flash"},
  "embeddings": {"provider": "gemini", "model": "models/embedding-001"}
}
```
*Supported Task Categories:* `simple_conversation`, `reasoning`, `coding`, `vision`, `long_context`, `embeddings`.

### `fallback_priority` (array of strings)
Ordered sequence of providers queried in case the primary routed provider is unavailable, rate-limited, or times out.
```json
"fallback_priority": ["openrouter", "gemini", "openai", "ollama"]
```

---

## 4. Voice Intelligence Configuration
All voice preferences, wake words, VAD metrics, and conversation timeout settings are defined in:
[voice_config.json](file:///e:/J.A.R.V.I.S/voice/voice_config.json)

### `preferred_stt` (string)
The active speech-to-text transcription engine.
- Supported Values: `local` (free Google Web Speech API), `openai` (hosted Whisper-1), `faster-whisper` (local stub), `whisper-cpp` (local stub).

### `preferred_tts` (string)
The active text-to-speech synthesis engine.
- Supported Values: `edge-tts` (free neural voice), `openai` (hosted OpenAI TTS), `elevenlabs` (high quality voices), `piper` (local stub), `coqui` (local stub).

### `wake_words` (array of strings)
List of keyword strings checked to trigger conversational listening.
- Default: `["jarvis", "hey jarvis"]`.

### `volume_threshold` (float)
Root-mean-square (RMS) microphone sound level required to detect voice activity.
- Default: `0.02`.

### `silence_duration_seconds` (float)
Length of trailing silence that triggers recording completion.
- Default: `1.5`.
