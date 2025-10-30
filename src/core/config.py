from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # DB Settings
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # SMTP configuration for email sending
    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    EMAIL_FROM: str

    # Credential encryption for ClientCredential table
    CREDENTIAL_ENCRYPTION_KEY: str

    # EXEDRA SSL Configuration
    EXEDRA_VERIFY_SSL: bool = True

    # Application settings
    ENVIRONMENT: str = "development"

    # Feature toggles
    REQUIRE_HMAC: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
