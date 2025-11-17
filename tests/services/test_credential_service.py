"""Tests for services.credential_service module."""
import uuid
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import SQLAlchemyError

from src.services.credential_service import CredentialService
from src.db.models import ClientCredential, ApiClient, Project


class TestCredentialServiceEncryption:
    """Test credential encryption/decryption."""

    def test_initialization_with_env_key(self, monkeypatch):
        """Test service initializes with environment key."""
        test_key = Fernet.generate_key().decode()
        monkeypatch.setenv('CREDENTIAL_ENCRYPTION_KEY', test_key)

        service = CredentialService()

        assert service.encryption_key == test_key.encode()
        assert service.cipher is not None

    def test_initialization_generates_key_if_missing(self, monkeypatch):
        """Test service generates key if env var missing."""
        monkeypatch.delenv('CREDENTIAL_ENCRYPTION_KEY', raising=False)

        service = CredentialService()

        assert service.encryption_key is not None
        assert len(service.encryption_key) > 0

    def test_encrypt_credential(self):
        """Test encrypting a credential."""
        service = CredentialService()
        plaintext = "my-secret-token"

        encrypted = service.encrypt_credential(plaintext)

        assert encrypted != plaintext
        assert len(encrypted) > 0
        assert isinstance(encrypted, str)

    def test_decrypt_credential(self):
        """Test decrypting a credential."""
        service = CredentialService()
        plaintext = "my-secret-token"
        encrypted = service.encrypt_credential(plaintext)

        decrypted = service.decrypt_credential(encrypted)

        assert decrypted == plaintext

    def test_encrypt_decrypt_roundtrip(self):
        """Test encrypt -> decrypt returns original value."""
        service = CredentialService()
        original = "test-api-key-12345"

        encrypted = service.encrypt_credential(original)
        decrypted = service.decrypt_credential(encrypted)

        assert decrypted == original

    def test_different_instances_same_key(self, monkeypatch):
        """Test different service instances with same key can decrypt."""
        test_key = Fernet.generate_key().decode()
        monkeypatch.setenv('CREDENTIAL_ENCRYPTION_KEY', test_key)

        service1 = CredentialService()
        service2 = CredentialService()

        plaintext = "shared-secret"
        encrypted = service1.encrypt_credential(plaintext)
        decrypted = service2.decrypt_credential(encrypted)

        assert decrypted == plaintext

    def test_decrypt_invalid_value_raises_error(self):
        """Test decrypting invalid value raises error."""
        service = CredentialService()

        with pytest.raises(Exception):  # Fernet raises various exceptions
            service.decrypt_credential("invalid-encrypted-value")

    def test_encrypt_empty_string(self):
        """Test encrypting empty string."""
        service = CredentialService()

        encrypted = service.encrypt_credential("")
        decrypted = service.decrypt_credential(encrypted)

        assert decrypted == ""

    def test_encrypt_unicode_string(self):
        """Test encrypting unicode characters."""
        service = CredentialService()
        plaintext = "🔐 secret-密码"

        encrypted = service.encrypt_credential(plaintext)
        decrypted = service.decrypt_credential(encrypted)

        assert decrypted == plaintext


class TestStoreCredential:
    """Test storing credentials in database."""

    def test_store_new_credential(self, db_session):
        """Test storing a new credential."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        credential = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="my-token-value",
            environment="prod",
            db=db_session
        )

        assert credential.credential_id is not None
        assert credential.service_name == "exedra"
        assert credential.credential_type == "api_token"
        assert credential.environment == "prod"
        assert credential.is_active is True
        assert credential.encrypted_value != "my-token-value"

    def test_store_credential_deactivates_existing(self, db_session):
        """Test storing new credential deactivates existing one."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Store first credential
        cred1 = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="old-token",
            environment="prod",
            db=db_session
        )

        # Store second credential (same type)
        cred2 = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="new-token",
            environment="prod",
            db=db_session
        )

        db_session.refresh(cred1)

        assert cred1.is_active is False
        assert cred2.is_active is True

    def test_store_credential_different_environments(self, db_session):
        """Test storing credentials for different environments keeps both active."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        prod_cred = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="prod-token",
            environment="prod",
            db=db_session
        )

        test_cred = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="test-token",
            environment="test",
            db=db_session
        )

        assert prod_cred.is_active is True
        assert test_cred.is_active is True

    def test_store_credential_no_autocommit(self, db_session):
        """Test storing credential without auto-commit."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        credential = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="my-token",
            environment="prod",
            db=db_session,
            auto_commit=False
        )

        # Should be in session but not committed
        assert credential in db_session.new

        db_session.commit()
        assert credential.credential_id is not None

    def test_store_credential_rollback_on_error(self, db_session):
        """Test credential storage rolls back on error with auto_commit."""
        project = Project(code="TEST-001", name="Test Project")
        db_session.add(project)
        db_session.commit()

        api_client = ApiClient(
            project_id=project.project_id,
            name="Test Client",
            status="active"
        )
        db_session.add(api_client)
        db_session.commit()

        with patch.object(db_session, 'commit', side_effect=SQLAlchemyError("DB Error")):
            with pytest.raises(RuntimeError):
                CredentialService.store_credential(
                    api_client_id=api_client.api_client_id,
                    service_name="exedra",
                    credential_type="api_token",
                    value="my-token",
                    environment="prod",
                    db=db_session,
                    auto_commit=True
                )


