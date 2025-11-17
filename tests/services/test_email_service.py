"""
Tests for email service
"""
import smtplib
from datetime import datetime
from unittest.mock import MagicMock, patch, Mock

import pytest

from src.services.email_service import EmailService, AlertSeverity


class TestSendSMTPEmail:
    """Tests for _send_smtp_email method"""

    @patch('src.services.email_service.smtplib.SMTP')
    @patch('src.services.email_service.settings')
    def test_send_smtp_email_success(self, mock_settings, mock_smtp_class):
        """Test successful email sending"""
        # Configure mock settings
        mock_settings.EMAIL_FROM = "noreply@example.com"
        mock_settings.SMTP_SERVER = "smtp.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USERNAME = "user"
        mock_settings.SMTP_PASSWORD = "password"

        # Configure mock SMTP server
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        # Call the method
        result = EmailService._send_smtp_email(
            recipients=["test@example.com"],
            subject="Test Subject",
            message="Test message body"
        )

        # Assertions
        assert result is True
        mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "password")
        mock_server.send_message.assert_called_once()

    @patch('src.services.email_service.smtplib.SMTP')
    @patch('src.services.email_service.settings')
    def test_send_smtp_email_multiple_recipients(self, mock_settings, mock_smtp_class):
        """Test sending email to multiple recipients"""
        # Configure mock settings
        mock_settings.EMAIL_FROM = "noreply@example.com"
        mock_settings.SMTP_SERVER = "smtp.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USERNAME = "user"
        mock_settings.SMTP_PASSWORD = "password"

        # Configure mock SMTP server
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        # Call the method
        result = EmailService._send_smtp_email(
            recipients=["test1@example.com", "test2@example.com", "test3@example.com"],
            subject="Test Subject",
            message="Test message"
        )

        # Assertions
        assert result is True
        mock_server.send_message.assert_called_once()

    @patch('src.services.email_service.smtplib.SMTP')
    @patch('src.services.email_service.settings')
    def test_send_smtp_email_smtp_exception(self, mock_settings, mock_smtp_class):
        """Test SMTP exception handling"""
        # Configure mock settings
        mock_settings.EMAIL_FROM = "noreply@example.com"
        mock_settings.SMTP_SERVER = "smtp.example.com"
        mock_settings.SMTP_PORT = 587

        # Configure mock to raise SMTPException
        mock_smtp_class.side_effect = smtplib.SMTPException("SMTP connection failed")

        # Call should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            EmailService._send_smtp_email(
                recipients=["test@example.com"],
                subject="Test",
                message="Test message"
            )

        assert "Failed to send email" in str(exc_info.value)
        assert "test@example.com" in str(exc_info.value)

    @patch('src.services.email_service.smtplib.SMTP')
    @patch('src.services.email_service.settings')
    def test_send_smtp_email_connection_error(self, mock_settings, mock_smtp_class):
        """Test connection error handling"""
        # Configure mock settings
        mock_settings.EMAIL_FROM = "noreply@example.com"
        mock_settings.SMTP_SERVER = "smtp.example.com"
        mock_settings.SMTP_PORT = 587

        # Configure mock to raise ConnectionError
        mock_smtp_class.side_effect = ConnectionError("Cannot connect to server")

        # Call should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            EmailService._send_smtp_email(
                recipients=["test@example.com"],
                subject="Test",
                message="Test message"
            )

        assert "Failed to send email" in str(exc_info.value)


class TestSendCriticalAlert:
    """Tests for send_critical_alert method"""

    @patch.object(EmailService, '_send_smtp_email')
    def test_send_critical_alert_basic(self, mock_send):
        """Test sending basic critical alert"""
        mock_send.return_value = True

        result = EmailService.send_critical_alert(
            recipients=["admin@example.com"],
            subject="Test Alert",
            message="Test alert message"
        )

        assert result is True
        mock_send.assert_called_once()

        # Check call arguments
        call_args = mock_send.call_args
        assert call_args[0][0] == ["admin@example.com"]
        assert "[CRITICAL]" in call_args[0][1]  # Subject includes severity
        assert "Test Alert" in call_args[0][1]
        assert "ALERT SEVERITY: CRITICAL" in call_args[0][2]
        assert "Test alert message" in call_args[0][2]

    @patch.object(EmailService, '_send_smtp_email')
    def test_send_critical_alert_with_context(self, mock_send):
        """Test sending alert with context data"""
        mock_send.return_value = True

        context = {
            "error_code": "E1001",
            "service_name": "EXEDRA",
            "retry_count": 3
        }

        result = EmailService.send_critical_alert(
            recipients=["admin@example.com"],
            subject="Service Error",
            message="Service failed",
            severity=AlertSeverity.HIGH,
            context=context
        )

        assert result is True

        # Check that context is in the message
        call_args = mock_send.call_args
        message = call_args[0][2]
        assert "TECHNICAL DETAILS" in message
        assert "Error Code: E1001" in message
        assert "Service Name: EXEDRA" in message
        assert "Retry Count: 3" in message

    @patch.object(EmailService, '_send_smtp_email')
    def test_send_critical_alert_low_severity(self, mock_send):
        """Test that LOW severity doesn't modify subject"""
        mock_send.return_value = True

        result = EmailService.send_critical_alert(
            recipients=["admin@example.com"],
            subject="Info Message",
            message="Information only",
            severity=AlertSeverity.LOW
        )

        assert result is True

        # LOW severity shouldn't add prefix to subject
        call_args = mock_send.call_args
        subject = call_args[0][1]
        assert subject == "Info Message"  # No [LOW] prefix

    @patch.object(EmailService, '_send_smtp_email')
    def test_send_critical_alert_high_severity(self, mock_send):
        """Test that HIGH severity modifies subject"""
        mock_send.return_value = True

        result = EmailService.send_critical_alert(
            recipients=["admin@example.com"],
            subject="Important Alert",
            message="High priority message",
            severity=AlertSeverity.HIGH
        )

        assert result is True

        # HIGH severity should add prefix
        call_args = mock_send.call_args
        subject = call_args[0][1]
        assert "[HIGH]" in subject
        assert "Important Alert" in subject


