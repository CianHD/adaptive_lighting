"""
Email service for sending critical notifications and alerts.

This service will be used to communicate critical issues to clients,
such as EXEDRA integration failures, system errors, or security alerts.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels for email notifications"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EmailService:
    """Service for sending email notifications to clients"""

    @staticmethod
    def send_critical_alert(
        recipients: List[str],
        subject: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.CRITICAL,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a critical alert email to specified recipients.
        
        Args:
            recipients: List of email addresses
            subject: Email subject line
            message: Email body content
            severity: Alert severity level
            context: Additional context data for the alert
            
        Returns:
            True if email sent successfully, False otherwise
        """
        # TODO: Implement email sending logic
        # This will be implemented when email notifications are required
        # Likely using SMTP with template system for consistent formatting

        logger.info("ALERT [%s]: %s", severity.value.upper(), subject)
        logger.info("Recipients: %s", ', '.join(recipients))
        logger.info("Message: %s", message)
        if context:
            logger.info("Context: %s", context)

        # For now, just log the alert - email sending will be added later
        return True

    @staticmethod
    def send_exedra_failure_alert(
        client_email: str,
        asset_external_id: str,
        error_message: str,
        operation: str
    ) -> bool:
        """
        Send alert when EXEDRA integration fails.
        
        Args:
            client_email: Client's notification email
            asset_external_id: EXEDRA device ID that failed
            error_message: Technical error details
            operation: Operation that failed (e.g., 'schedule_update', 'realtime_command')
            
        Returns:
            True if notification sent successfully
        """
        subject = f"EXEDRA Integration Failure - Asset {asset_external_id}"
        message = f"""EXEDRA operation failed for asset {asset_external_id}.

Operation: {operation}
Time: {datetime.now().isoformat()}
Error: {error_message}

Please check your EXEDRA system and contact support if the issue persists."""

        context = {
            "asset_id": asset_external_id,
            "operation": operation,
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }

        return EmailService.send_critical_alert(
            recipients=[client_email],
            subject=subject,
            message=message,
            severity=AlertSeverity.HIGH,
            context=context
        )

    @staticmethod
    def send_system_status_alert(
        admin_emails: List[str],
        service_name: str,
        status: str,
        details: str
    ) -> bool:
        """
        Send system status alerts to administrators.
        
        Args:
            admin_emails: List of administrator email addresses
            service_name: Name of the service experiencing issues
            status: Current status (e.g., 'degraded', 'down', 'recovered')
            details: Additional details about the status change
            
        Returns:
            True if notification sent successfully
        """
        subject = f"System Alert: {service_name} - {status.upper()}"
        message = f"""System status change detected:

Service: {service_name}
Status: {status}
Time: {datetime.now().isoformat()}
Details: {details}

Please investigate and take appropriate action."""

        context = {
            "service": service_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }

        severity = AlertSeverity.CRITICAL if status in ['down', 'critical'] else AlertSeverity.HIGH

        return EmailService.send_critical_alert(
            recipients=admin_emails,
            subject=subject,
            message=message,
            severity=severity,
            context=context
        )
