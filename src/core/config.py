import os
import json
import boto3
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class AWSSecretsManager:
    """AWS Secrets Manager integration for production deployments"""

    def __init__(self, region_name: str = "ap-southeast-2"):
        self.region_name = region_name
        self._client = None

    @property
    def client(self):
        """AWS Client for Secrets Manager"""
        if self._client is None:
            self._client = boto3.client('secretsmanager', region_name=self.region_name)
        return self._client

    def get_secret(self, secret_name: str) -> dict:
        """Retrieve and parse a secret from AWS Secrets Manager"""
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve secret '{secret_name}': {e}") from e

class Settings(BaseSettings):
    # DB Settings
    DATABASE_URL: str
    DATABASE_ADMIN_URL: Optional[str] = None
    DB_POOL_SIZE: int
    DB_MAX_OVERFLOW: int

    # SMTP configuration for email sending
    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    EMAIL_FROM: str

    # Credential encryption for ClientCredential table
    CREDENTIAL_ENCRYPTION_KEY: str

    # EXEDRA SSL Configuration
    EXEDRA_VERIFY_SSL: bool

    # Application settings
    ENVIRONMENT: str
    LOG_LEVEL: str
    HOST: str
    PORT: int

    # Server configuration
    WORKERS: int
    TIMEOUT_KEEP_ALIVE: int
    TIMEOUT_GRACEFUL_SHUTDOWN: int
    MAX_REQUESTS: int
    MAX_REQUESTS_JITTER: int

    # Feature toggles
    REQUIRE_HMAC: bool

    # AWS configuration (only these get defaults since they're AWS-specific)
    AWS_REGION: str = "ap-southeast-2"  # Default region, can override in .env
    AWS_SECRET_NAME: Optional[str] = None  # Only set in production

    def __init__(self, **kwargs):
        # Load from AWS Secrets Manager if configured for production
        if os.getenv('AWS_SECRET_NAME') and os.getenv('ENVIRONMENT') == 'production':
            try:
                secrets = self._load_from_aws_secrets()
                # Update kwargs with secrets, but let .env values override if present
                for key, value in secrets.items():
                    if key not in kwargs and not os.getenv(key):
                        kwargs[key] = value
            except (boto3.exceptions.Boto3Error, json.JSONDecodeError, KeyError) as e:
                # Log error but don't fail - fall back to .env
                print(f"Warning: Failed to load AWS secrets, using .env fallback: {e}")

        super().__init__(**kwargs)

    def _load_from_aws_secrets(self) -> dict:
        """Load configuration from AWS Secrets Manager"""
        secret_name = os.getenv('AWS_SECRET_NAME')
        region = os.getenv('AWS_REGION', 'ap-southeast-2')

        secrets_manager = AWSSecretsManager(region_name=region)
        return secrets_manager.get_secret(secret_name)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
