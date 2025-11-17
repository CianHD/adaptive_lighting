"""Tests for ScopeService."""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from src.services.scope_service import ScopeService
from src.db.models import ScopeCatalogue


@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def mock_scope_catalogue():
    """Mock scope catalogue entries."""
    scopes = []

    # Asset scopes
    scope1 = Mock(spec=ScopeCatalogue)
    scope1.scope_code = "asset:read"
    scope1.description = "Read asset state"
    scope1.category = "asset"
    scopes.append(scope1)

    scope2 = Mock(spec=ScopeCatalogue)
    scope2.scope_code = "asset:metadata"
    scope2.description = "Read asset metadata"
    scope2.category = "asset"
    scopes.append(scope2)

    # Sensor scopes
    scope3 = Mock(spec=ScopeCatalogue)
    scope3.scope_code = "sensor:read"
    scope3.description = "Read sensor state"
    scope3.category = "sensor"
    scopes.append(scope3)

    # Admin scopes
    scope4 = Mock(spec=ScopeCatalogue)
    scope4.scope_code = "admin:policy:read"
    scope4.description = "Read policies"
    scope4.category = "admin"
    scopes.append(scope4)

    return scopes


class TestGetAllScopes:
    """Tests for get_all_scopes method"""

    def test_get_all_scopes_from_database(self, mock_db, mock_scope_catalogue):
        """Test retrieving scopes from database."""
        mock_db.query.return_value.all.return_value = mock_scope_catalogue

        result = ScopeService.get_all_scopes(db=mock_db)

        assert len(result) == 4
        assert "asset:read" in result
        assert result["asset:read"]["description"] == "Read asset state"
        assert result["asset:read"]["category"] == "asset"
        mock_db.query.assert_called_once()

    def test_get_all_scopes_without_database(self):
        """Test fallback to static definitions when no DB session."""
        result = ScopeService.get_all_scopes(db=None)

        assert isinstance(result, dict)
        assert len(result) > 0
        assert "asset:read" in result
        assert "sensor:ingest" in result
        assert "admin:policy:read" in result
        # Verify structure
        assert "description" in result["asset:read"]
        assert "category" in result["asset:read"]


class TestGetScopesByCategory:
    """Tests for get_scopes_by_category method"""

    def test_get_asset_scopes_from_database(self, mock_db, mock_scope_catalogue):
        """Test retrieving asset scopes from database."""
        asset_scopes = [s for s in mock_scope_catalogue if s.category == "asset"]
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = asset_scopes
        mock_db.query.return_value = mock_query

        result = ScopeService.get_scopes_by_category(category="asset", db=mock_db)

        assert len(result) == 2
        assert "asset:read" in result
        assert "asset:metadata" in result
        assert "sensor:read" not in result

    def test_get_sensor_scopes_without_database(self):
        """Test fallback to static definitions for sensor category."""
        result = ScopeService.get_scopes_by_category(category="sensor", db=None)

        assert isinstance(result, dict)
        assert len(result) > 0
        assert "sensor:read" in result
        assert "sensor:ingest" in result
        # Verify no asset scopes
        assert "asset:read" not in result
        # Verify all returned scopes are sensor category
        for scope_details in result.values():
            assert scope_details["category"] == "sensor"

    def test_get_admin_scopes_from_database(self, mock_db, mock_scope_catalogue):
        """Test retrieving admin scopes from database."""
        admin_scopes = [s for s in mock_scope_catalogue if s.category == "admin"]
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = admin_scopes
        mock_db.query.return_value = mock_query

        result = ScopeService.get_scopes_by_category(category="admin", db=mock_db)

        assert len(result) == 1
        assert "admin:policy:read" in result


