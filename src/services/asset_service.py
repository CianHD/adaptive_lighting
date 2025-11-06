from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DatabaseError, SQLAlchemyError

from src.db.models import Asset, Schedule, AuditLog, Policy, RealtimeCommand
from src.schemas.asset import AssetResponse, AssetStateResponse
from src.schemas.command import RealtimeCommandRequest
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
            exedra_id=asset.external_id,
            current_dim_percent=current_dim,
            current_schedule_id=current_schedule_id,
            updated_at=asset.updated_at
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
            exedra_id=asset.external_id,
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
                except (IntegrityError, DatabaseError, SQLAlchemyError) as sync_error:
                    # Don't fail the main operation if audit sync fails
                    print(f"Warning: Failed to sync schedule to local DB: {sync_error}")
                    if db:
                        db.rollback()

            return schedule_data

        except (ValueError, RuntimeError, ConnectionError, TimeoutError) as e:
            raise RuntimeError(f"Failed to retrieve EXEDRA schedule: {str(e)}") from e

    @staticmethod
    def update_asset_schedule_in_exedra(
        asset: Asset,
        schedule_steps: List[Dict[str, Any]],
        actor: str,
        idempotency_key: Optional[str],
        db: Session
    ) -> str:
        """
        Update an asset's schedule in EXEDRA
        
        Args:
            asset: Asset to update schedule for
            schedule_steps: List of {"time": "HH:MM", "dim": 0-100} objects
            actor: Name of the actor making the change
            idempotency_key: Optional idempotency key for duplicate prevention
            db: Database session
            
        Returns:
            Schedule ID of the created schedule record
            
        Raises:
            ValueError: If asset has no EXEDRA program ID configured
            RuntimeError: If EXEDRA API call fails
        """
        # Check for duplicate request using idempotency key
        if idempotency_key:
            existing_schedule = db.query(Schedule).filter(
                Schedule.asset_id == asset.asset_id,
                Schedule.idempotency_key == idempotency_key
            ).first()

            if existing_schedule:
                return str(existing_schedule.schedule_id)

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
                    status="active",
                    idempotency_key=idempotency_key
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

        except (IntegrityError, DatabaseError, SQLAlchemyError) as db_error:
            db.rollback()
            raise RuntimeError(f"Database error during EXEDRA schedule update: {str(db_error)}") from db_error
        except (ValueError, RuntimeError, ConnectionError, TimeoutError) as api_error:
            db.rollback()
            raise RuntimeError(f"EXEDRA API error during schedule update: {str(api_error)}") from api_error

    # Realtime Command Methods

    @staticmethod
    def validate_basic_guardrails(_asset: Asset, dim_percent: int) -> tuple[bool, Optional[str]]:
        """
        Apply basic guardrails (API hygiene level).
        
        Args:
            asset: Asset to validate against
            dim_percent: Dimming percentage to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not 0 <= dim_percent <= 100:
            return False, "Dimming percentage must be between 0 and 100"

        # TODO: Implement actual rate limiting with Redis/database tracking (e.g., 1000/hr)
        # For now, this is a placeholder for future rate limiting logic

        return True, None

    @staticmethod
    def validate_policy_guardrails(asset: Asset, dim_percent: int, db: Session) -> tuple[bool, Optional[str]]:
        """
        Apply policy-level guardrails (only in optimize mode).
        
        Args:
            asset: Asset to validate against
            dim_percent: Dimming percentage to validate
            db: Database session
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if asset.control_mode != "optimise":
            return True, None  # No policy guardrails in passthrough mode

        current_policy = db.query(Policy).filter(Policy.project_id == asset.project_id).order_by(Policy.active_from.desc()).first()

        if not current_policy:
            return True, None  # No policy configured

        policy_body = current_policy.body

        # Check min/max constraints
        min_dim = policy_body.get("min_dim", 0)
        max_dim = policy_body.get("max_dim", 100)

        if dim_percent < min_dim:
            return False, f"Dimming below policy minimum: {min_dim}%"

        if dim_percent > max_dim:
            return False, f"Dimming above policy maximum: {max_dim}%"

        # TODO: Add more policy checks for future adaptive_service.py (optimise mode):
        # - Rate limiting (max_changes_per_hr) - implemented in adaptive service
        # - Dwell time constraints - prevent rapid cycling
        # - Time-of-night restrictions - reduce late night changes
        # - Kill switch status - emergency override capability
        # - Environmental data integration - weather/occupancy consideration
        # These will be implemented when developing the 'optimise' control mode

        return True, None

    @staticmethod
    def create_realtime_command(
        request: RealtimeCommandRequest,
        asset: Asset,
        api_client_id: str,
        api_client_name: str,
        idempotency_key: Optional[str],
        db: Session
    ) -> str:
        """
        Create a real-time dimming command.
        
        Args:
            request: Command request details
            asset: Target asset
            api_client_id: ID of requesting API client
            api_client_name: Name of requesting API client  
            idempotency_key: Optional idempotency key
            db: Database session
            
        Returns:
            Created command ID
            
        Raises:
            ValueError: If idempotency key already exists
            
        Note:
            This is a skeleton implementation. For actual EXEDRA integration,
            this should be expanded to use ExedraService similar to schedule updates.
        """
        # Check for existing command with same idempotency key
        if idempotency_key:
            existing_command = db.query(RealtimeCommand).filter(
                RealtimeCommand.requested_by_api_client == api_client_id,
                RealtimeCommand.idempotency_key == idempotency_key
            ).first()

            if existing_command:
                # Return existing command ID for idempotent behavior
                return existing_command.realtime_command_id

        # Create command record
        command = RealtimeCommand(
            asset_id=asset.asset_id,
            dim_percent=request.dim_percent,
            source_mode=asset.control_mode,
            vendor=api_client_name,
            status="simulated",  # TODO: Implement actual EXEDRA integration
            requested_by_api_client=api_client_id,
            idempotency_key=idempotency_key
        )

        db.add(command)
        db.flush()  # Get the ID

        # Audit log
        audit_entry = AuditLog(
            actor="api",
            project_id=asset.project_id,
            action="realtime_command",
            entity="asset",
            entity_id=asset.asset_id,
            details={
                "asset_external_id": asset.external_id,
                "dim_percent": request.dim_percent,
                "control_mode": asset.control_mode,
                "api_client": api_client_name,
                "note": request.note,
                "idempotency_key": idempotency_key
            }
        )
        db.add(audit_entry)
        db.commit()

        # TODO: Implement actual EXEDRA integration similar to schedule updates:
        # 1. Get EXEDRA configuration from CredentialService
        # 2. Use ExedraService to send realtime command
        # 3. Update command status based on success/failure
        # 4. Handle errors appropriately

        return command.realtime_command_id

    @staticmethod
    def create_asset(
        project_id: str,
        external_id: str,
        control_mode: str,
        exedra_name: str,
        exedra_control_program_id: str,
        exedra_calendar_id: str,
        actor: str,
        db: Session
    ) -> Asset:
        """
        Create a new asset with EXEDRA metadata and initial schedule record.
        
        Args:
            project_id: Project ID for the asset
            external_id: External ID of the asset (EXEDRA ID)
            control_mode: Control mode (optimise|passthrough)
            exedra_name: EXEDRA device name
            exedra_control_program_id: EXEDRA control program ID
            exedra_calendar_id: EXEDRA calendar ID
            actor: Name of the actor creating the asset
            db: Database session
            
        Returns:
            Created Asset instance
            
        Raises:
            ValueError: If asset already exists
        """
        # Check if asset already exists
        existing_asset = db.query(Asset).filter(
            Asset.project_id == project_id,
            Asset.external_id == external_id
        ).first()
        if existing_asset:
            raise ValueError(f"Asset with external_id '{external_id}' already exists in this project")

        # Create asset metadata
        asset_metadata = {
            "exedra_control_program_id": exedra_control_program_id,
            "exedra_calendar_id": exedra_calendar_id
        }

        # Create the asset
        asset = Asset(
            project_id=project_id,
            external_id=external_id,
            name=exedra_name,
            control_mode=control_mode,
            asset_metadata=asset_metadata
        )

        db.add(asset)
        db.flush()  # Flush to get the asset_id

        # Create initial schedule record with the control program ID and calendar ID
        schedule = Schedule(
            asset_id=asset.asset_id,
            exedra_control_program_id=exedra_control_program_id,
            exedra_calendar_id=exedra_calendar_id,
            schedule={"steps": []},  # Empty schedule initially
            provider="exedra",
            status="active"
        )
        db.add(schedule)

        # Create audit log
        audit = AuditLog(
            actor=actor,
            action="create_asset",
            entity="asset",
            entity_id=str(asset.asset_id),
            details={
                "external_id": external_id,
                "control_mode": control_mode,
                "exedra_name": exedra_name,
                "exedra_control_program_id": exedra_control_program_id,
                "exedra_calendar_id": exedra_calendar_id
            }
        )
        db.add(audit)
        db.commit()

        return asset

    @staticmethod
    def update_asset(
        external_id: str,
        project_id: str,
        exedra_name: Optional[str] = None,
        exedra_control_program_id: Optional[str] = None,
        exedra_calendar_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        actor: str = "unknown",
        db: Session = None
    ) -> Asset:
        """
        Update an asset's details (excludes external_id which is immutable).
        
        Args:
            external_id: The asset's external ID (immutable identifier)
            project_id: Project ID for tenant isolation
            exedra_name: Updated EXEDRA device name
            exedra_control_program_id: Updated EXEDRA control program ID
            exedra_calendar_id: Updated EXEDRA calendar ID
            metadata: Updated metadata (merged with existing)
            actor: Who is performing the update
            db: Database session
            
        Returns:
            Updated Asset object
            
        Raises:
            ValueError: If asset not found or no updates provided
        """
        # Get existing asset
        asset = db.query(Asset).filter(
            Asset.project_id == project_id,
            Asset.external_id == external_id
        ).first()

        if not asset:
            raise ValueError(f"Asset with external_id '{external_id}' not found in this project")

        # Check if any updates are provided
        if not any([exedra_name, exedra_control_program_id, exedra_calendar_id, metadata]):
            raise ValueError("At least one field must be provided for update")

        # Update asset fields
        if exedra_name is not None:
            asset.name = exedra_name

        # Update metadata - merge with existing
        if metadata is not None:
            current_metadata = asset.asset_metadata or {}

            # Update EXEDRA fields in metadata
            if exedra_control_program_id is not None:
                current_metadata["exedra_control_program_id"] = exedra_control_program_id
            if exedra_calendar_id is not None:
                current_metadata["exedra_calendar_id"] = exedra_calendar_id

            # Merge additional metadata
            current_metadata.update(metadata)
            asset.asset_metadata = current_metadata
        else:
            # Update EXEDRA fields even if no additional metadata provided
            current_metadata = asset.asset_metadata or {}
            if exedra_control_program_id is not None:
                current_metadata["exedra_control_program_id"] = exedra_control_program_id
            if exedra_calendar_id is not None:
                current_metadata["exedra_calendar_id"] = exedra_calendar_id
            asset.asset_metadata = current_metadata

        # Note: updated_at will be handled by database trigger or default value
        # No need to manually set timestamp

        try:
            db.commit()
            db.refresh(asset)

            # Log the update
            audit_entry = AuditLog(
                actor=actor,
                project_id=project_id,
                action="update_asset",
                entity="asset",
                entity_id=asset.asset_id,
                details={
                    "external_id": external_id,
                    "updated_fields": {
                        "exedra_name": exedra_name,
                        "exedra_control_program_id": exedra_control_program_id,
                        "exedra_calendar_id": exedra_calendar_id,
                        "metadata_updated": metadata is not None
                    }
                }
            )
            db.add(audit_entry)
            db.commit()

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            raise RuntimeError(f"Database error during asset update: {str(e)}") from e

        return asset

    @staticmethod
    def delete_asset(
        external_id: str,
        project_id: str,
        actor: str = "unknown",
        db: Session = None
    ) -> bool:
        """
        Delete an asset and its associated data.
        
        Args:
            external_id: The asset's external ID
            project_id: Project ID for tenant isolation
            actor: Who is performing the deletion
            db: Database session
            
        Returns:
            True if deletion was successful
            
        Raises:
            ValueError: If asset not found
        """
        # Get existing asset
        asset = db.query(Asset).filter(
            Asset.project_id == project_id,
            Asset.external_id == external_id
        ).first()

        if not asset:
            raise ValueError(f"Asset with external_id '{external_id}' not found in this project")

        asset_id = asset.asset_id

        try:
            # Log the deletion before actually deleting
            audit_entry = AuditLog(
                actor=actor,
                project_id=project_id,
                action="delete_asset",
                entity="asset",
                entity_id=asset_id,
                details={
                    "external_id": external_id,
                    "asset_name": asset.name,
                    "control_mode": asset.control_mode
                }
            )
            db.add(audit_entry)

            # Delete the asset (cascade will handle related records)
            db.delete(asset)
            db.commit()

        except (IntegrityError, DatabaseError, SQLAlchemyError) as e:
            db.rollback()
            raise RuntimeError(f"Database error during asset deletion: {str(e)}") from e

        return True
