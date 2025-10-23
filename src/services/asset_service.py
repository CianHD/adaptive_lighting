from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from src.db.models import Asset, Schedule, AuditLog
from src.schemas.asset import AssetResponse, AssetStateResponse
from src.schemas.command import ScheduleResponse, ScheduleStep


class AssetService:
    """Service class for asset-related business logic"""

    @staticmethod
    def get_asset_by_external_id(external_id: str, project_id: str, db: Session) -> Optional[Asset]:
        """
        Get asset by external ID within project scope.
        
        Args:
            external_id: External ID of the asset
            project_id: Project ID for tenant isolation
            db: Database session
            
        Returns:
            Asset instance or None if not found
        """
        return db.query(Asset).filter(
            Asset.project_id == project_id,
            Asset.external_id == external_id
        ).first()

    @staticmethod
    def get_asset_state(asset: Asset, db: Session) -> AssetStateResponse:
        """
        Get current state of an asset including dimming level and active schedule.
        
        Args:
            asset: Asset to get state for
            db: Database session
            
        Returns:
            AssetStateResponse with current state
        """
        # Get current active schedule
        current_schedule = db.query(Schedule).filter(
            Schedule.asset_id == asset.asset_id,
            Schedule.status == "active"
        ).order_by(Schedule.created_at.desc()).first()

        # In a real implementation, you'd query the actual asset state
        # For now, we'll use placeholder data or derive from recent commands
        current_dim = None
        current_schedule_id = current_schedule.schedule_id if current_schedule else None

        # TODO: Query asset state table or real-time asset status
        # This would typically come from EXEDRA or cached state

        return AssetStateResponse(
            asset_external_id=asset.external_id,
            current_dim_percent=current_dim,
            current_schedule_id=current_schedule_id,
            updated_at=datetime.now(timezone.utc)
        )

    @staticmethod
    def get_asset_schedule(asset: Asset, db: Session) -> Optional[ScheduleResponse]:
        """
        Get current active schedule for an asset.
        
        Args:
            asset: Asset to get schedule for
            db: Database session
            
        Returns:
            ScheduleResponse or None if no active schedule
        """
        # Get current active schedule
        current_schedule = db.query(Schedule).filter(
            Schedule.asset_id == asset.asset_id,
            Schedule.status == "active"
        ).order_by(Schedule.created_at.desc()).first()

        if not current_schedule:
            return None

        # Parse schedule steps
        steps = []
        for step_data in current_schedule.schedule.get("steps", []):
            steps.append(ScheduleStep(
                time=step_data["time"],
                dim=step_data["dim"]
            ))

        return ScheduleResponse(
            schedule_id=current_schedule.schedule_id,
            steps=steps,
            provider=current_schedule.provider,
            status=current_schedule.status,
            created_at=current_schedule.created_at
        )

    @staticmethod
    def get_asset_details(asset: Asset) -> AssetResponse:
        """
        Get asset details for API response.
        
        Args:
            asset: Asset to get details for
            
        Returns:
            AssetResponse with asset details
        """
        return AssetResponse(
            external_id=asset.external_id,
            name=asset.name,
            control_mode=asset.control_mode,
            road_class=asset.road_class,
            metadata=asset.metadata
        )

    @staticmethod
    def update_control_mode(
        asset: Asset,
        new_mode: str,
        api_client_name: str,
        project_id: str,
        db: Session
    ) -> Asset:
        """
        Update asset control mode and create audit trail.
        
        Args:
            asset: Asset to update
            new_mode: New control mode ('optimise' or 'passthrough')
            api_client_name: Name of API client making the change
            project_id: Project ID for audit trail
            db: Database session
            
        Returns:
            Updated Asset instance
        """
        old_mode = asset.control_mode
        asset.control_mode = new_mode

        # Audit log
        audit_entry = AuditLog(
            actor="api",
            project_id=project_id,
            action="control_mode_change",
            entity="asset",
            entity_id=asset.asset_id,
            details={
                "asset_external_id": asset.external_id,
                "old_mode": old_mode,
                "new_mode": new_mode,
                "api_client": api_client_name
            }
        )
        db.add(audit_entry)
        db.commit()

        return asset
