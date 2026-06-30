import os
import sys
import json
import unittest
import tempfile
import uuid
from unittest.mock import patch, MagicMock

# Add parent directory to path so core/ memory/ can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plugins.sdk import BasePlugin, PluginContext, PluginLogger, PluginConfig, PluginStorage
from core.plugins.manager import (
    PluginManager,
    PluginError,
    ManifestValidationError,
    UnsupportedPluginAPIVersionError,
    DependencyResolutionError,
    CircularDependencyError,
    MissingDependencyError,
    VersionConflictError
)
from core.plugins.registry import extension_registry, WorkflowTemplate
from tools.registry import tool_registry
from core.router import JarvisRouter
from core.planner import TaskDecomposer, Task
import memory.database as db

class TestPlugins(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = PluginManager(plugins_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_plugin_on_disk(self, plugin_id: str, manifest: dict, entry_code: str = ""):
        plugin_folder = os.path.join(self.temp_dir.name, plugin_id)
        os.makedirs(plugin_folder, exist_ok=True)
        
        with open(os.path.join(plugin_folder, "manifest.json"), "w") as f:
            json.dump(manifest, f)
            
        entry_file = manifest.get("entry_point", "plugin.py")
        if not entry_code:
            entry_code = f"""
from core.plugins.sdk import BasePlugin

class Plugin(BasePlugin):
    def on_enable(self):
        self.context.logger.log("Plugin {plugin_id} enabled.")
"""
        with open(os.path.join(plugin_folder, entry_file), "w") as f:
            f.write(entry_code)

        return plugin_folder

    def test_manifest_validation_success(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py"
        }
        self.assertTrue(self.manager.validate_manifest(manifest))

    def test_manifest_validation_missing_fields(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "1.0.0"
            # Missing api_version and entry_point
        }
        with self.assertRaises(ManifestValidationError):
            self.manager.validate_manifest(manifest)

    def test_manifest_validation_api_compatibility(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "api_version": "v2", # Unsupported version
            "entry_point": "plugin.py"
        }
        with self.assertRaises(UnsupportedPluginAPIVersionError) as ctx:
            self.manager.validate_manifest(manifest)
        self.assertIn("targets API version 'v2'", str(ctx.exception))

    def test_manifest_validation_platform_incompatibility(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py",
            "supported_platforms": ["incompatible_os_xyz"]
        }
        with self.assertRaises(ManifestValidationError):
            self.manager.validate_manifest(manifest)

    def test_dependency_resolution_topo_sort(self):
        # A depends on B. B depends on C.
        self.manager.plugin_manifests = {
            "A": {"id": "A", "dependencies": ["B"]},
            "B": {"id": "B", "dependencies": {"C": ">=1.0.0"}},
            "C": {"id": "C", "version": "1.0.0"}
        }
        order = self.manager.resolve_dependencies()
        self.assertEqual(order, ["C", "B", "A"])

    def test_dependency_resolution_missing(self):
        self.manager.plugin_manifests = {
            "A": {"id": "A", "dependencies": ["B"]}
        }
        with self.assertRaises(MissingDependencyError):
            self.manager.resolve_dependencies()

    def test_dependency_resolution_circular(self):
        self.manager.plugin_manifests = {
            "A": {"id": "A", "dependencies": ["B"]},
            "B": {"id": "B", "dependencies": ["A"]}
        }
        with self.assertRaises(CircularDependencyError):
            self.manager.resolve_dependencies()

    def test_dependency_resolution_version_conflict(self):
        self.manager.plugin_manifests = {
            "A": {"id": "A", "dependencies": {"B": ">=2.0.0"}},
            "B": {"id": "B", "version": "1.5.0"}
        }
        with self.assertRaises(VersionConflictError):
            self.manager.resolve_dependencies()

    def test_plugin_config_and_storage(self):
        folder = os.path.join(self.temp_dir.name, "config_test")
        os.makedirs(folder, exist_ok=True)
        config_path = os.path.join(folder, "config.json")
        storage_path = os.path.join(folder, "storage.json")

        # Test Config
        config = PluginConfig(config_path, {"default_port": 8080})
        self.assertEqual(config.get("default_port"), 8080)
        config.set("default_port", 9090)
        self.assertEqual(config.get("default_port"), 9090)
        
        # Load from disk again to check persistence
        config2 = PluginConfig(config_path, {"default_port": 8080})
        self.assertEqual(config2.get("default_port"), 9090)

        # Test Storage
        storage = PluginStorage(storage_path)
        storage.set("token", "secret123")
        self.assertEqual(storage.get("token"), "secret123")
        
        storage2 = PluginStorage(storage_path)
        self.assertEqual(storage2.get("token"), "secret123")
        storage2.delete("token")
        self.assertIsNone(storage2.get("token"))

    def test_plugin_manager_lifecycle(self):
        plugin_id = f"test_lifecycle_{uuid.uuid4().hex[:8]}"
        manifest = {
            "id": plugin_id,
            "name": "Lifecycle Test Plugin",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py"
        }
        
        entry_code = f"""
from core.plugins.sdk import BasePlugin

class Plugin(BasePlugin):
    def __init__(self, context):
        super().__init__(context)
        self.history = []

    def on_install(self):
        self.history.append("installed")

    def on_enable(self):
        self.history.append("enabled")

    def on_disable(self):
        self.history.append("disabled")

    def on_shutdown(self):
        self.history.append("shutdown")
"""
        self.create_plugin_on_disk(plugin_id, manifest, entry_code)
        
        # Discover and Load
        self.manager.discover_plugins()
        self.manager.load_plugin(plugin_id)
        
        self.assertIn(plugin_id, self.manager.loaded_plugins)
        plugin_inst = self.manager.loaded_plugins[plugin_id]
        
        self.assertTrue(plugin_inst.enabled)
        self.assertEqual(plugin_inst.history, ["installed", "enabled"])

        # Check DB Entry
        db_entry = db.get_plugin(plugin_id)
        self.assertIsNotNone(db_entry)
        self.assertEqual(db_entry["status"], "ENABLED")

        # Disable
        self.manager.disable_plugin(plugin_id)
        self.assertFalse(plugin_inst.enabled)
        self.assertEqual(plugin_inst.history, ["installed", "enabled", "disabled"])
        
        db_entry = db.get_plugin(plugin_id)
        self.assertEqual(db_entry["status"], "DISABLED")

        # Enable
        self.manager.enable_plugin(plugin_id)
        self.assertTrue(plugin_inst.enabled)
        self.assertEqual(plugin_inst.history, ["installed", "enabled", "disabled", "enabled"])

        # Unload
        self.manager.unload_plugin(plugin_id)
        self.assertNotIn(plugin_id, self.manager.loaded_plugins)
        self.assertEqual(plugin_inst.history, ["installed", "enabled", "disabled", "enabled", "disabled", "shutdown"])

    def test_plugin_extension_points(self):
        plugin_id = f"test_ext_{uuid.uuid4().hex[:8]}"
        manifest = {
            "id": plugin_id,
            "name": "Extension Test Plugin",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py"
        }
        
        entry_code = f"""
from core.plugins.sdk import BasePlugin
from tools.base import BaseTool
from core.plugins.registry import extension_registry, WorkflowTemplate

class PluginTool(BaseTool):
    name: str = "plugin_custom_tool"
    description: str = "A custom tool contributed by a plugin"

    def execute(self) -> str:
        return "custom_tool_success"

class DummyAgent:
    description = "A dummy custom agent"
    def process_message(self, msg, sid):
        return "agent_processed"

class Plugin(BasePlugin):
    def on_enable(self):
        # 1. Register tool
        from tools.registry import tool_registry
        self.tool = PluginTool()
        tool_registry.register(self.tool)

        # 2. Register agent
        self.agent = DummyAgent()
        extension_registry.register_agent("DummyAgent", self.agent)

        # 3. Register template
        self.template = WorkflowTemplate(
            name="DummyTemplate",
            pattern="run dummy workflow",
            tasks=[{{
                "id": "t1",
                "description": "Run custom plugin tool",
                "assigned_agent": "DummyAgent",
                "assigned_tool": "plugin_custom_tool",
                "args": {{}}
            }}]
        )
        extension_registry.register_workflow_template(self.template)

    def on_disable(self):
        from tools.registry import tool_registry
        tool_registry.unregister(self.tool.name)
        extension_registry.unregister_agent("DummyAgent")
        extension_registry.unregister_workflow_template("DummyTemplate")
"""
        self.create_plugin_on_disk(plugin_id, manifest, entry_code)
        
        self.manager.discover_plugins()
        self.manager.load_plugin(plugin_id)

        # 1. Tool verification
        tool = tool_registry.get_tool("plugin_custom_tool")
        self.assertIsNotNone(tool)
        
        # 2. Agent verification in Router
        router = JarvisRouter()
        self.assertIn("DummyAgent", router.all_agents)
        self.assertIn("DummyAgent", router.get_routing_prompt())

        # 3. Workflow template resolution in Planner Decomposer
        brain = MagicMock()
        decomposer = TaskDecomposer(brain)
        tasks = decomposer.decompose("run dummy workflow")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "t1")
        self.assertEqual(tasks[0].assigned_tool, "plugin_custom_tool")

        # Disable plugin and verify clean removal
        self.manager.disable_plugin(plugin_id)
        
        with self.assertRaises(Exception):
            tool_registry.get_tool("plugin_custom_tool")
        self.assertNotIn("DummyAgent", router.all_agents)
        self.assertIsNone(extension_registry.get_matching_workflow_template("run dummy workflow"))

    def test_sandbox_ast_forbidden_import(self):
        plugin_id = f"test_sandbox_import_{uuid.uuid4().hex[:8]}"
        manifest = {
            "id": plugin_id,
            "name": "Sandbox Import Test",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py",
            "permissions_requested": []
        }
        entry_code = """
import subprocess
from core.plugins.sdk import BasePlugin

class Plugin(BasePlugin):
    def on_enable(self):
        pass
"""
        self.create_plugin_on_disk(plugin_id, manifest, entry_code)
        self.manager.discover_plugins()
        self.assertFalse(self.manager.load_plugin(plugin_id))
        db_entry = db.get_plugin(plugin_id)
        self.assertEqual(db_entry["status"], "ERROR")
        self.assertIn("Security Sandbox Violation", db_entry["error_message"])

    def test_sandbox_ast_forbidden_eval(self):
        plugin_id = f"test_sandbox_eval_{uuid.uuid4().hex[:8]}"
        manifest = {
            "id": plugin_id,
            "name": "Sandbox Eval Test",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py"
        }
        entry_code = """
from core.plugins.sdk import BasePlugin

class Plugin(BasePlugin):
    def on_enable(self):
        eval("print('hello')")
"""
        self.create_plugin_on_disk(plugin_id, manifest, entry_code)
        self.manager.discover_plugins()
        self.assertFalse(self.manager.load_plugin(plugin_id))
        db_entry = db.get_plugin(plugin_id)
        self.assertIn("forbidden builtin function", db_entry["error_message"])

    def test_runtime_permission_enforcement(self):
        plugin_id = f"test_runtime_sec_{uuid.uuid4().hex[:8]}"
        manifest = {
            "id": plugin_id,
            "name": "Runtime Security Test",
            "version": "1.0.0",
            "api_version": "v1",
            "entry_point": "plugin.py",
            "permissions_requested": ["read_file"]
        }
        entry_code = f"""
from core.plugins.sdk import BasePlugin
from tools.base import BaseTool

class DummyPluginTool(BaseTool):
    name: str = "dummy_plugin_tool_{plugin_id}"
    description: str = "A dummy tool trying to execute unauthorized actions"

    def execute(self) -> str:
        from tools.registry import tool_registry
        return tool_registry.get_tool("execute_command").execute(command="dir")

class Plugin(BasePlugin):
    def on_enable(self):
        from tools.registry import tool_registry
        self.tool = DummyPluginTool()
        tool_registry.register(self.tool)

    def on_disable(self):
        from tools.registry import tool_registry
        tool_registry.unregister(self.tool.name)
"""
        with patch("core.plugins.manager.plugin_manager", self.manager):
            self.create_plugin_on_disk(plugin_id, manifest, entry_code)
            self.manager.discover_plugins()
            self.assertTrue(self.manager.load_plugin(plugin_id))

            from tools.registry import tool_registry
            from core.security import PermissionDeniedError
            
            tool = tool_registry.get_tool(f"dummy_plugin_tool_{plugin_id}")
            with self.assertRaises(PermissionDeniedError):
                tool.execute()

            self.manager.disable_plugin(plugin_id)

if __name__ == "__main__":
    unittest.main()
