"""
FastAPI dependencies for workspace-aware LightRAG instances
"""

from typing import Optional, TYPE_CHECKING
from fastapi import Request, HTTPException, Header

from lightrag import LightRAG
from lightrag.utils import logger

if TYPE_CHECKING:
    from lightrag.api.workspace_manager import WorkspaceManager


async def get_rag_instance(
    request: Request,
    x_workspace: Optional[str] = Header(None, description="Target workspace for the operation. Uses server default if not provided.")
) -> tuple[LightRAG, any]:
    """
    FastAPI dependency function to get LightRAG and DocumentManager instances for a workspace.

    This function extracts the workspace from the X-Workspace header and returns the appropriate
    LightRAG and DocumentManager instances. Falls back to the default workspace if no header is provided.

    Args:
        request: FastAPI request object containing app state
        x_workspace: Optional workspace name from X-Workspace header

    Returns:
        tuple: (LightRAG instance, DocumentManager instance)

    Raises:
        HTTPException: If workspace is invalid or instances cannot be created
    """
    try:
        # Get the workspace manager from app state
        workspace_manager = request.app.state.workspace_manager

        # Log the workspace request for debugging
        if x_workspace:
            logger.debug(f"Request for workspace: {x_workspace}")
        else:
            logger.debug(f"Request for default workspace: {workspace_manager.get_default_workspace()}")

        # Get or create instances for the workspace
        rag_instance, doc_manager = await workspace_manager.get_or_create(x_workspace)

        return rag_instance, doc_manager

    except ValueError as e:
        # Handle invalid workspace names
        logger.warning(f"Invalid workspace request: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid workspace: {str(e)}"
        )
    except Exception as e:
        # Handle other errors
        logger.error(f"Error getting RAG instance for workspace '{x_workspace}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get RAG instance: {str(e)}"
        )


async def get_rag_only(
    request: Request,
    x_workspace: Optional[str] = Header(None, description="Target workspace for the operation. Uses server default if not provided.")
) -> LightRAG:
    """
    FastAPI dependency function to get only the LightRAG instance for a workspace.

    Args:
        request: FastAPI request object containing app state
        x_workspace: Optional workspace name from X-Workspace header

    Returns:
        LightRAG: LightRAG instance for the workspace

    Raises:
        HTTPException: If workspace is invalid or instance cannot be created
    """
    rag_instance, _ = await get_rag_instance(request, x_workspace)
    return rag_instance


async def get_doc_manager_only(
    request: Request,
    x_workspace: Optional[str] = Header(None, description="Target workspace for the operation. Uses server default if not provided.")
) -> any:
    """
    FastAPI dependency function to get only the DocumentManager instance for a workspace.

    Args:
        request: FastAPI request object containing app state
        x_workspace: Optional workspace name from X-Workspace header

    Returns:
        DocumentManager: DocumentManager instance for the workspace

    Raises:
        HTTPException: If workspace is invalid or instance cannot be created
    """
    _, doc_manager = await get_rag_instance(request, x_workspace)
    return doc_manager