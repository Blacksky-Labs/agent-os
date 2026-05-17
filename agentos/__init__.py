"""AgentOS — the foundation infrastructure for the Blacksky agent fleet.

Public API. See SPEC.md for the specification.
"""

from agentos.config import ManifestError, load_manifest
from agentos.context import AgentContext
from agentos.hooks import EVENT_TYPES, HookDispatcher
from agentos.observability import log_event
from agentos.pipeline import Pipeline
from agentos.registry import Registry

__version__ = "0.1.0"

__all__ = [
    "AgentContext",
    "EVENT_TYPES",
    "HookDispatcher",
    "ManifestError",
    "Pipeline",
    "Registry",
    "load_manifest",
    "log_event",
    "__version__",
]