class TestSendExedraFailureAlert:
    """Tests for send_exedra_failure_alert method"""

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_exedra_failure_alert_success(self, mock_send_alert):
        """Test sending EXEDRA failure alert"""
        mock_send_alert.return_value = True

        result = EmailService.send_exedra_failure_alert(
            client_email="client@example.com",
            asset_external_id="EXEDRA123",
            error_message="Connection timeout",
            operation="schedule_update"
        )

        assert result is True
        mock_send_alert.assert_called_once()

        # Check call arguments
        call_args = mock_send_alert.call_args
        assert call_args[1]['recipients'] == ["client@example.com"]
        assert "EXEDRA123" in call_args[1]['subject']
        assert "Connection timeout" in call_args[1]['message']
        assert "schedule_update" in call_args[1]['message']
        assert call_args[1]['severity'] == AlertSeverity.HIGH

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_exedra_failure_alert_with_context(self, mock_send_alert):
        """Test that context is passed correctly"""
        mock_send_alert.return_value = True

        result = EmailService.send_exedra_failure_alert(
            client_email="client@example.com",
            asset_external_id="EXEDRA456",
            error_message="API Error 500",
            operation="realtime_command"
        )

        assert result is True

        # Check context
        call_args = mock_send_alert.call_args
        context = call_args[1]['context']
        assert context['asset_id'] == "EXEDRA456"
        assert context['operation'] == "realtime_command"
        assert context['error'] == "API Error 500"
        assert 'timestamp' in context


class TestSendSystemStatusAlert:
    """Tests for send_system_status_alert method"""

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_system_status_alert_critical(self, mock_send_alert):
        """Test system status alert for critical status"""
        mock_send_alert.return_value = True

        result = EmailService.send_system_status_alert(
            admin_emails=["admin1@example.com", "admin2@example.com"],
            service_name="Database",
            status="down",
            details="All connection attempts failed"
        )

        assert result is True
        mock_send_alert.assert_called_once()

        # Check call arguments
        call_args = mock_send_alert.call_args
        assert call_args[1]['recipients'] == ["admin1@example.com", "admin2@example.com"]
        assert "Database" in call_args[1]['subject']
        assert "DOWN" in call_args[1]['subject']
        assert call_args[1]['severity'] == AlertSeverity.CRITICAL

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_system_status_alert_high(self, mock_send_alert):
        """Test system status alert for non-critical status"""
        mock_send_alert.return_value = True

        result = EmailService.send_system_status_alert(
            admin_emails=["admin@example.com"],
            service_name="API",
            status="degraded",
            details="High latency detected"
        )

        assert result is True

        # Check severity is HIGH for non-critical statuses
        call_args = mock_send_alert.call_args
        assert call_args[1]['severity'] == AlertSeverity.HIGH

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_system_status_alert_with_context(self, mock_send_alert):
        """Test that context is included"""
        mock_send_alert.return_value = True

        result = EmailService.send_system_status_alert(
            admin_emails=["admin@example.com"],
            service_name="Cache",
            status="recovered",
            details="Service back online"
        )

        assert result is True

        # Check context
        call_args = mock_send_alert.call_args
        context = call_args[1]['context']
        assert context['service'] == "Cache"
        assert context['status'] == "recovered"
        assert context['details'] == "Service back online"
        assert 'timestamp' in context


