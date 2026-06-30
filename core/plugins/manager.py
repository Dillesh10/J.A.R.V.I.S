import os
import sys
import json
import time
import importlib.util
import ast
import contextvars
from typing import Dict, List, Any, Optional
import core.logger as logger
import memory.database as db
from core.plugins.sdk import BasePlugin, PluginContext, PluginLogger, PluginConfig, PluginStorage

loading_plugin_id_var = contextvars.ContextVar("loading_plugin_id", default=None)

# ─── EXCEPTIONS ──────────────────────────────────────────────────────────────

class PluginError(Exception):
    """Base class for all plugin-related errors."""
    pass

class ManifestValidationError(PluginError):
    """Raised when plugin manifest structure is invalid."""
    pass

class UnsupportedPluginAPIVersionError(ManifestValidationError):
    """Raised when plugin targets an unsupported API version."""
    pass

class DependencyResolutionError(PluginError):
    """Base class for dependency-related issues."""
    pass

class CircularDependencyError(DependencyResolutionError):
    """Raised when circular dependencies are detected."""
    pass

class MissingDependencyError(DependencyResolutionError):
    """Raised when required dependencies are missing."""
    pass

class VersionConflictError(DependencyResolutionError):
    """Raised when dependencies have conflicting version requirements."""
    pass

