from typing import Dict, List
from core.providers.base import BaseProvider

class ProviderRegistry:
    """Central registry holding instantiated BaseProvider instances."""
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        """Enrolls a provider class into the registry."""
        self._providers[name.lower().strip()] = provider

    def get(self, name: str) -> BaseProvider:
        """Retrieves a provider by its name, raising ValueError if not found."""
        p_name = name.lower().strip()
        if p_name not in self._providers:
            raise ValueError(f"Provider '{name}' is not registered.")
        return self._providers[p_name]

    def list_providers(self) -> List[str]:
        """Lists all registered provider identifiers."""
        return list(self._providers.keys())

# Global single-instance provider registry
provider_registry = ProviderRegistry()
