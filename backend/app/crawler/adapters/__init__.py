"""
Adapter registry for site-specific extraction rules.

Import ``DEFAULT_REGISTRY`` for a pre-built registry containing all bundled
adapters, or build your own with ``AdapterRegistry([MyAdapter(), ...])``.
"""
from .base import AdapterRegistry, BaseSiteAdapter
from .bbc import BBCAdapter
from .cnn import CNNAdapter
from .medium import MediumAdapter

# All bundled adapters — add new ones here
_BUNDLED: list[BaseSiteAdapter] = [
    BBCAdapter(),
    CNNAdapter(),
    MediumAdapter(),
]

DEFAULT_REGISTRY = AdapterRegistry(_BUNDLED)

__all__ = [
    "BaseSiteAdapter",
    "AdapterRegistry",
    "DEFAULT_REGISTRY",
    "BBCAdapter",
    "CNNAdapter",
    "MediumAdapter",
]
