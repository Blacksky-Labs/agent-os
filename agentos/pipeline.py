"""Cell pipeline executor.

Loads cells from the registry, runs them in sequence against an
AgentContext. A failure in any cell is recorded but does not crash
the pipeline.

See SPEC.md §4 (cell contract) and §5 (cell library).
"""

from __future__ import annotations

import importlib
import time
from typing import Any

from agentos.context import AgentContext
from agentos.observability import log_event
from agentos.registry import Registry


class Pipeline:
    """The ordered sequence of cells for one agent."""

    def __init__(self, manifest: dict, cell_registry: Registry):
        self.agent_name: str = manifest["name"]
        self.namespace: str = manifest["namespace"]
        self.manifest: dict = manifest
        self.registry: Registry = cell_registry
        self.cells: list[Any] = self._load_cells()

    def _load_cells(self) -> list:
        loaded: list = []
        for cell_entry in self.manifest.get("cells", []) or []:
            name = cell_entry["name"]
            version = cell_entry.get("version", "latest")
            config = cell_entry.get("config", {}) or {}

            module_path = self.registry.resolve(name, version)
            module = importlib.import_module(module_path)
            if not hasattr(module, "Cell"):
                raise RuntimeError(
                    f"Module '{module_path}' has no `Cell` class. "
                    "Every cell must expose `class Cell` (SPEC §4)."
                )
            cell = module.Cell(config)
            cell.init(config)
            loaded.append(cell)
            log_event(
                kind="kernel",
                namespace=self.namespace,
                turn_id="-",
                event="cell_loaded",
                cell=name,
                version=version,
            )
        return loaded

    async def run(self, context: AgentContext) -> AgentContext:
        """Execute the pipeline against an AgentContext.

        Errors in any cell are caught, recorded on ``context.cell_errors``,
        and logged. The pipeline continues to the next cell.
        """
        for cell in self.cells:
            start = time.time()
            try:
                context = await cell.execute(context)
                duration_ms = int((time.time() - start) * 1000)
                context.cell_timings[cell.name] = duration_ms
                log_event(
                    kind="cell",
                    namespace=context.namespace,
                    turn_id=context.turn_id,
                    cell=cell.name,
                    version=cell.version,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                context.cell_errors[cell.name] = str(e)
                log_event(
                    kind="cell",
                    namespace=context.namespace,
                    turn_id=context.turn_id,
                    cell=cell.name,
                    version=getattr(cell, "version", "?"),
                    duration_ms=duration_ms,
                    error=str(e),
                )
        return context

    async def teardown(self) -> None:
        for cell in self.cells:
            try:
                await cell.teardown()
            except Exception as e:
                log_event(
                    kind="kernel",
                    namespace=self.namespace,
                    turn_id="-",
                    event="cell_teardown_error",
                    cell=getattr(cell, "name", "?"),
                    error=str(e),
                )