class TestSendCommissionFailureAlert:
    """Tests for send_commission_failure_alert method"""

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_commission_failure_with_admin_email(self, mock_send_alert):
        """Test commission failure alert with provided admin email"""
        mock_send_alert.return_value = True

        # Mock asset and schedule
        mock_asset = Mock()
        mock_asset.external_id = "EXEDRA789"
        mock_asset.name = "Test Asset"
        mock_asset.control_mode = "optimise"
        mock_asset.project_id = "project1"

        mock_schedule = Mock()
        mock_schedule.schedule_id = "sched123"
        mock_schedule.created_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_schedule.last_commission_attempt = datetime(2024, 1, 1, 13, 0, 0)
        mock_schedule.commission_attempts = 5
        mock_schedule.commission_error = "Connection refused"

        mock_db = Mock()

        result = EmailService.send_commission_failure_alert(
            asset=mock_asset,
            schedule=mock_schedule,
            db_session=mock_db,
            admin_email="admin@example.com"
        )

        assert result is True
        mock_send_alert.assert_called_once()

        # Check call arguments
        call_args = mock_send_alert.call_args
        assert call_args[1]['recipients'] == ["admin@example.com"]
        assert "EXEDRA789" in call_args[1]['subject']
        assert "5 attempts" in call_args[1]['message']
        assert "Connection refused" in call_args[1]['message']

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_commission_failure_from_api_client(self, mock_send_alert):
        """Test getting admin email from API client"""
        mock_send_alert.return_value = True

        # Mock asset
        mock_asset = Mock()
        mock_asset.external_id = "EXEDRA999"
        mock_asset.name = "Another Asset"
        mock_asset.control_mode = "passthrough"
        mock_asset.project_id = "project2"

        # Mock schedule
        mock_schedule = Mock()
        mock_schedule.schedule_id = "sched456"
        mock_schedule.created_at = datetime(2024, 1, 2, 12, 0, 0)
        mock_schedule.last_commission_attempt = datetime(2024, 1, 2, 13, 0, 0)
        mock_schedule.commission_attempts = 3
        mock_schedule.commission_error = "Device not found"

        # Mock DB session and API client
        mock_api_client = Mock()
        mock_api_client.contact_email = "client@example.com"

        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = mock_api_client

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        result = EmailService.send_commission_failure_alert(
            asset=mock_asset,
            schedule=mock_schedule,
            db_session=mock_db
        )

        assert result is True

        # Check that email was sent to client contact email
        call_args = mock_send_alert.call_args
        assert call_args[1]['recipients'] == ["client@example.com"]

    def test_send_commission_failure_no_email_raises_error(self):
        """Test error when no admin email is available"""
        # Mock asset
        mock_asset = Mock()
        mock_asset.project_id = "project3"
        mock_asset.external_id = "EXEDRA111"

        # Mock schedule
        mock_schedule = Mock()

        # Mock DB session with no API client
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with pytest.raises(ValueError) as exc_info:
            EmailService.send_commission_failure_alert(
                asset=mock_asset,
                schedule=mock_schedule,
                db_session=mock_db
            )

        assert "No admin contact email found" in str(exc_info.value)
        assert "project3" in str(exc_info.value)

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_commission_failure_api_client_no_email(self, mock_send_alert):
        """Test error when API client exists but has no email"""
        # Mock asset
        mock_asset = Mock()
        mock_asset.project_id = "project4"
        mock_asset.external_id = "EXEDRA222"

        # Mock schedule
        mock_schedule = Mock()

        # Mock DB session with API client but no email
        mock_api_client = Mock()
        mock_api_client.contact_email = None

        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = mock_api_client

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with pytest.raises(ValueError) as exc_info:
            EmailService.send_commission_failure_alert(
                asset=mock_asset,
                schedule=mock_schedule,
                db_session=mock_db
            )

        assert "No admin contact email found" in str(exc_info.value)

    @patch.object(EmailService, 'send_critical_alert')
    def test_send_commission_failure_with_context(self, mock_send_alert):
        """Test that commission failure includes correct context"""
        mock_send_alert.return_value = True

        # Mock asset and schedule
        mock_asset = Mock()
        mock_asset.external_id = "EXEDRA555"
        mock_asset.name = "Context Test"
        mock_asset.control_mode = "optimise"
        mock_asset.project_id = "projectX"

        mock_schedule = Mock()
        mock_schedule.schedule_id = "schedX"
        mock_schedule.created_at = datetime(2024, 1, 3, 12, 0, 0)
        mock_schedule.last_commission_attempt = datetime(2024, 1, 3, 13, 0, 0)
        mock_schedule.commission_attempts = 7
        mock_schedule.commission_error = "Timeout after 30s"

        mock_db = Mock()

        result = EmailService.send_commission_failure_alert(
            asset=mock_asset,
            schedule=mock_schedule,
            db_session=mock_db,
            admin_email="admin@example.com"
        )

        assert result is True

        # Check context
        call_args = mock_send_alert.call_args
        context = call_args[1]['context']
        assert context['asset_external_id'] == "EXEDRA555"
        assert context['asset_name'] == "Context Test"
        assert context['schedule_id'] == "schedX"
        assert context['commission_attempts'] == 7
        assert context['commission_error'] == "Timeout after 30s"
        assert context['project_id'] == "projectX"


class TestAlertSeverity:
    """Tests for AlertSeverity enum"""

    def test_alert_severity_values(self):
        """Test all alert severity levels exist"""
        assert AlertSeverity.LOW.value == "low"
        assert AlertSeverity.MEDIUM.value == "medium"
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.CRITICAL.value == "critical"

    def test_alert_severity_comparison(self):
        """Test that severity enum can be compared"""
        assert AlertSeverity.CRITICAL in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]
        assert AlertSeverity.LOW not in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]
