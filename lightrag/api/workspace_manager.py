"""
WorkspaceManager for managing multiple LightRAG instances with workspace isolation
"""

import re
from typing import Dict, Optional, List
from threading import RLock

from lightrag import LightRAG
from lightrag.api.routers.document_routes import DocumentManager
from lightrag.utils import logger


class WorkspaceManager:
    """
    Thread-safe manager for multiple LightRAG instances with workspace isolation.

    Provides methods to create, cache, and manage LightRAG instances for different workspaces,
    ensuring proper isolation and resource management.
    """

    def __init__(self, default_workspace: str, rag_config: dict, doc_manager_config: dict):
        """
        Initialize WorkspaceManager.

        Args:
            default_workspace: Default workspace name to use when no workspace is specified
            rag_config: Configuration dictionary for creating LightRAG instances
            doc_manager_config: Configuration dictionary for creating DocumentManager instances
        """
        self.default_workspace = default_workspace
        self.rag_config = rag_config
        self.doc_manager_config = doc_manager_config
        self._instances: Dict[str, LightRAG] = {}
        self._doc_managers: Dict[str, DocumentManager] = {}
        self._lock = RLock()

        logger.info(f"WorkspaceManager initialized with default workspace: {default_workspace}")

    @staticmethod
    def validate_workspace_name(workspace: str) -> bool:
        """
        Validate workspace name to prevent directory traversal and ensure security.

        Args:
            workspace: Workspace name to validate

        Returns:
            bool: True if workspace name is valid, False otherwise
        """
        if not workspace:
            return False

        # Allow only alphanumeric characters, underscores, hyphens, and dots
        # Prevent directory traversal patterns
        if not re.match(r'^[a-zA-Z0-9_.-]+$', workspace):
            return False

        # Prevent relative path components
        if '..' in workspace or workspace.startswith('.') or workspace.endswith('.'):
            return False

        # Prevent reserved names
        reserved_names = {'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4',
                         'com5', 'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2',
                         'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'}
        if workspace.lower() in reserved_names:
            return False

        # Check length constraints
        if len(workspace) > 255:
            return False

        return True

    async def get_or_create(self, workspace: Optional[str] = None) -> tuple[LightRAG, DocumentManager]:
        """
        Get or create LightRAG and DocumentManager instances for the specified workspace.

        Args:
            workspace: Target workspace name. Uses default if None.

        Returns:
            tuple: (LightRAG instance, DocumentManager instance)

        Raises:
            ValueError: If workspace name is invalid
        """
        # Use default workspace if none specified
        if workspace is None:
            workspace = self.default_workspace

        # Validate workspace name
        if not self.validate_workspace_name(workspace):
            raise ValueError(f"Invalid workspace name: {workspace}")

        with self._lock:
            # Return existing instances if available
            if workspace in self._instances:
                return self._instances[workspace], self._doc_managers[workspace]

            # Create new instances
            logger.info(f"Creating new LightRAG instance for workspace: {workspace}")

            # Create workspace-specific configuration
            rag_config = self.rag_config.copy()
            rag_config['workspace'] = workspace

            # Create LightRAG instance
            rag_instance = LightRAG(**rag_config)

            # Initialize storages for the new instance
            await rag_instance.initialize_storages()

            # Create DocumentManager instance with workspace support
            doc_manager_config = self.doc_manager_config.copy()
            doc_manager = DocumentManager(**doc_manager_config, workspace=workspace)

            # Cache the instances
            self._instances[workspace] = rag_instance
            self._doc_managers[workspace] = doc_manager

            logger.info(f"Successfully created instances for workspace: {workspace}")
            return rag_instance, doc_manager

    def list_workspaces(self) -> List[str]:
        """
        List all currently managed workspaces.

        Returns:
            List[str]: List of workspace names
        """
        with self._lock:
            return list(self._instances.keys())

    async def shutdown_workspace(self, workspace: str) -> bool:
        """
        Shutdown and remove instances for a specific workspace.

        Args:
            workspace: Workspace name to shutdown

        Returns:
            bool: True if workspace was shutdown, False if not found
        """
        with self._lock:
            if workspace not in self._instances:
                return False

            logger.info(f"Shutting down workspace: {workspace}")

            # Finalize storages for the workspace
            try:
                await self._instances[workspace].finalize_storages()
            except Exception as e:
                logger.error(f"Error finalizing storages for workspace {workspace}: {e}")

            # Remove instances from cache
            del self._instances[workspace]
            del self._doc_managers[workspace]

            logger.info(f"Successfully shutdown workspace: {workspace}")
            return True

    async def shutdown_all(self) -> None:
        """
        Shutdown all workspace instances and clean up resources.
        """
        with self._lock:
            workspaces = list(self._instances.keys())

        logger.info(f"Shutting down all workspaces: {workspaces}")

        # Shutdown all workspaces
        for workspace in workspaces:
            await self.shutdown_workspace(workspace)

        logger.info("All workspaces shutdown successfully")

    def get_workspace_count(self) -> int:
        """
        Get the number of currently managed workspaces.

        Returns:
            int: Number of workspaces
        """
        with self._lock:
            return len(self._instances)

    def get_default_workspace(self) -> str:
        """
        Get the default workspace name.

        Returns:
            str: Default workspace name
        """
        return self.default_workspace