import os
from typing import Optional
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.db.models import ClientCredential, ApiClient


class CredentialService:
    """Service for managing encrypted client credentials"""

    def __init__(self):
        # In production, this should come from a secure key management service
        self.encryption_key = os.getenv('CREDENTIAL_ENCRYPTION_KEY')
        if not self.encryption_key:
            # Generate a key for development - in production this should be managed securely
            self.encryption_key = Fernet.generate_key()

        if isinstance(self.encryption_key, str):
            self.encryption_key = self.encryption_key.encode()

        self.cipher = Fernet(self.encryption_key)

    def encrypt_credential(self, value: str) -> str:
        """Encrypt a credential value"""
        return self.cipher.encrypt(value.encode()).decode()

    def decrypt_credential(self, encrypted_value: str) -> str:
        """Decrypt a credential value"""
        return self.cipher.decrypt(encrypted_value.encode()).decode()

    @staticmethod
    def store_credential(
        api_client_id: str,
        service_name: str,
        credential_type: str,
        value: str,
        environment: str = "prod",
        db: Session = None
    ) -> ClientCredential:
        """
        Store an encrypted credential for a client
        
        Args:
            api_client_id: ID of the API client
            service_name: Name of the service (e.g., 'exedra')
            credential_type: Type of credential (e.g., 'api_key')
            value: The credential value to encrypt
            environment: Environment (prod, test, staging)
            db: Database session
            
        Returns:
            Created ClientCredential record
        """
        service = CredentialService()
        encrypted_value = service.encrypt_credential(value)

        # Deactivate any existing credentials for this service/environment
        existing = db.query(ClientCredential).filter(
            and_(
                ClientCredential.api_client_id == api_client_id,
                ClientCredential.service_name == service_name,
                ClientCredential.environment == environment,
                ClientCredential.is_active == True
            )
        ).all()

        for cred in existing:
            cred.is_active = False

        # Create new credential
        credential = ClientCredential(
            api_client_id=api_client_id,
            service_name=service_name,
            credential_type=credential_type,
            encrypted_value=encrypted_value,
            environment=environment,
            is_active=True
        )

        db.add(credential)
        db.commit()

        return credential

    @staticmethod
    def get_credential_by_type(
        api_client_id: str,
        service_name: str,
        credential_type: str,
        environment: str = "prod",
        db: Session = None
    ) -> Optional[str]:
        """
        Retrieve and decrypt a specific type of credential for a client
        
        Args:
            api_client_id: ID of the API client
            service_name: Name of the service (e.g., 'exedra')
            credential_type: Type of credential (e.g., 'api_token', 'base_url')
            environment: Environment (prod, test, staging)
            db: Database session
            
        Returns:
            Decrypted credential value or None if not found
        """
        credential = db.query(ClientCredential).filter(
            and_(
                ClientCredential.api_client_id == api_client_id,
                ClientCredential.service_name == service_name,
                ClientCredential.credential_type == credential_type,
                ClientCredential.environment == environment,
                ClientCredential.is_active == True
            )
        ).first()

        if not credential:
            return None

        service = CredentialService()
        return service.decrypt_credential(credential.encrypted_value)

    @staticmethod
    def get_exedra_config(api_client: ApiClient, db: Session, environment: str = "prod") -> dict:
        """
        Get both EXEDRA API token and base URL for a client
        
        Args:
            api_client: ApiClient instance
            db: Database session
            environment: Environment (prod, test, staging)
            
        Returns:
            Dictionary with 'token' and 'base_url' keys, or empty dict if not found
        """
        token = CredentialService.get_credential_by_type(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="api_token",
            environment=environment,
            db=db
        )

        base_url = CredentialService.get_credential_by_type(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="base_url",
            environment=environment,
            db=db
        )

        return {
            "token": token,
            "base_url": base_url
        }

    @staticmethod
    def store_exedra_config(
        api_client: ApiClient,
        api_token: str,
        base_url: str,
        db: Session,
        environment: str = "prod"
    ) -> tuple[ClientCredential, ClientCredential]:
        """
        Store both EXEDRA API token and base URL for a client
        
        Args:
            api_client: ApiClient instance
            api_token: EXEDRA API token
            base_url: EXEDRA base URL
            db: Database session
            environment: Environment (prod, test, staging)
            
        Returns:
            Tuple of (token_credential, url_credential)
        """
        token_cred = CredentialService.store_credential(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value=api_token,
            environment=environment,
            db=db
        )

        url_cred = CredentialService.store_credential(
            api_client_id=api_client.api_client_id,
            service_name="exedra",
            credential_type="base_url",
            value=base_url,
            environment=environment,
            db=db
        )

        return token_cred, url_cred
