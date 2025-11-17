"""
Tests for commission processing service
"""
from unittest.mock import Mock, patch
from sqlalchemy.exc import SQLAlchemyError

import pytest

from src.services.commission_processing_service import (
    CommissionProcessingService,
    run_commission_processing
)


class TestCommissionProcessingServiceInit:
    """Tests for CommissionProcessingService initialization"""

    def test_init_with_session(self):
        """Test initialization with provided session"""
        mock_session = Mock()

        service = CommissionProcessingService(db_session=mock_session)

        assert service.db_session == mock_session
        assert service._session_maker is None

    def test_init_without_session(self):
        """Test initialization without session creates session maker"""
        service = CommissionProcessingService()

        assert service.db_session is None
        assert service._session_maker is not None


class TestProcessAllPendingCommissions:
    """Tests for process_all_pending_commissions method"""

    @pytest.mark.asyncio
    @patch.object(CommissionProcessingService, '_process_with_session')
    async def test_process_all_with_provided_session(self, mock_process):
        """Test processing with provided session"""
        mock_session = Mock()
        mock_process.return_value = {
            "success": True,
            "duration_seconds": 5.2
        }

        service = CommissionProcessingService(db_session=mock_session)
        result = await service.process_all_pending_commissions(max_concurrent=5)

        assert result["success"] is True
        mock_process.assert_called_once_with(mock_session, 5)

    @pytest.mark.asyncio
    @patch.object(CommissionProcessingService, '_process_with_session')
    async def test_process_all_without_session(self, mock_process):
        """Test processing creates new session when none provided"""
        mock_process.return_value = {
            "success": True,
            "duration_seconds": 3.1
        }

        service = CommissionProcessingService()
        result = await service.process_all_pending_commissions(max_concurrent=10)

        assert result["success"] is True
        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_all_handles_database_error(self):
        """Test handling of SQLAlchemy errors"""
        mock_session = Mock()
        mock_session.query.side_effect = SQLAlchemyError("Database connection failed")

        service = CommissionProcessingService(db_session=mock_session)

        with patch.object(service, '_process_with_session', side_effect=SQLAlchemyError("Connection error")):
            result = await service.process_all_pending_commissions()

        assert result["success"] is False
        assert "Database error" in result["error"]
        assert "start_time" in result
        assert "end_time" in result


class TestProcessWithSession:
    """Tests for _process_with_session method"""

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.process_pending_commissions')
    async def test_process_with_session_success(self, mock_process_pending):
        """Test successful processing"""
        mock_process_pending.return_value = None
        mock_session = Mock()

        service = CommissionProcessingService()
        result = await service._process_with_session(mock_session, max_concurrent=8)

        assert result["success"] is True
        assert result["max_concurrent"] == 8
        assert "duration_seconds" in result
        assert "start_time" in result
        assert "end_time" in result
        mock_process_pending.assert_called_once_with(db=mock_session, max_concurrent=8)

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.process_pending_commissions')
    async def test_process_with_session_handles_value_error(self, mock_process_pending):
        """Test handling of ValueError"""
        mock_process_pending.side_effect = ValueError("Invalid configuration")
        mock_session = Mock()

        service = CommissionProcessingService()
        result = await service._process_with_session(mock_session, max_concurrent=5)

        assert result["success"] is False
        assert "Invalid configuration" in result["error"]

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.process_pending_commissions')
    async def test_process_with_session_handles_runtime_error(self, mock_process_pending):
        """Test handling of RuntimeError"""
        mock_process_pending.side_effect = RuntimeError("Processing failed")
        mock_session = Mock()

        service = CommissionProcessingService()
        result = await service._process_with_session(mock_session, max_concurrent=3)

        assert result["success"] is False
        assert "Processing failed" in result["error"]

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.process_pending_commissions')
    async def test_process_with_session_handles_sqlalchemy_error(self, mock_process_pending):
        """Test handling of SQLAlchemyError"""
        mock_process_pending.side_effect = SQLAlchemyError("Database error")
        mock_session = Mock()

        service = CommissionProcessingService()
        result = await service._process_with_session(mock_session, max_concurrent=5)

        assert result["success"] is False
        assert "Database error" in result["error"]


