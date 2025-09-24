"""FastAPI dependency helpers for multi-workspace support."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from .workspace import WorkspaceContext, WorkspaceManager


async def get_workspace_manager(request: Request) -> WorkspaceManager:
    manager = getattr(request.app.state, "workspace_manager", None)
    if manager is None:
        raise HTTPException(status_code=500, detail="Workspace manager is not configured")
    return manager


async def get_workspace_context(
    request: Request,
    x_workspace: Optional[str] = Header(
        None,
        alias="X-Workspace",
        description="Workspace name used to isolate data. Defaults to the server workspace when omitted.",
    ),
    manager: WorkspaceManager = Depends(get_workspace_manager),
) -> WorkspaceContext:
    try:
        return await manager.get_context(x_workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def get_rag_instance(
    context: WorkspaceContext = Depends(get_workspace_context),
):
    return context.rag


async def get_document_manager(
    context: WorkspaceContext = Depends(get_workspace_context),
):
    return context.doc_manager


async def get_workspace_name(
    context: WorkspaceContext = Depends(get_workspace_context),
):
    return context.workspace
