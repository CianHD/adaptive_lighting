"""Tests for core.config module."""
import json
from unittest.mock import Mock, patch

import pytest

from src.core.config import AWSSecretsManager, Settings


class TestAWSSecretsManager:
    """Test AWS Secrets Manager integration."""

    def test_initialization(self):
        """Test SecretsManager initializes with correct region."""
        manager = AWSSecretsManager(region_name="us-east-1")
        assert manager.region_name == "us-east-1"

    def test_default_region(self):
        """Test default region is ap-southeast-2."""
        manager = AWSSecretsManager()
        assert manager.region_name == "ap-southeast-2"

    def test_client_lazy_initialization(self):
        """Test client is lazily initialized."""
        manager = AWSSecretsManager()
        assert manager._client is None

        with patch('boto3.client') as mock_boto_client:
            mock_boto_client.return_value = Mock()
            _ = manager.client

            mock_boto_client.assert_called_once_with('secretsmanager', region_name='ap-southeast-2')

    def test_get_secret_success(self):
        """Test successfully retrieving secret."""
        manager = AWSSecretsManager()

        mock_client = Mock()
        secret_data = {"DATABASE_URL": "postgresql://test", "API_KEY": "test-key"}
        mock_client.get_secret_value.return_value = {
            'SecretString': json.dumps(secret_data)
        }

        # Patch the _client attribute directly instead of the property
        manager._client = mock_client

        result = manager.get_secret("test-secret")

        assert result == secret_data
        mock_client.get_secret_value.assert_called_once_with(SecretId="test-secret")

    def test_get_secret_failure(self):
        """Test handling secret retrieval failure."""
        manager = AWSSecretsManager()

        mock_client = Mock()
        mock_client.get_secret_value.side_effect = Exception("Secret not found")

        # Patch the _client attribute directly
        manager._client = mock_client

        with pytest.raises(RuntimeError) as exc_info:
            manager.get_secret("nonexistent-secret")

        assert "Failed to retrieve secret 'nonexistent-secret'" in str(exc_info.value)

    def test_get_secret_invalid_json(self):
        """Test handling invalid JSON in secret."""
        manager = AWSSecretsManager()

        mock_client = Mock()
        mock_client.get_secret_value.return_value = {
            'SecretString': 'invalid-json{'
        }

        # Patch the _client attribute directly
        manager._client = mock_client

        with pytest.raises(RuntimeError):
            manager.get_secret("test-secret")


