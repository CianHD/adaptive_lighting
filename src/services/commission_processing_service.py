from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import engine
from src.services.asset_service import AssetService


class CommissionProcessingService:
    """Service for processing pending asset commissions"""

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize the commission processing service
        
        Args:
            db_session: Optional database session (will create one if not provided)
        """
        self.db_session = db_session
        self._session_maker = sessionmaker(bind=engine) if not db_session else None

    async def process_all_pending_commissions(self, max_concurrent: int = 10) -> dict:
        """
        Process all pending commissions across all projects
        
        Args:
            max_concurrent: Maximum concurrent commission attempts
            
        Returns:
            Dictionary with processing results and statistics
        """
        start_time = datetime.now(timezone.utc)

        try:
            if self.db_session:
                # Use provided session
                return await self._process_with_session(self.db_session, max_concurrent)
            else:
                # Create new session
                with self._session_maker() as db:
                    return await self._process_with_session(db, max_concurrent)

        except SQLAlchemyError as e:
            return {
                "success": False,
                "error": f"Database error: {str(e)}",
                "start_time": start_time,
                "end_time": datetime.now(timezone.utc)
            }

    async def _process_with_session(self, db: Session, max_concurrent: int) -> dict:
        """Process pending commissions with the given database session"""
        start_time = datetime.now(timezone.utc)

        try:
            # Use AssetService method for actual processing
            await AssetService.process_pending_commissions(db=db, max_concurrent=max_concurrent)

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            return {
                "success": True,
                "start_time": start_time,
                "end_time": end_time,
                "duration_seconds": duration,
                "max_concurrent": max_concurrent
            }

        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            return {
                "success": False,
                "error": str(e),
                "start_time": start_time,
                "end_time": datetime.now(timezone.utc)
            }

    async def process_single_asset_commission(self, asset_external_id: str, project_id: str) -> dict:
        """
        Process commissioning for a single specific asset
        
        Args:
            asset_external_id: External ID of the asset to commission
            project_id: Project ID for tenant isolation
            
        Returns:
            Dictionary with commission result
        """
        try:
            if self.db_session:
                db = self.db_session
            else:
                db = self._session_maker()

            try:
                # Find the asset
                asset = AssetService.get_asset_by_external_id(
                    external_id=asset_external_id,
                    project_id=project_id,
                    db=db
                )

                if not asset:
                    return {
                        "success": False,
                        "error": f"Asset {asset_external_id} not found in project {project_id}"
                    }

                # Attempt commissioning
                success = AssetService.commission_asset(
                    asset=asset,
                    actor="commission_service",
                    db=db
                )

                return {
                    "success": success,
                    "asset_external_id": asset_external_id,
                    "project_id": project_id,
                    "timestamp": datetime.now(timezone.utc)
                }

            finally:
                if not self.db_session and db:
                    db.close()

        except (SQLAlchemyError, ValueError, RuntimeError) as e:
            return {
                "success": False,
                "error": str(e),
                "asset_external_id": asset_external_id,
                "project_id": project_id
            }


# Standalone function for scheduled execution (background tasks, schedulers, etc.)
async def run_commission_processing(max_concurrent: int = 10) -> dict:
    """
    Standalone function for running commission processing.
    
    This function is designed for background processing systems, scheduled tasks,
    API endpoints, and containerized environments.
    
    Args:
        max_concurrent: Maximum concurrent commission attempts
        
    Returns:
        Dictionary with processing results
    """
    service = CommissionProcessingService()
    return await service.process_all_pending_commissions(max_concurrent)