class TestGetCredential:
    """Test retrieving credentials."""

    def test_get_credential_by_type(self, db_session):
        """Test retrieving credential by type."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Store credential
        stored = CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="my-secret-token",
            environment="prod",
            db=db_session
        )
        assert stored.is_active is True

        # Retrieve credential
        retrieved = CredentialService.get_credential_by_type(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            environment="prod",
            db=db_session
        )

        assert retrieved == "my-secret-token"

    def test_get_credential_not_found(self, db_session):
        """Test retrieving non-existent credential returns None."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        result = CredentialService.get_credential_by_type(
            api_client_id=api_client_id,
            service_name="nonexistent",
            credential_type="api_token",
            environment="prod",
            db=db_session
        )

        assert result is None

    def test_get_credential_only_active(self, db_session):
        """Test only active credentials are retrieved."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Store and deactivate old credential
        service = CredentialService()
        old_cred = ClientCredential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            encrypted_value=service.encrypt_credential("old-token"),
            environment="prod",
            is_active=False
        )
        db_session.add(old_cred)
        db_session.commit()

        result = CredentialService.get_credential_by_type(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            environment="prod",
            db=db_session
        )

        assert result is None


class TestGetExedraConfig:
    """Test getting EXEDRA configuration."""

    def test_get_exedra_config_success(self, db_session):
        """Test retrieving EXEDRA token and base URL."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Store token and base URL
        CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="api_token",
            value="my-exedra-token",
            environment="prod",
            db=db_session
        )

        CredentialService.store_credential(
            api_client_id=api_client_id,
            service_name="exedra",
            credential_type="base_url",
            value="https://exedra.example.com",
            environment="prod",
            db=db_session
        )

        config = CredentialService.get_exedra_config(
            api_client=api_client,
            db=db_session,
            environment="prod"
        )

        assert config["token"] == "my-exedra-token"
        assert config["base_url"] == "https://exedra.example.com"

    def test_get_exedra_config_missing(self, db_session):
        """Test getting EXEDRA config when not configured."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        config = CredentialService.get_exedra_config(
            api_client=api_client,
            db=db_session,
            environment="prod"
        )

        assert config["token"] is None
        assert config["base_url"] is None


class TestStoreExedraConfig:
    """Test storing EXEDRA configuration."""

    def test_store_exedra_config_success(self, db_session):
        """Test storing EXEDRA token and base URL as atomic operation."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Store both credentials together
        token_cred, url_cred = CredentialService.store_exedra_config(
            api_client=api_client,
            api_token="my-exedra-token",
            base_url="https://exedra.example.com",
            environment="prod",
            db=db_session
        )

        # Both should be stored and active
        assert token_cred.credential_type == "api_token"
        assert token_cred.is_active is True
        assert url_cred.credential_type == "base_url"
        assert url_cred.is_active is True

        # Verify they're retrievable
        config = CredentialService.get_exedra_config(
            api_client=api_client,
            db=db_session,
            environment="prod"
        )
        assert config["token"] == "my-exedra-token"
        assert config["base_url"] == "https://exedra.example.com"

    def test_store_exedra_config_replaces_existing(self, db_session):
        """Test that storing new config deactivates old credentials."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Store initial config
        CredentialService.store_exedra_config(
            api_client=api_client,
            api_token="old-token",
            base_url="https://old.example.com",
            environment="prod",
            db=db_session
        )

        # Store new config
        token_cred, url_cred = CredentialService.store_exedra_config(
            api_client=api_client,
            api_token="new-token",
            base_url="https://new.example.com",
            environment="prod",
            db=db_session
        )
        assert token_cred.is_active is True
        assert url_cred.is_active is True

        # New credentials should be active
        config = CredentialService.get_exedra_config(
            api_client=api_client,
            db=db_session,
            environment="prod"
        )
        assert config["token"] == "new-token"
        assert config["base_url"] == "https://new.example.com"

        # Old credentials should be deactivated
        old_creds = db_session.query(ClientCredential).filter_by(
            api_client_id=api_client_id,
            service_name="exedra",
            is_active=False
        ).all()
        assert len(old_creds) == 2  # Both old token and URL

    def test_store_exedra_config_rollback_on_error(self, db_session):
        """Test that transaction is rolled back if either credential fails."""
        project_id = str(uuid.uuid4())
        api_client_id = str(uuid.uuid4())

        project = Project(project_id=project_id, code="TEST-001", name="Test Project")
        api_client = ApiClient(
            api_client_id=api_client_id,
            project_id=project_id,
            name="Test Client",
            status="active"
        )
        db_session.add_all([project, api_client])
        db_session.commit()

        # Mock db.commit to raise an error
        original_commit = db_session.commit

        def failing_commit():
            raise SQLAlchemyError("Database error")

        db_session.commit = failing_commit

        # Should raise RuntimeError and rollback
        with pytest.raises(RuntimeError) as exc_info:
            CredentialService.store_exedra_config(
                api_client=api_client,
                api_token="test-token",
                base_url="https://test.example.com",
                environment="prod",
                db=db_session
            )

        assert "Failed to store EXEDRA config" in str(exc_info.value)
        assert "transaction rolled back" in str(exc_info.value)

        # Restore original commit
        db_session.commit = original_commit

        # Verify no partial data was committed
        creds = db_session.query(ClientCredential).filter_by(
            api_client_id=api_client_id
        ).all()
        assert len(creds) == 0
