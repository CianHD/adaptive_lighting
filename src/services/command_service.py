from typing import Optional, Tuple, List
from sqlalchemy.orm import Session

from src.db.models import Asset, RealtimeCommand, Schedule, AuditLog, Policy
from src.schemas.command import RealtimeCommandRequest, ScheduleCommandRequest, ScheduleStep


class CommandService:
    """Service class for command-related business logic"""

    @staticmethod
    def validate_basic_guardrails(asset: Asset, dim_percent: int) -> Tuple[bool, Optional[str]]:
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

        # Add more basic validation as needed
        return True, None

    @staticmethod
    def validate_policy_guardrails(asset: Asset, dim_percent: int, db: Session) -> Tuple[bool, Optional[str]]:
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

        # Get current policy for project
        current_policy = db.query(Policy).filter(
            Policy.project_id == asset.project_id
        ).order_by(Policy.active_from.desc()).first()

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

        # TODO: Add more policy checks:
        # - Rate limiting (max_changes_per_hr)
        # - Dwell time constraints
        # - Time-of-night restrictions
        # - Kill switch status

        return True, None

    @staticmethod
    def create_realtime_command(
        request: RealtimeCommandRequest,
        asset: Asset,
        api_client_id: str,
        api_client_name: str,
        project_id: str,
        idempotency_key: Optional[str],
        db: Session
    ) -> RealtimeCommand:
        """
        Create a real-time dimming command.
        
        Args:
            request: Command request details
            asset: Target asset
            api_client_id: ID of requesting API client
            api_client_name: Name of requesting API client
            project_id: Project ID for audit trail
            idempotency_key: Optional idempotency key
            db: Database session
            
        Returns:
            Created RealtimeCommand instance
        """
        # Create command record
        command = RealtimeCommand(
            asset_id=asset.asset_id,
            requested_at=request.requested_at,
            dim_percent=request.dim_percent,
            source_mode=asset.control_mode,
            vendor=api_client_name,
            status="simulated",  # Will be updated when actually sent to EXEDRA
            requested_by_api_client=api_client_id
        )

        db.add(command)
        db.flush()  # Get the ID

        # Audit log
        audit_entry = AuditLog(
            actor="api",
            project_id=project_id,
            action="realtime_command",
            entity="asset",
            entity_id=asset.asset_id,
            details={
                "asset_external_id": request.asset_external_id,
                "dim_percent": request.dim_percent,
                "control_mode": asset.control_mode,
                "api_client": api_client_name,
                "note": request.note,
                "idempotency_key": idempotency_key
            }
        )
        db.add(audit_entry)
        db.commit()

        # TODO: Queue for EXEDRA relay
        # In a real implementation, you'd send this to a message queue
        # or background service to relay to EXEDRA

        return command

    @staticmethod
    def validate_schedule_steps(steps: List[ScheduleStep]) -> Tuple[bool, Optional[str]]:
        """
        Validate schedule step format and content.
        
        Args:
            steps: List of schedule steps to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not steps:
            return False, "Schedule must have at least one step"

        for step in steps:
            # Validate time format
            try:
                hour, minute = step.time.split(":")
                if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                    raise ValueError()
            except (ValueError, IndexError):
                return False, f"Invalid time format: {step.time}. Use HH:MM"

            # Validate dim percentage
            if not 0 <= step.dim <= 100:
                return False, f"Invalid dim percentage: {step.dim}. Must be 0-100"

        return True, None

    @staticmethod
    def create_schedule_command(
        request: ScheduleCommandRequest,
        asset: Asset,
        api_client_name: str,
        project_id: str,
        idempotency_key: Optional[str],
        db: Session
    ) -> Schedule:
        """
        Create a lighting schedule command.
        
        Args:
            request: Schedule command request
            asset: Target asset
            api_client_name: Name of requesting API client
            project_id: Project ID for audit trail
            idempotency_key: Optional idempotency key
            db: Database session
            
        Returns:
            Created Schedule instance
        """
        # Mark existing schedules as superseded
        db.query(Schedule).filter(
            Schedule.asset_id == asset.asset_id,
            Schedule.status == "active"
        ).update({"status": "superseded"})

        # Create new schedule
        schedule_data = {
            "steps": [{"time": step.time, "dim": step.dim} for step in request.steps],
            "note": request.note,
            "requested_at": request.requested_at.isoformat()
        }

        schedule = Schedule(
            asset_id=asset.asset_id,
            schedule=schedule_data,
            provider="vendor",
            status="active"
        )

        db.add(schedule)
        db.flush()

        # Audit log
        audit_entry = AuditLog(
            actor="api",
            project_id=project_id,
            action="schedule_command",
            entity="asset",
            entity_id=asset.asset_id,
            details={
                "asset_external_id": request.asset_external_id,
                "schedule_id": schedule.schedule_id,
                "step_count": len(request.steps),
                "control_mode": asset.control_mode,
                "api_client": api_client_name,
                "idempotency_key": idempotency_key
            }
        )
        db.add(audit_entry)
        db.commit()

        return schedule

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