class PluginSecurityVisitor(ast.NodeVisitor):
    def __init__(self, permissions: List[str]):
        self.permissions = permissions
        self.errors = []

    def visit_Import(self, node):
        for alias in node.names:
            self._check_module(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self._check_module(node.module)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in ["eval", "exec"]:
                self.errors.append(f"Use of forbidden builtin function: '{node.func.id}'")
        self.generic_visit(node)

    def _check_module(self, name: str):
        base_name = name.split('.')[0]
        if name == "ctypes":
            self.errors.append("Direct ctypes import is forbidden in sandboxed plugins.")
        if base_name == "subprocess" and "execute_command" not in self.permissions:
            self.errors.append("Direct subprocess import is forbidden without 'execute_command' permission.")
        if base_name in ["sqlite3", "psycopg2", "mysql", "sqlalchemy"]:
            self.errors.append(f"Direct database module '{base_name}' import is forbidden. Plugins must use the provided SDK.")
        if name.startswith("memory.database"):
            self.errors.append("Importing 'memory.database' is forbidden. Plugins must use the SDK.")
        if base_name in ["socket", "requests", "urllib", "http", "aiohttp", "urllib3"]:
            if "web_search" not in self.permissions and "execute_command" not in self.permissions:
                self.errors.append(f"Network access module '{base_name}' is forbidden without 'web_search' or 'execute_command' permission.")


# ─── PLUGIN MANAGER ──────────────────────────────────────────────────────────

class PluginManager:
    SUPPORTED_API_VERSIONS = ["v1"]

    def __init__(self, plugins_dir: Optional[str] = None):
        if plugins_dir is None:
            # Default plugins folder in workspace root
            core_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            workspace_root = os.path.dirname(core_dir)
            self.plugins_dir = os.path.join(workspace_root, "plugins")
        else:
            self.plugins_dir = plugins_dir
            
        self.loaded_plugins: Dict[str, BasePlugin] = {}
        self.plugin_manifests: Dict[str, Dict[str, Any]] = {}
        self.plugin_paths: Dict[str, str] = {}

    def verify_plugin_code_safety(self, folder_path: str, manifest: Dict[str, Any]):
        """Statically analyzes python files in plugin folder to enforce security sandboxing."""
        permissions = manifest.get("permissions_requested", [])
        visitor = PluginSecurityVisitor(permissions)

        for root, _, files in os.walk(folder_path):
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    tree = ast.parse(code, filename=file_path)
                    visitor.visit(tree)
                except SyntaxError as se:
                    raise PluginError(f"Syntax error in plugin file {file}: {se}")
                except Exception as e:
                    raise PluginError(f"Failed to parse security AST for {file}: {e}")

        if visitor.errors:
            error_msg = "; ".join(visitor.errors)
            raise PluginError(f"Security Sandbox Violation: {error_msg}")

    def discover_plugins(self) -> Dict[str, Dict[str, Any]]:
        """Scans the plugins directory and reads all manifests."""
        if not os.path.exists(self.plugins_dir):
            try:
                os.makedirs(self.plugins_dir, exist_ok=True)
            except Exception:
                pass
            return {}

        self.plugin_manifests.clear()
        self.plugin_paths.clear()

        for folder in os.listdir(self.plugins_dir):
            folder_path = os.path.join(self.plugins_dir, folder)
            if not os.path.isdir(folder_path):
                continue

            manifest_path = os.path.join(folder_path, "manifest.json")
            if not os.path.exists(manifest_path):
                continue

            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                
                plugin_id = manifest.get("id")
                if not plugin_id:
                    logger.log(f"[PluginManager] Skipping folder {folder}: missing 'id' in manifest.", category="SYSTEM")
                    continue

                self.plugin_manifests[plugin_id] = manifest
                self.plugin_paths[plugin_id] = folder_path
            except Exception as e:
                logger.log(f"[PluginManager] Failed to read manifest in {folder}: {e}", category="SYSTEM")

        return self.plugin_manifests

    def validate_manifest(self, manifest: Dict[str, Any]) -> bool:
        """Validates manifest requirements, platform support, and API version compatibility."""
        required_fields = ["id", "name", "version", "api_version", "entry_point"]
        for field in required_fields:
            if not manifest.get(field):
                raise ManifestValidationError(f"Plugin manifest missing required field: '{field}'")

        # 1. API Version Compatibility Check
        api_version = manifest.get("api_version")
        if api_version not in self.SUPPORTED_API_VERSIONS:
            report = f"Plugin targets API version '{api_version}' but J.A.R.V.I.S. Core only supports: {self.SUPPORTED_API_VERSIONS}"
            raise UnsupportedPluginAPIVersionError(report)

        # 2. Platform Compatibility Check
        supported_platforms = manifest.get("supported_platforms")
        if supported_platforms:
            current_platform = sys.platform.lower()
            # Normalize common names
            if "win" in current_platform:
                current_platform = "windows"
            elif "linux" in current_platform:
                current_platform = "linux"
            elif "darwin" in current_platform:
                current_platform = "mac"

            # Check if current platform matches
            is_compatible = False
            for plat in supported_platforms:
                if plat.lower() in current_platform or current_platform in plat.lower():
                    is_compatible = True
                    break
            if not is_compatible:
                raise ManifestValidationError(f"Plugin is incompatible with current platform '{sys.platform}'. Supported: {supported_platforms}")

        return True

    def resolve_dependencies(self) -> List[str]:
        """Resolves dependencies, circular deps, and version conflicts, returning top-sorted loading order."""
        # 1. Parse versions helper
        def parse_version(v_str: str) -> tuple:
            import re
            return tuple(int(x) for x in re.findall(r"\d+", v_str))

        # 2. Build DAG adjacency list
        adj_list: Dict[str, List[str]] = {p_id: [] for p_id in self.plugin_manifests}
        in_degree: Dict[str, int] = {p_id: 0 for p_id in self.plugin_manifests}

        for p_id, manifest in self.plugin_manifests.items():
            deps = manifest.get("dependencies", {})
            
            # Standardize list vs dictionary dependency definitions
            dep_dict = {}
            if isinstance(deps, list):
                dep_dict = {d_id: "" for d_id in deps}
            elif isinstance(deps, dict):
                dep_dict = deps

            for dep_id, ver_req in dep_dict.items():
                if dep_id not in self.plugin_manifests:
                    raise MissingDependencyError(f"Plugin '{p_id}' requires dependency '{dep_id}' which is not installed.")
                
                # Check version conflict if B specifies version constraint
                if ver_req:
                    dep_manifest = self.plugin_manifests[dep_id]
                    dep_ver = dep_manifest.get("version", "0.0.0")
                    if ver_req.startswith(">="):
                        min_ver = ver_req.replace(">=", "").strip()
                        if parse_version(dep_ver) < parse_version(min_ver):
                            raise VersionConflictError(f"Plugin '{p_id}' requires '{dep_id}' version {ver_req}, but installed version is '{dep_ver}'.")
                    elif ver_req.startswith("=="):
                        exact_ver = ver_req.replace("==", "").strip()
                        if parse_version(dep_ver) != parse_version(exact_ver):
                            raise VersionConflictError(f"Plugin '{p_id}' requires '{dep_id}' version {ver_req}, but installed version is '{dep_ver}'.")

                # Edge goes from dep_id -> p_id (dep_id must load before p_id)
                adj_list[dep_id].append(p_id)
                in_degree[p_id] += 1

        # 3. Topological Sort (Kahn's Algorithm)
        queue = [p_id for p_id, deg in in_degree.items() if deg == 0]
        queue.sort() # lexicographical determinism
        order = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)

            for neighbor in adj_list.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            queue.sort()

        if len(order) != len(self.plugin_manifests):
            raise CircularDependencyError("Circular dependency detected between plugins.")

        return order

    def load_plugin(self, plugin_id: str) -> bool:
        """Loads a plugin into memory and invokes setup lifecycle hooks."""
        if plugin_id in self.loaded_plugins:
            return True

        folder_path = self.plugin_paths.get(plugin_id)
        manifest = self.plugin_manifests.get(plugin_id)
        if not folder_path or not manifest:
            logger.log(f"[PluginManager] Cannot load plugin '{plugin_id}': not discovered.", category="SYSTEM")
            return False

        start_time = time.time()
        try:
            # 1. Validate manifest
            self.validate_manifest(manifest)

            # Enforce security sandbox via AST static analysis
            self.verify_plugin_code_safety(folder_path, manifest)

            # 2. Dynamic module import from path
            entry_point = manifest.get("entry_point", "plugin.py")
            entry_file = os.path.join(folder_path, entry_point)
            if not os.path.exists(entry_file):
                raise PluginError(f"Entry point file '{entry_point}' not found in plugin path '{folder_path}'.")

            # Load module under unique namespace
            module_name = f"plugins_{plugin_id}_{int(start_time)}"
            spec = importlib.util.spec_from_file_location(module_name, entry_file)
            if not spec or not spec.loader:
                raise PluginError(f"Could not load spec for module {entry_file}")
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 3. Search for BasePlugin subclass in module
            plugin_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin_class = obj
                    break

            if not plugin_class:
                raise PluginError("No subclass of 'BasePlugin' found in entry point module.")

            # 4. Instantiate Developer SDK Context variables
            config_path = os.path.join(folder_path, "config.json")
            storage_path = os.path.join(folder_path, "storage.json")
            
            p_config = PluginConfig(config_path, manifest.get("default_configuration", {}))
            p_storage = PluginStorage(storage_path)
            p_logger = PluginLogger(plugin_id)
            
            p_context = PluginContext(plugin_id, manifest, p_config, p_storage, p_logger)
            
            # 5. Instantiate and trigger lifecycle hooks
            plugin_instance = plugin_class(p_context)
            
            # Determine if this is a first-time install
            db_entry = db.get_plugin(plugin_id)
            is_new_install = (db_entry is None)
            
            token = loading_plugin_id_var.set(plugin_id)
            try:
                if is_new_install:
                    plugin_instance.on_install()
                    logger.log(f"[PluginManager] Executed on_install() for plugin '{plugin_id}'.", category="SYSTEM")
                elif db_entry.get("version") != manifest.get("version"):
                    plugin_instance.on_update()
                    logger.log(f"[PluginManager] Executed on_update() for plugin '{plugin_id}' (migrated {db_entry['version']} -> {manifest['version']}).", category="SYSTEM")

                # Check dynamic enabled/disabled setting from DB, default to enabled if new
                should_enable = True
                if not is_new_install:
                    should_enable = (db_entry["status"] == "ENABLED")

                load_time = time.time() - start_time

                if should_enable:
                    plugin_instance.on_enable()
                    plugin_instance.enabled = True
                    db_status = "ENABLED"
                    logger.log(f"[PluginManager] Loaded & Enabled plugin '{plugin_id}' successfully in {load_time:.3f}s.", category="SYSTEM")
                else:
                    db_status = "DISABLED"
                    logger.log(f"[PluginManager] Loaded (but Kept Disabled) plugin '{plugin_id}'.", category="SYSTEM")
            finally:
                loading_plugin_id_var.reset(token)

            # Update DB Registry
            db.register_plugin(
                plugin_id=plugin_id,
                name=manifest["name"],
                version=manifest["version"],
                api_version=manifest["api_version"],
                status=db_status,
                load_time=load_time,
                error_message=None,
                manifest=json.dumps(manifest)
            )

            self.loaded_plugins[plugin_id] = plugin_instance
            return True

        except Exception as e:
            load_time = time.time() - start_time
            logger.log(f"[PluginManager] Failed to load plugin '{plugin_id}': {e}", category="SYSTEM")
            # Log error in DB
            db.register_plugin(
                plugin_id=plugin_id,
                name=manifest.get("name", plugin_id),
                version=manifest.get("version", "0.0.0"),
                api_version=manifest.get("api_version", "unknown"),
                status="ERROR",
                load_time=load_time,
                error_message=str(e),
                manifest=json.dumps(manifest) if manifest else "{}"
            )
            return False

    def unload_plugin(self, plugin_id: str) -> bool:
        """Disables and unloads a plugin from active memory."""
        plugin = self.loaded_plugins.get(plugin_id)
        if not plugin:
            return True

        try:
            token = loading_plugin_id_var.set(plugin_id)
            try:
                if plugin.enabled:
                    plugin.on_disable()
                    plugin.enabled = False
                
                plugin.on_shutdown()
            finally:
                loading_plugin_id_var.reset(token)
            logger.log(f"[PluginManager] Executed on_shutdown() for plugin '{plugin_id}'.", category="SYSTEM")
            
            # Remove from loaded set
            del self.loaded_plugins[plugin_id]
            
            # Force module cleanup in sys.path and sys.modules
            module_name = plugin.__class__.__module__
            if module_name in sys.modules:
                del sys.modules[module_name]

            # Update DB registry (keep status as is, just clear memory reference)
            db_entry = db.get_plugin(plugin_id)
            if db_entry:
                db.update_plugin_status(plugin_id, db_entry["status"], None)

            logger.log(f"[PluginManager] Unloaded plugin '{plugin_id}' from memory.", category="SYSTEM")
            return True
        except Exception as e:
            logger.log(f"[PluginManager] Failed to clean up plugin '{plugin_id}' during unload: {e}", category="SYSTEM")
            db.update_plugin_status(plugin_id, "ERROR", str(e))
            return False

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enables a loaded but disabled plugin."""
        plugin = self.loaded_plugins.get(plugin_id)
        if not plugin:
            # If not in memory, try loading it
            return self.load_plugin(plugin_id)

        if plugin.enabled:
            return True

        try:
            token = loading_plugin_id_var.set(plugin_id)
            try:
                plugin.on_enable()
                plugin.enabled = True
            finally:
                loading_plugin_id_var.reset(token)
            db.update_plugin_status(plugin_id, "ENABLED", None)
            logger.log(f"[PluginManager] Enabled plugin '{plugin_id}'.", category="SYSTEM")
            return True
        except Exception as e:
            logger.log(f"[PluginManager] Failed to enable plugin '{plugin_id}': {e}", category="SYSTEM")
            db.update_plugin_status(plugin_id, "ERROR", str(e))
            return False

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disables an active plugin, unregistering its contributed assets."""
        plugin = self.loaded_plugins.get(plugin_id)
        if not plugin:
            return True

        if not plugin.enabled:
            return True

        try:
            token = loading_plugin_id_var.set(plugin_id)
            try:
                plugin.on_disable()
                plugin.enabled = False
            finally:
                loading_plugin_id_var.reset(token)
            db.update_plugin_status(plugin_id, "DISABLED", None)
            logger.log(f"[PluginManager] Disabled plugin '{plugin_id}'.", category="SYSTEM")
            return True
        except Exception as e:
            logger.log(f"[PluginManager] Failed to disable plugin '{plugin_id}': {e}", category="SYSTEM")
            db.update_plugin_status(plugin_id, "ERROR", str(e))
            return False

    def load_all_plugins(self) -> List[str]:
        """Discovers, validates dependencies, and loads all plugins topologically."""
        self.discover_plugins()
        loaded = []
        try:
            order = self.resolve_dependencies()
            for p_id in order:
                if self.load_plugin(p_id):
                    loaded.append(p_id)
        except DependencyResolutionError as de:
            logger.log(f"[PluginManager] Dependency resolution failure: {de}", category="SYSTEM")
        return loaded

    def shutdown_all_plugins(self):
        """Cleanly unloads all active plugins on core shutdown."""
        # Copy keys to avoid mutation during loop
        active_ids = list(self.loaded_plugins.keys())
        for p_id in active_ids:
            self.unload_plugin(p_id)

plugin_manager = PluginManager()
