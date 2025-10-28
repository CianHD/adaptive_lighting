from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from src.db.models import Asset, Schedule, AuditLog
from src.schemas.asset import AssetResponse, AssetStateResponse
from src.services.exedra_service import ExedraService
from src.services.credential_service import CredentialService


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
            db: Database session (for audit logging)
            
        Returns:
            AssetStateResponse with current state from EXEDRA
        """
        try:
            # Get current schedule from EXEDRA for compliance validation
            # and sync to local DB for audit trail
            schedule_data = AssetService.get_asset_exedra_schedule(asset, db)
            current_schedule_id = schedule_data.get("schedule_id")
        except (ValueError, RuntimeError):
            # If EXEDRA is unavailable, fall back to local database
            current_schedule = db.query(Schedule).filter(
                Schedule.asset_id == asset.asset_id,
                Schedule.status == "active"
            ).order_by(Schedule.created_at.desc()).first()
            current_schedule_id = current_schedule.schedule_id if current_schedule else None

        # In a real implementation, you'd query the actual asset state from EXEDRA
        # For now, we'll use placeholder data
        current_dim = None

        # TODO: Query real-time asset status from EXEDRA
        # This would typically come from EXEDRA's live status endpoint

        return AssetStateResponse(
            asset_external_id=asset.external_id,
            current_dim_percent=current_dim,
            current_schedule_id=current_schedule_id,
            updated_at=datetime.now(timezone.utc)
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
            metadata=asset.asset_metadata
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

    @staticmethod
    def get_asset_exedra_schedule(asset: Asset, db: Session = None) -> Dict[str, Any]:
        """
        Get the current schedule from EXEDRA for an asset and sync to local database
        
        Args:
            asset: Asset to get EXEDRA schedule for
            db: Database session (optional, for audit syncing)
            
        Returns:
            Dictionary containing schedule data from EXEDRA
            
        Raises:
            ValueError: If asset has no EXEDRA program ID configured
            RuntimeError: If EXEDRA API call fails
        """
        # Get EXEDRA program ID from asset metadata
        metadata = asset.asset_metadata or {}
        exedra_program_id = metadata.get("exedra_program_id")

        if not exedra_program_id:
            raise ValueError(f"Asset {asset.external_id} has no EXEDRA program ID configured")

        # Get client's EXEDRA configuration (token and base URL)
        api_client = asset.project.api_clients[0] if asset.project.api_clients else None
        if not api_client:
            raise ValueError(f"No API client found for asset {asset.external_id}")

        exedra_config = CredentialService.get_exedra_config(api_client, db)
        if not exedra_config.get("token"):
            raise ValueError(f"No EXEDRA API token found for client {api_client.name}")
        if not exedra_config.get("base_url"):
            raise ValueError(f"No EXEDRA base URL found for client {api_client.name}")

        try:
            # Fetch from EXEDRA using client's token and base URL
            exedra_data = ExedraService.get_control_program(
                exedra_program_id,
                exedra_config["token"],
                exedra_config["base_url"]
            )

            # Convert EXEDRA commands to our schedule format
            steps = []
            for cmd in exedra_data.get("commands", []):
                if cmd.get("base") == "midnight":
                    offset_minutes = cmd.get("offset", 0)
                    hours = offset_minutes // 60
                    minutes = offset_minutes % 60

                    # Handle negative offsets (previous day)
                    if hours < 0:
                        hours = 24 + hours
                    elif hours >= 24:
                        hours = hours % 24

                    time_str = f"{hours:02d}:{minutes:02d}"
                    steps.append({
                        "time": time_str,
                        "dim": cmd.get("level", 0)
                    })

            schedule_data = {
                "schedule_id": exedra_program_id,
                "steps": sorted(steps, key=lambda x: x["time"]),
                "provider": "exedra",
                "status": "active",
                "exedra_data": exedra_data
            }

            # Sync to local database for audit trail (if db session provided)
            if db:
                try:
                    # Check if we already have this schedule version in local DB
                    existing_schedule = db.query(Schedule).filter(
                        Schedule.asset_id == asset.asset_id,
                        Schedule.schedule_id == exedra_program_id,
                        Schedule.status == "active"
                    ).first()

                    if not existing_schedule:
                        # Mark any existing schedules as superseded
                        db.query(Schedule).filter(
                            Schedule.asset_id == asset.asset_id,
                            Schedule.status == "active"
                        ).update({"status": "superseded"})

                        # Create new schedule record for audit trail
                        schedule = Schedule(
                            schedule_id=exedra_program_id,
                            asset_id=asset.asset_id,
                            schedule={"steps": schedule_data["steps"]},
                            provider="exedra",
                            status="active"
                        )
                        db.add(schedule)
                        db.commit()
                except Exception as sync_error:
                    # Don't fail the main operation if audit sync fails
                    print(f"Warning: Failed to sync schedule to local DB: {sync_error}")
                    if db:
                        db.rollback()

            return schedule_data

        except Exception as e:
            raise RuntimeError(f"Failed to retrieve EXEDRA schedule: {str(e)}") from e

    @staticmethod
    def update_asset_schedule_in_exedra(
        asset: Asset,
        schedule_steps: List[Dict[str, Any]],
        actor: str,
        db: Session
    ) -> str:
        """
        Update an asset's schedule in EXEDRA
        
        Args:
            asset: Asset to update schedule for
            schedule_steps: List of {"time": "HH:MM", "dim": 0-100} objects
            actor: Name of the actor making the change
            db: Database session
            
        Returns:
            Schedule ID of the created schedule record
            
        Raises:
            ValueError: If asset has no EXEDRA program ID configured
            RuntimeError: If EXEDRA API call fails
        """
        # Get EXEDRA program ID
        metadata = asset.asset_metadata or {}
        exedra_program_id = metadata.get("exedra_program_id")

        if not exedra_program_id:
            raise ValueError(f"Asset {asset.external_id} has no EXEDRA program ID configured")

        # Get client's EXEDRA configuration (token and base URL)
        api_client = asset.project.api_clients[0] if asset.project.api_clients else None
        if not api_client:
            raise ValueError(f"No API client found for asset {asset.external_id}")

        exedra_config = CredentialService.get_exedra_config(api_client, db)
        if not exedra_config.get("token"):
            raise ValueError(f"No EXEDRA API token found for client {api_client.name}")
        if not exedra_config.get("base_url"):
            raise ValueError(f"No EXEDRA base URL found for client {api_client.name}")

        try:
            # Convert schedule steps to EXEDRA commands
            exedra_commands = ExedraService.create_schedule_from_steps(schedule_steps)

            # Validate commands
            ExedraService.validate_commands(exedra_commands)

            # Update in EXEDRA
            success = ExedraService.update_control_program(
                program_id=exedra_program_id,
                commands=exedra_commands,
                token=exedra_config["token"],
                base_url=exedra_config["base_url"],
                asset_name=asset.name
            )

            if success:
                # Create schedule record in our database
                schedule = Schedule(
                    asset_id=asset.asset_id,
                    schedule={"steps": schedule_steps},
                    provider="exedra",
                    status="active"
                )

                # Mark any existing schedules as superseded
                db.query(Schedule).filter(
                    Schedule.asset_id == asset.asset_id,
                    Schedule.status == "active"
                ).update({"status": "superseded"})

                db.add(schedule)

                # Create audit log
                audit = AuditLog(
                    actor=actor,
                    action="update_schedule",
                    entity="asset",
                    entity_id=str(asset.asset_id),
                    details={
                        "asset_external_id": asset.external_id,
                        "schedule_steps": schedule_steps,
                        "exedra_program_id": exedra_program_id,
                        "provider": "exedra"
                    }
                )
                db.add(audit)
                db.commit()

                return schedule.schedule_id
            else:
                raise RuntimeError("EXEDRA update failed")

        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to update EXEDRA schedule: {str(e)}") from e
