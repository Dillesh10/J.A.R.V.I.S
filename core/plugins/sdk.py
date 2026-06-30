import os
import json
from typing import Dict, Any, Optional
import core.logger as logger

# ─── PLUGIN EVENT INTERFACES ───────────────────────────────────────────────

class PluginEvents:
    """Interface templates representing event hooks for future Event Bus compatibility."""
    def on_workflow_started(self, workflow_id: str, goal: str):
        pass

    def on_workflow_completed(self, workflow_id: str, status: str):
        pass

    def on_task_started(self, workflow_id: str, task_id: str, tool_name: str):
        pass

    def on_task_completed(self, workflow_id: str, task_id: str, status: str):
        pass

    def on_plugin_loaded(self, plugin_id: str):
        pass

    def on_plugin_unloaded(self, plugin_id: str):
        pass

    def on_permission_granted(self, workflow_id: str, task_id: str, tool_name: str, approval_id: str):
        pass

    def on_permission_denied(self, workflow_id: str, task_id: str, tool_name: str, reason: str):
        pass


# ─── PLUGIN LOGGER ─────────────────────────────────────────────────────────

class PluginLogger:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id

    def log(self, message: str, category: str = "PLUGIN"):
        logger.log(f"[Plugin: {self.plugin_id}] {message}", category=category)


# ─── PLUGIN CONFIGURATION ──────────────────────────────────────────────────

class PluginConfig:
    def __init__(self, config_path: str, default_config: Dict[str, Any]):
        self.config_path = config_path
        self.defaults = default_config
        self.data = default_config.copy()
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    user_data = json.load(f)
                    if isinstance(user_data, dict):
                        self.data.update(user_data)
            except Exception as e:
                logger.log(f"Failed to load plugin config at {self.config_path}: {e}", category="SYSTEM")

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.log(f"Failed to save plugin config at {self.config_path}: {e}", category="SYSTEM")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()


# ─── PLUGIN STORAGE ────────────────────────────────────────────────────────

class PluginStorage:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.log(f"Failed to load plugin storage at {self.storage_path}: {e}", category="SYSTEM")

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.log(f"Failed to save plugin storage at {self.storage_path}: {e}", category="SYSTEM")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()

    def delete(self, key: str):
        if key in self.data:
            del self.data[key]
            self.save()


# ─── PLUGIN CONTEXT ────────────────────────────────────────────────────────

class PluginContext:
    def __init__(self, plugin_id: str, manifest: Dict[str, Any], config: PluginConfig, storage: PluginStorage, logger: PluginLogger):
        self.plugin_id = plugin_id
        self.manifest = manifest
        self.config = config
        self.storage = storage
        self.logger = logger


# ─── BASE PLUGIN CLASS ──────────────────────────────────────────────────────

class BasePlugin(PluginEvents):
    def __init__(self, context: PluginContext):
        self.context = context
        self.enabled = False

    def on_install(self):
        """Called once when plugin is installed."""
        pass

    def on_uninstall(self):
        """Called once when plugin is uninstalled."""
        pass

    def on_enable(self):
        """Called when plugin is enabled."""
        pass

    def on_disable(self):
        """Called when plugin is disabled."""
        pass

    def on_update(self):
        """Called when plugin is updated to a new version."""
        pass

    def on_startup(self):
        """Called during core system startup for all enabled plugins."""
        pass

    def on_shutdown(self):
        """Called during core system shutdown."""
        pass
