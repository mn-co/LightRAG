"""Workspace management utilities for the LightRAG API server."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from lightrag import LightRAG
from lightrag.utils import logger

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from lightrag.api.routers.document_routes import DocumentManager


_WORKSPACE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class WorkspaceContext:
    """Represents the runtime context bound to a workspace."""

    workspace: str
    rag: LightRAG
    doc_manager: "DocumentManager"


class WorkspaceManager:
    """Manage `LightRAG` instances scoped to workspaces."""

    def __init__(
        self,
        *,
        create_rag: Callable[[str], LightRAG],
        create_doc_manager: Callable[[str], "DocumentManager"],
        default_workspace: str = "",
    ) -> None:
        self._create_rag = create_rag
        self._create_doc_manager = create_doc_manager
        self._default_workspace = self._validate_default_workspace(default_workspace)
        self._contexts: Dict[str, WorkspaceContext] = {}
        self._lock = asyncio.Lock()

    @property
    def default_workspace(self) -> str:
        """Return the default workspace name used when none is specified."""

        return self._default_workspace

    def sanitize(self, workspace: Optional[str]) -> str:
        """Return a validated workspace name, falling back to the default."""

        if workspace is None:
            return self._default_workspace

        candidate = workspace.strip()
        if not candidate:
            return self._default_workspace

        if not _WORKSPACE_PATTERN.fullmatch(candidate):
            raise ValueError(
                "Invalid workspace name. Only letters, numbers, hyphen, and underscore are allowed (1-64 chars)."
            )

        return candidate

    async def get_context(self, workspace: Optional[str]) -> WorkspaceContext:
        """Return the context for the given workspace, creating it when needed."""

        target = self.sanitize(workspace)
        context = self._contexts.get(target)
        if context is not None:
            return context

        async with self._lock:
            # Re-check after acquiring the lock to avoid duplicate initialization
            context = self._contexts.get(target)
            if context is not None:
                return context

            rag = self._create_rag(target)
            await rag.initialize_storages()
            await rag.check_and_migrate_data()

            doc_manager = self._create_doc_manager(target)
            context = WorkspaceContext(workspace=target, rag=rag, doc_manager=doc_manager)
            self._contexts[target] = context
            logger.info("Initialized workspace '%s'", target or "<default>")
            return context

    def list_workspaces(self) -> list[str]:
        """Return the list of currently loaded workspaces."""

        return sorted(self._contexts.keys())

    async def shutdown_all(self) -> None:
        """Finalize storages for all managed workspaces."""

        for context in list(self._contexts.values()):
            try:
                await context.rag.finalize_storages()
            except Exception:
                logger.exception(
                    "Failed to finalize storages for workspace '%s'", context.workspace or "<default>"
                )

    def _validate_default_workspace(self, value: str) -> str:
        if not value:
            return ""

        candidate = value.strip()
        if not candidate:
            return ""

        if not _WORKSPACE_PATTERN.fullmatch(candidate):
            raise ValueError(
                "Default workspace contains invalid characters. Use letters, numbers, hyphen, or underscore."
            )

        return candidate
