import re
from typing import Dict, List, Any, Optional
import core.logger as logger

class WorkflowTemplate:
    def __init__(self, name: str, pattern: str, tasks: List[Dict[str, Any]]):
        self.name = name
        self.pattern = pattern
        self.tasks = tasks  # list of task parameters suitable for Task constructor


class ExtensionRegistry:
    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._workflow_templates: List[WorkflowTemplate] = []
        
        # Future extension points (defined as interfaces / hooks)
        self._ai_providers: Dict[str, Any] = {}
        self._vision_modules: Dict[str, Any] = {}
        self._voice_modules: Dict[str, Any] = {}
        self._notification_channels: Dict[str, Any] = {}

    # Agent Extension Points
    def register_agent(self, name: str, agent_instance):
        try:
            from core.plugins.manager import loading_plugin_id_var
            plugin_id = loading_plugin_id_var.get()
            if plugin_id:
                agent_instance.plugin_id = plugin_id
        except ImportError:
            pass

        original_process_message = getattr(agent_instance, "process_message", None)
        if original_process_message:
            def secure_process_message(*args, **kwargs):
                from core.security import active_plugin_id_var
                plugin_id_exec = getattr(agent_instance, "plugin_id", None)
                token = None
                if plugin_id_exec:
                    token = active_plugin_id_var.set(plugin_id_exec)
                try:
                    return original_process_message(*args, **kwargs)
                finally:
                    if token:
                        active_plugin_id_var.reset(token)
            agent_instance.process_message = secure_process_message

        self._agents[name] = agent_instance
        logger.log(f"[Registry] Dynamic agent '{name}' registered.", category="SYSTEM")

    def unregister_agent(self, name: str):
        if name in self._agents:
            del self._agents[name]
            logger.log(f"[Registry] Dynamic agent '{name}' unregistered.", category="SYSTEM")

    def list_agents(self) -> Dict[str, Any]:
        return self._agents

    # Workflow Template Extension Points
    def register_workflow_template(self, template: WorkflowTemplate):
        self._workflow_templates.append(template)
        logger.log(f"[Registry] Workflow template '{template.name}' registered.", category="SYSTEM")

    def unregister_workflow_template(self, name: str):
        self._workflow_templates = [t for t in self._workflow_templates if t.name != name]
        logger.log(f"[Registry] Workflow template '{name}' unregistered.", category="SYSTEM")

    def get_matching_workflow_template(self, goal: str) -> Optional[WorkflowTemplate]:
        for template in self._workflow_templates:
            if re.search(template.pattern, goal, re.IGNORECASE):
                return template
        return None

    def list_workflow_templates(self) -> List[WorkflowTemplate]:
        return self._workflow_templates

    # AI Providers
    def register_ai_provider(self, name: str, provider_instance):
        self._ai_providers[name] = provider_instance

    def unregister_ai_provider(self, name: str):
        if name in self._ai_providers:
            del self._ai_providers[name]

    # Vision Modules
    def register_vision_module(self, name: str, module_instance):
        self._vision_modules[name] = module_instance

    def unregister_vision_module(self, name: str):
        if name in self._vision_modules:
            del self._vision_modules[name]

    # Voice Modules
    def register_voice_module(self, name: str, module_instance):
        self._voice_modules[name] = module_instance

    def unregister_voice_module(self, name: str):
        if name in self._voice_modules:
            del self._voice_modules[name]

    # Notification Channels
    def register_notification_channel(self, name: str, channel_instance):
        self._notification_channels[name] = channel_instance

    def unregister_notification_channel(self, name: str):
        if name in self._notification_channels:
            del self._notification_channels[name]


# Global Extension Registry instance
extension_registry = ExtensionRegistry()
