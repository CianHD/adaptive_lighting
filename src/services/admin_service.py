from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.db.models import Policy, AuditLog
from src.schemas.admin import PolicyRequest


class AdminService:
    """Service class for administrative operations"""

    @staticmethod
    def validate_policy_body(policy_body: dict) -> tuple[bool, Optional[str]]:
        """
        Validate policy configuration structure and values.
        
        Args:
            policy_body: Policy configuration dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["min_dim", "max_dim", "max_changes_per_hr"]
        for field in required_fields:
            if field not in policy_body:
                return False, f"Missing required policy field: {field}"

        # Basic validation
        if policy_body["min_dim"] < 0 or policy_body["max_dim"] > 100:
            return False, "Dimming percentages must be between 0 and 100"

        if policy_body["min_dim"] >= policy_body["max_dim"]:
            return False, "min_dim must be less than max_dim"

        if policy_body["max_changes_per_hr"] <= 0:
            return False, "max_changes_per_hr must be positive"

        return True, None

    @staticmethod
    def create_policy(request: PolicyRequest, project_id: str, api_client_name: str, db: Session) -> Policy:
        """
        Create a new policy configuration.
        
        Args:
            request: Policy creation request
            project_id: Project ID for the policy
            api_client_name: Name of API client creating policy
            db: Database session
            
        Returns:
            Created Policy instance
        """
        # Create new policy (supersedes previous)
        policy = Policy(
            project_id=project_id,
            version=request.version,
            body=request.body,
            active_from=datetime.now(timezone.utc)
        )

        db.add(policy)
        db.flush()

        # Audit log
        audit_entry = AuditLog(
            actor="api",
            project_id=project_id,
            action="policy_update",
            entity="policy",
            entity_id=policy.policy_id,
            details={
                "version": request.version,
                "api_client": api_client_name,
                "policy_fields": list(request.body.keys())
            }
        )
        db.add(audit_entry)
        db.commit()

        return policy

    @staticmethod
    def get_current_policy(
        project_id: str,
        db: Session
    ) -> Optional[Policy]:
        """
        Get the current active policy for a project.
        
        Args:
            project_id: Project ID to get policy for
            db: Database session
            
        Returns:
            Current Policy instance or None if no policy exists
        """
        return db.query(Policy).filter(
            Policy.project_id == project_id
        ).order_by(desc(Policy.active_from)).first()

    @staticmethod
    def toggle_kill_switch(
        enabled: bool,
        reason: Optional[str],
        project_id: str,
        api_client_name: str,
        db: Session
    ) -> AuditLog:
        """
        Toggle kill switch state and create audit record.
        
        Args:
            enabled: Whether to enable or disable kill switch
            reason: Optional reason for the change
            project_id: Project ID for the kill switch
            api_client_name: Name of API client making the change
            db: Database session
            
        Returns:
            Created AuditLog entry
        """
        # Audit log entry (serves as kill switch state storage)
        audit_entry = AuditLog(
            actor="api",
            project_id=project_id,
            action="kill_switch_toggle",
            entity="system",
            entity_id=project_id,
            details={
                "enabled": enabled,
                "reason": reason,
                "api_client": api_client_name
            }
        )
        db.add(audit_entry)
        db.commit()

        # Implementation note: In production, notify background services
        # of kill switch state change via message queue or cache update

        return audit_entry

    @staticmethod
    def get_kill_switch_status(
        project_id: str,
        db: Session
    ) -> tuple[bool, Optional[str], datetime, str]:
        """
        Get current kill switch status for a project.
        
        Args:
            project_id: Project ID to check kill switch for
            db: Database session
            
        Returns:
            Tuple of (enabled, reason, changed_at, changed_by)
        """
        # Find most recent kill switch action
        latest_toggle = db.query(AuditLog).filter(
            AuditLog.project_id == project_id,
            AuditLog.action == "kill_switch_toggle"
        ).order_by(desc(AuditLog.timestamp)).first()

        if not latest_toggle:
            # Default to disabled if no toggle found
            return False, None, datetime.now(timezone.utc), "system"

        return (
            latest_toggle.details.get("enabled", False),
            latest_toggle.details.get("reason"),
            latest_toggle.timestamp,
            latest_toggle.details.get("api_client", "unknown")
        )

    @staticmethod
    def get_audit_logs(
        project_id: str,
        limit: int,
        offset: int,
        entity_filter: Optional[str],
        action_filter: Optional[str],
        db: Session
    ) -> List[AuditLog]:
        """
        Get filtered audit log entries for a project.
        
        Args:
            project_id: Project ID to get logs for
            limit: Maximum number of logs to return
            offset: Number of logs to skip
            entity_filter: Optional entity type filter
            action_filter: Optional action type filter
            db: Database session
            
        Returns:
            List of AuditLog instances
        """
        query = db.query(AuditLog).filter(
            AuditLog.project_id == project_id
        )

        if entity_filter:
            query = query.filter(AuditLog.entity == entity_filter)

        if action_filter:
            query = query.filter(AuditLog.action == action_filter)

        return query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()