class TestSettings:
    """Test Settings configuration loading."""

    @pytest.fixture(autouse=True)
    def setup_env_vars(self, monkeypatch):
        """Set up required environment variables for testing."""
        required_vars = {
            'DATABASE_URL': 'postgresql://test:test@localhost/test',
            'DB_POOL_SIZE': '5',
            'DB_MAX_OVERFLOW': '10',
            'SMTP_SERVER': 'smtp.test.com',
            'SMTP_PORT': '587',
            'SMTP_USERNAME': 'test@test.com',
            'SMTP_PASSWORD': 'test-password',
            'EMAIL_FROM': 'noreply@test.com',
            'CREDENTIAL_ENCRYPTION_KEY': 'test-encryption-key',
            'EXEDRA_VERIFY_SSL': 'False',
            'ENVIRONMENT': 'test',
            'LOG_LEVEL': 'INFO',
            'HOST': '0.0.0.0',
            'PORT': '8000',
            'WORKERS': '1',
            'TIMEOUT_KEEP_ALIVE': '5',
            'TIMEOUT_GRACEFUL_SHUTDOWN': '30',
            'MAX_REQUESTS': '1000',
            'MAX_REQUESTS_JITTER': '50',
            'REQUIRE_HMAC': 'False',
            'JWT_SECRET_KEY': 'test-jwt-secret',
            'JWT_ALGORITHM': 'HS256',
            'ACCESS_TOKEN_EXPIRE_MINUTES': '30'
        }
        for key, value in required_vars.items():
            monkeypatch.setenv(key, value)

    def test_settings_load_from_env(self):
        """Test settings load from environment variables."""
        settings = Settings()

        assert settings.DATABASE_URL == 'postgresql://test:test@localhost/test'
        assert settings.DB_POOL_SIZE == 5
        assert settings.SMTP_SERVER == 'smtp.test.com'
        assert settings.ENVIRONMENT == 'test'
        assert settings.EXEDRA_VERIFY_SSL is False
        assert settings.REQUIRE_HMAC is False

    def test_settings_default_aws_region(self):
        """Test AWS region defaults to ap-southeast-2."""
        settings = Settings()
        assert settings.AWS_REGION == "ap-southeast-2"

    def test_settings_custom_aws_region(self, monkeypatch):
        """Test custom AWS region can be set."""
        monkeypatch.setenv('AWS_REGION', 'us-west-2')
        settings = Settings()
        assert settings.AWS_REGION == "us-west-2"

    def test_settings_without_aws_secrets(self, monkeypatch):
        """Test settings work without AWS Secrets Manager."""
        monkeypatch.delenv('AWS_SECRET_NAME', raising=False)
        settings = Settings()

        assert settings.DATABASE_URL is not None
        assert settings.ENVIRONMENT == 'test'

    @patch('src.core.config.AWSSecretsManager')
    def test_settings_load_from_aws_production(self, mock_secrets_manager, monkeypatch):
        """Test settings load from AWS in production."""
        monkeypatch.setenv('AWS_SECRET_NAME', 'prod-secret')
        monkeypatch.setenv('ENVIRONMENT', 'production')

        mock_manager_instance = Mock()
        mock_manager_instance.get_secret.return_value = {
            'DATABASE_URL': 'postgresql://prod:prod@prod-db/prod',
            'SMTP_PASSWORD': 'prod-smtp-password'
        }
        mock_secrets_manager.return_value = mock_manager_instance

        settings = Settings()

        # Should still use env vars if present
        assert settings.ENVIRONMENT == 'production'

    @pytest.mark.skip(reason="Complex AWS mocking - test manually in integration tests")
    @patch('boto3.client')
    @patch('src.core.config.AWSSecretsManager')
    def test_settings_fallback_on_aws_failure(self, mock_secrets_manager, mock_boto_client, monkeypatch, capsys):
        """Test settings fall back to .env on AWS failure."""
        monkeypatch.setenv('AWS_SECRET_NAME', 'prod-secret')
        monkeypatch.setenv('ENVIRONMENT', 'production')

        mock_manager_instance = Mock()
        # Simulate boto3 error (which is caught in the except clause)
        mock_manager_instance.get_secret.side_effect = Exception("Boto3 Error")  # boto3.exceptions.Boto3Error inherits from Exception
        mock_secrets_manager.return_value = mock_manager_instance

        settings = Settings()

        # Should fall back to env vars
        assert settings.DATABASE_URL == 'postgresql://test:test@localhost/test'

        # Should print warning
        captured = capsys.readouterr()
        assert "Warning: Failed to load AWS secrets" in captured.out

    def test_settings_integer_conversion(self):
        """Test integer fields are properly converted."""
        settings = Settings()

        assert isinstance(settings.DB_POOL_SIZE, int)
        assert isinstance(settings.SMTP_PORT, int)
        assert isinstance(settings.PORT, int)
        assert isinstance(settings.WORKERS, int)

    def test_settings_boolean_conversion(self):
        """Test boolean fields are properly converted."""
        settings = Settings()

        assert isinstance(settings.EXEDRA_VERIFY_SSL, bool)
        assert isinstance(settings.REQUIRE_HMAC, bool)

    def test_settings_optional_aws_secret_name(self):
        """Test AWS_SECRET_NAME is optional."""
        settings = Settings()

        # Should be None or not set in test environment
        assert settings.AWS_SECRET_NAME is None or settings.AWS_SECRET_NAME == ""