class TestProcessSingleAssetCommission:
    """Tests for process_single_asset_commission method"""

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    @patch('src.services.commission_processing_service.AssetService.commission_asset')
    async def test_process_single_asset_success(self, mock_commission, mock_get_asset):
        """Test successful single asset commission"""
        mock_asset = Mock()
        mock_asset.external_id = "EXEDRA123"
        mock_get_asset.return_value = mock_asset
        mock_commission.return_value = True

        mock_session = Mock()
        service = CommissionProcessingService(db_session=mock_session)

        result = await service.process_single_asset_commission(
            asset_external_id="EXEDRA123",
            project_id="project1"
        )

        assert result["success"] is True
        assert result["asset_external_id"] == "EXEDRA123"
        assert result["project_id"] == "project1"
        assert "timestamp" in result

        mock_get_asset.assert_called_once_with(
            external_id="EXEDRA123",
            project_id="project1",
            db=mock_session
        )
        mock_commission.assert_called_once_with(
            asset=mock_asset,
            actor="commission_service",
            db=mock_session
        )

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    async def test_process_single_asset_not_found(self, mock_get_asset):
        """Test handling when asset is not found"""
        mock_get_asset.return_value = None

        mock_session = Mock()
        service = CommissionProcessingService(db_session=mock_session)

        result = await service.process_single_asset_commission(
            asset_external_id="EXEDRA999",
            project_id="project1"
        )

        assert result["success"] is False
        assert "not found" in result["error"]
        assert "EXEDRA999" in result["error"]
        assert "project1" in result["error"]

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    @patch('src.services.commission_processing_service.AssetService.commission_asset')
    async def test_process_single_asset_commission_fails(self, mock_commission, mock_get_asset):
        """Test handling when commission fails"""
        mock_asset = Mock()
        mock_get_asset.return_value = mock_asset
        mock_commission.return_value = False

        mock_session = Mock()
        service = CommissionProcessingService(db_session=mock_session)

        result = await service.process_single_asset_commission(
            asset_external_id="EXEDRA456",
            project_id="project2"
        )

        # Commission returned False, so success should be False
        assert result["success"] is False

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    async def test_process_single_asset_handles_value_error(self, mock_get_asset):
        """Test handling of ValueError"""
        mock_get_asset.side_effect = ValueError("Invalid external ID")

        mock_session = Mock()
        service = CommissionProcessingService(db_session=mock_session)

        result = await service.process_single_asset_commission(
            asset_external_id="BAD_ID",
            project_id="project3"
        )

        assert result["success"] is False
        assert "Invalid external ID" in result["error"]
        assert result["asset_external_id"] == "BAD_ID"
        assert result["project_id"] == "project3"

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    async def test_process_single_asset_handles_runtime_error(self, mock_get_asset):
        """Test handling of RuntimeError"""
        mock_get_asset.side_effect = RuntimeError("EXEDRA connection failed")

        mock_session = Mock()
        service = CommissionProcessingService(db_session=mock_session)

        result = await service.process_single_asset_commission(
            asset_external_id="EXEDRA789",
            project_id="project4"
        )

        assert result["success"] is False
        assert "EXEDRA connection failed" in result["error"]

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    async def test_process_single_asset_handles_sqlalchemy_error(self, mock_get_asset):
        """Test handling of SQLAlchemyError"""
        mock_get_asset.side_effect = SQLAlchemyError("Database query failed")

        mock_session = Mock()
        service = CommissionProcessingService(db_session=mock_session)

        result = await service.process_single_asset_commission(
            asset_external_id="EXEDRA000",
            project_id="project5"
        )

        assert result["success"] is False
        assert "Database query failed" in result["error"]

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.AssetService.get_asset_by_external_id')
    @patch('src.services.commission_processing_service.AssetService.commission_asset')
    async def test_process_single_asset_without_provided_session(self, mock_commission, mock_get_asset):
        """Test processing without provided session creates and closes session"""
        mock_asset = Mock()
        mock_get_asset.return_value = mock_asset
        mock_commission.return_value = True

        service = CommissionProcessingService()

        result = await service.process_single_asset_commission(
            asset_external_id="EXEDRA111",
            project_id="project6"
        )

        assert result["success"] is True


class TestRunCommissionProcessing:
    """Tests for standalone run_commission_processing function"""

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.CommissionProcessingService.process_all_pending_commissions')
    async def test_run_commission_processing(self, mock_process_all):
        """Test standalone function creates service and processes"""
        mock_process_all.return_value = {
            "success": True,
            "duration_seconds": 4.5
        }

        result = await run_commission_processing(max_concurrent=15)

        assert result["success"] is True
        assert result["duration_seconds"] == 4.5
        mock_process_all.assert_called_once_with(15)

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.CommissionProcessingService.process_all_pending_commissions')
    async def test_run_commission_processing_default_concurrent(self, mock_process_all):
        """Test standalone function uses default max_concurrent"""
        mock_process_all.return_value = {
            "success": True
        }

        result = await run_commission_processing()

        assert result["success"] is True
        mock_process_all.assert_called_once_with(10)  # Default value

    @pytest.mark.asyncio
    @patch('src.services.commission_processing_service.CommissionProcessingService.process_all_pending_commissions')
    async def test_run_commission_processing_handles_errors(self, mock_process_all):
        """Test standalone function handles processing errors"""
        mock_process_all.return_value = {
            "success": False,
            "error": "Processing failed"
        }

        result = await run_commission_processing()

        assert result["success"] is False
        assert "error" in result