class TestValidateScopes:
    """Tests for validate_scopes method"""

    def test_validate_all_valid_scopes_with_database(self, mock_db, mock_scope_catalogue):
        """Test validation with all valid scopes from database."""
        mock_db.query.return_value.all.return_value = mock_scope_catalogue

        scopes_to_validate = ["asset:read", "sensor:read"]
        is_valid, invalid = ScopeService.validate_scopes(scopes_to_validate, db=mock_db)

        assert is_valid is True
        assert invalid == []

    def test_validate_with_invalid_scopes_from_database(self, mock_db, mock_scope_catalogue):
        """Test validation with some invalid scopes from database."""
        mock_db.query.return_value.all.return_value = mock_scope_catalogue

        scopes_to_validate = ["asset:read", "invalid:scope", "another:invalid"]
        is_valid, invalid = ScopeService.validate_scopes(scopes_to_validate, db=mock_db)

        assert is_valid is False
        assert len(invalid) == 2
        assert "invalid:scope" in invalid
        assert "another:invalid" in invalid

    def test_validate_all_valid_scopes_without_database(self):
        """Test validation with all valid scopes using static definitions."""
        scopes_to_validate = ["asset:read", "sensor:ingest", "admin:policy:read"]
        is_valid, invalid = ScopeService.validate_scopes(scopes_to_validate, db=None)

        assert is_valid is True
        assert invalid == []

    def test_validate_with_invalid_scopes_without_database(self):
        """Test validation with invalid scopes using static definitions."""
        scopes_to_validate = ["asset:read", "not:valid", "sensor:fake"]
        is_valid, invalid = ScopeService.validate_scopes(scopes_to_validate, db=None)

        assert is_valid is False
        assert len(invalid) == 2
        assert "not:valid" in invalid
        assert "sensor:fake" in invalid

    def test_validate_empty_scope_list(self, mock_db):
        """Test validation with empty scope list."""
        mock_db.query.return_value.all.return_value = []

        is_valid, invalid = ScopeService.validate_scopes([], db=mock_db)

        assert is_valid is True
        assert invalid == []


class TestGetValidScopeCodes:
    """Tests for get_valid_scope_codes method"""

    def test_get_valid_scope_codes(self, mock_db, mock_scope_catalogue):
        """Test retrieving valid scope codes from database."""
        mock_db.query.return_value.all.return_value = mock_scope_catalogue

        result = ScopeService.get_valid_scope_codes(db=mock_db)

        assert isinstance(result, set)
        assert len(result) == 4
        assert "asset:read" in result
        assert "sensor:read" in result
        assert "admin:policy:read" in result


class TestGetRecommendedScopes:
    """Tests for get_recommended_scopes method"""

    def test_get_recommended_scopes_structure(self):
        """Test recommended scopes returns proper structure."""
        result = ScopeService.get_recommended_scopes()

        assert isinstance(result, dict)
        assert len(result) > 0
        # Check specific recommendations exist
        assert "asset_readonly" in result
        assert "sensor_client" in result
        assert "system_admin" in result

    def test_asset_readonly_recommendation(self):
        """Test asset readonly recommendation."""
        result = ScopeService.get_recommended_scopes()

        asset_readonly = result["asset_readonly"]
        assert isinstance(asset_readonly, list)
        assert "asset:read" in asset_readonly

    def test_asset_full_control_recommendation(self):
        """Test asset full control recommendation."""
        result = ScopeService.get_recommended_scopes()

        asset_full = result["asset_full_control"]
        assert isinstance(asset_full, list)
        assert "asset:read" in asset_full
        assert "asset:metadata" in asset_full
        assert "asset:create" in asset_full
        assert "asset:update" in asset_full
        assert "asset:delete" in asset_full
        assert "asset:command" in asset_full

    def test_sensor_client_recommendation(self):
        """Test sensor client recommendation."""
        result = ScopeService.get_recommended_scopes()

        sensor_client = result["sensor_client"]
        assert "sensor:read" in sensor_client
        assert "sensor:ingest" in sensor_client

    def test_integration_service_recommendation(self):
        """Test integration service recommendation."""
        result = ScopeService.get_recommended_scopes()

        integration = result["integration_service"]
        assert "asset:read" in integration
        assert "asset:command" in integration
        assert "sensor:read" in integration
        assert "sensor:ingest" in integration


