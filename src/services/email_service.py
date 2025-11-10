"""
Email service for sending critical notifications and alerts.

This service will be used to communicate critical issues to clients,
such as EXEDRA integration failures, system errors, or security alerts.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from src.core.config import settings
from src.db.models import ApiClient


class AlertSeverity(Enum):
    """Alert severity levels for email notifications"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EmailService:
    """Service for sending email notifications to clients"""

    @staticmethod
    def _send_smtp_email(
        recipients: List[str],
        subject: str,
        message: str
    ) -> bool:
        """
        Send email using SMTP configuration from settings.
        
        Args:
            recipients: List of email addresses
            subject: Email subject line
            message: Email body content
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = settings.EMAIL_FROM
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject

            # Attach body
            msg.attach(MIMEText(message, 'plain'))

            # Connect to SMTP server and send
            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()  # Enable TLS encryption
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)

            return True

        except (smtplib.SMTPException, ConnectionError, OSError) as e:
            # Re-raise with more context for error middleware
            raise RuntimeError(f"Failed to send email to {', '.join(recipients)}: {str(e)}") from e

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
            True if email sent successfully
        """
        # Build enhanced email body with severity and context
        message = f"""ALERT SEVERITY: {severity.value.upper()}
                      Timestamp: {datetime.now().isoformat()}

                      {message}"""

        # Add context information if provided
        if context:
            message += "\n\n--- TECHNICAL DETAILS ---\n"
            for key, value in context.items():
                message += f"{key.replace('_', ' ').title()}: {value}\n"

        # Update subject to include severity for urgent alerts
        enhanced_subject = subject
        if severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            enhanced_subject = f"[{severity.value.upper()}] {subject}"

        # Send the actual email
        return EmailService._send_smtp_email(recipients, enhanced_subject, message)

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

    @staticmethod
    def send_commission_failure_alert(
        asset,
        schedule,
        db_session,
        admin_email: Optional[str] = None
    ) -> bool:
        """
        Send alert when asset commissioning fails after max retries.
        
        Args:
            asset: Asset that failed commissioning
            schedule: Schedule with commission failure details
            db_session: Database session for querying admin email
            admin_email: Override admin email (defaults to API client email)
            
        Returns:
            True if notification sent successfully
        """
        # Get admin email from API client if not provided
        if not admin_email:
            api_client = db_session.query(ApiClient).filter_by(project_id=asset.project_id).first()
            if (api_client and api_client.contact_email):
                admin_email = api_client.contact_email
            else:
                raise ValueError(f"No admin contact email found for project {asset.project_id}. Please configure a contact email for the project's API client.")

        recipient_email = admin_email

        subject = f"EXEDRA Commissioning Failed: Asset {asset.external_id}"
        message = f"""Commissioning failed for asset {asset.external_id} ({asset.name}) after {schedule.commission_attempts} attempts.

                      Asset Details:
                      - External ID: {asset.external_id}
                      - Name: {asset.name}
                      - Control Mode: {asset.control_mode}
                      - Project: {asset.project_id}

                      Schedule Details:
                      - Schedule ID: {schedule.schedule_id}
                      - Created: {schedule.created_at}
                      - Last Attempt: {schedule.last_commission_attempt}
                      - Total Attempts: {schedule.commission_attempts}

                      Last Error: {schedule.commission_error}

                      Please investigate the asset connectivity and EXEDRA system status.
                      You can manually retry commissioning via the API or admin interface."""

        context = {
            "asset_external_id": asset.external_id,
            "asset_name": asset.name,
            "schedule_id": schedule.schedule_id,
            "commission_attempts": schedule.commission_attempts,
            "commission_error": schedule.commission_error,
            "project_id": asset.project_id
        }

        return EmailService.send_critical_alert(
            recipients=[recipient_email],
            subject=subject,
            message=message,
            severity=AlertSeverity.HIGH,
            context=context
        )