class TestSyncCatalogueToDatabase:
    """Tests for sync_catalogue_to_database method"""

    def test_sync_new_scopes_to_empty_database(self, mock_db):
        """Test syncing scopes to empty database."""
        # Mock empty database
        mock_db.query.return_value.filter.return_value.first.return_value = None

        count = ScopeService.sync_catalogue_to_database(db=mock_db)

        # Should have added all scopes from SCOPE_DEFINITIONS
        expected_count = len(ScopeService.SCOPE_DEFINITIONS)
        assert count == expected_count
        assert mock_db.add.call_count == expected_count
        mock_db.commit.assert_called_once()

    def test_sync_updates_existing_scopes(self, mock_db):
        """Test syncing updates existing scopes."""
        # Mock existing scope
        existing_scope = Mock(spec=ScopeCatalogue)
        existing_scope.scope_code = "asset:read"
        existing_scope.description = "Old description"
        existing_scope.category = "asset"

        mock_db.query.return_value.filter.return_value.first.return_value = existing_scope

        count = ScopeService.sync_catalogue_to_database(db=mock_db)

        # Should not add any new scopes (all exist)
        assert count == 0
        # Should have updated existing scopes
        assert existing_scope.description != "Old description"
        mock_db.commit.assert_called_once()

    def test_sync_mixed_new_and_existing_scopes(self, mock_db):
        """Test syncing with mix of new and existing scopes."""
        call_count = 0

        def mock_first():
            nonlocal call_count
            call_count += 1
            # Return existing scope for first 3 calls, None for rest
            if call_count <= 3:
                scope = Mock(spec=ScopeCatalogue)
                scope.description = "Old"
                scope.category = "old"
                return scope
            return None

        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first

        count = ScopeService.sync_catalogue_to_database(db=mock_db)

        # Should have added scopes after the first 3
        expected_new = len(ScopeService.SCOPE_DEFINITIONS) - 3
        assert count == expected_new
        mock_db.commit.assert_called_once()


class TestScopeDefinitions:
    """Tests for SCOPE_DEFINITIONS structure"""

    def test_scope_definitions_exist(self):
        """Test that scope definitions are defined."""
        assert hasattr(ScopeService, 'SCOPE_DEFINITIONS')
        assert isinstance(ScopeService.SCOPE_DEFINITIONS, dict)
        assert len(ScopeService.SCOPE_DEFINITIONS) > 0

    def test_all_scopes_have_required_fields(self):
        """Test that all scope definitions have required fields."""
        for scope_code, details in ScopeService.SCOPE_DEFINITIONS.items():
            assert "description" in details, f"{scope_code} missing description"
            assert "category" in details, f"{scope_code} missing category"
            assert isinstance(details["description"], str)
            assert isinstance(details["category"], str)

    def test_scope_categories_are_valid(self):
        """Test that all scopes use valid categories."""
        valid_categories = {"asset", "sensor", "admin"}

        for scope_code, details in ScopeService.SCOPE_DEFINITIONS.items():
            category = details["category"]
            assert category in valid_categories, f"{scope_code} has invalid category: {category}"

    def test_asset_scopes_exist(self):
        """Test that expected asset scopes exist."""
        expected_asset_scopes = [
            "asset:read", "asset:metadata", "asset:create",
            "asset:update", "asset:delete", "asset:command"
        ]

        for scope in expected_asset_scopes:
            assert scope in ScopeService.SCOPE_DEFINITIONS
            assert ScopeService.SCOPE_DEFINITIONS[scope]["category"] == "asset"

    def test_sensor_scopes_exist(self):
        """Test that expected sensor scopes exist."""
        expected_sensor_scopes = [
            "sensor:read", "sensor:metadata", "sensor:create",
            "sensor:update", "sensor:delete", "sensor:ingest"
        ]

        for scope in expected_sensor_scopes:
            assert scope in ScopeService.SCOPE_DEFINITIONS
            assert ScopeService.SCOPE_DEFINITIONS[scope]["category"] == "sensor"

    def test_admin_scopes_exist(self):
        """Test that expected admin scopes exist."""
        expected_admin_scopes = [
            "admin:policy:read", "admin:policy:create", "admin:policy:update",
            "admin:killswitch", "admin:audit", "admin:credentials"
        ]

        for scope in expected_admin_scopes:
            assert scope in ScopeService.SCOPE_DEFINITIONS
            assert ScopeService.SCOPE_DEFINITIONS[scope]["category"] == "admin"
