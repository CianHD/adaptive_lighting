"""
Tests for EXEDRA API service integration.

Tests the ExedraService class which handles external EXEDRA API calls
for control program management, device commands, and commissioning.
"""

from unittest.mock import Mock, patch

import pytest
import requests

from src.services.exedra_service import ExedraService


class TestGetHeaders:
    """Test _get_headers helper method"""

    def test_get_headers_returns_correct_format(self):
        """Should return properly formatted headers with Bearer token"""
        token = "test-token-123"
        headers = ExedraService._get_headers(token)

        assert headers["Authorization"] == f"Bearer {token}"
        assert headers["Content-Type"] == "application/json"
        assert len(headers) == 2


class TestGetControlProgram:
    """Test get_control_program method"""

    @patch('src.services.exedra_service.requests.get')
    def test_get_control_program_success(self, mock_get):
        """Should retrieve control program successfully"""
        # Arrange
        program_id = "prog-123"
        token = "test-token"
        base_url = "https://exedra.test"
        expected_data = {
            "id": program_id,
            "name": "Test Program",
            "commands": [{"level": 50, "base": "midnight", "offset": 0}]
        }

        mock_response = Mock()
        mock_response.json.return_value = expected_data
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Act
        result = ExedraService.get_control_program(program_id, token, base_url)

        # Assert
        assert result == expected_data
        # Verify mock called correctly (verify value depends on EXEDRA_VERIFY_SSL setting)
        call_args = mock_get.call_args
        assert call_args[0][0] == f"{base_url}/api/v2/controlprograms/{program_id}"
        assert call_args[1]["headers"]["Authorization"] == f"Bearer {token}"
        assert call_args[1]["timeout"] == 30

    def test_get_control_program_empty_program_id(self):
        """Should raise ValueError for empty program_id"""
        with pytest.raises(ValueError, match="program_id cannot be empty"):
            ExedraService.get_control_program("", "token", "base_url")

    def test_get_control_program_empty_token(self):
        """Should raise ValueError for empty token"""
        with pytest.raises(ValueError, match="EXEDRA token cannot be empty"):
            ExedraService.get_control_program("prog-123", "", "base_url")

    def test_get_control_program_empty_base_url(self):
        """Should raise ValueError for empty base_url"""
        with pytest.raises(ValueError, match="EXEDRA base URL cannot be empty"):
            ExedraService.get_control_program("prog-123", "token", "")

    @patch('src.services.exedra_service.requests.get')
    def test_get_control_program_request_exception(self, mock_get):
        """Should raise RuntimeError on request failure"""
        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(RuntimeError, match="Failed to retrieve control program prog-123"):
            ExedraService.get_control_program("prog-123", "token", "https://exedra.test")


class TestUpdateControlProgram:
    """Test update_control_program method"""

    @patch('src.services.exedra_service.ExedraService.get_control_program')
    @patch('src.services.exedra_service.requests.put')
    def test_update_control_program_success(self, mock_put, mock_get):
        """Should update control program successfully"""
        # Arrange
        program_id = "prog-123"
        token = "test-token"
        base_url = "https://exedra.test"
        commands = [{"id": "cmd-1", "level": 75, "base": "midnight", "offset": 0}]
        asset_name = "Test Asset"

        # Mock existing program
        existing_program = {
            "id": program_id,
            "name": "Old Name",
            "description": "Old Description",
            "color": "#ffffff",
            "isTemplate": False,
            "category": "lighting",
            "type": "control",
            "onOff": False,
            "midnightMidnight": False,
            "tenant": "hyperion"
        }
        mock_get.return_value = existing_program

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        # Act
        result = ExedraService.update_control_program(
            program_id, commands, token, base_url, asset_name=asset_name
        )

        # Assert
        assert result is True
        mock_get.assert_called_once_with(program_id, token, base_url)

        # Verify PUT call with correct payload
        call_args = mock_put.call_args
        assert call_args[1]["json"]["id"] == program_id
        assert call_args[1]["json"]["name"] == f"Adaptive Schedule ({asset_name})"
        assert call_args[1]["json"]["commands"] == commands
        assert call_args[1]["json"]["color"] == "#ffffff"

    @patch('src.services.exedra_service.ExedraService.get_control_program')
    @patch('src.services.exedra_service.requests.put')
    def test_update_control_program_with_description(self, mock_put, mock_get):
        """Should use custom description when provided"""
        program_id = "prog-123"
        custom_desc = "Custom description"
        asset_name = "TestAsset"
        commands = [{"id": "cmd-1", "level": 50, "base": "midnight", "offset": 0}]

        mock_get.return_value = {"id": program_id, "name": "Test", "tenant": "hyperion"}
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_put.return_value = mock_response

        ExedraService.update_control_program(
            program_id, commands, "token", "https://exedra.test",
            asset_name=asset_name, description=custom_desc
        )

        call_args = mock_put.call_args
        assert call_args[1]["json"]["description"] == custom_desc

    def test_update_control_program_empty_program_id(self):
        """Should raise ValueError for empty program_id"""
        with pytest.raises(ValueError, match="program_id cannot be empty"):
            ExedraService.update_control_program("", [], "token", "base_url")

    def test_update_control_program_invalid_commands(self):
        """Should raise ValueError if commands is not a list"""
        with pytest.raises(ValueError, match="commands must be a list"):
            ExedraService.update_control_program("prog-123", "not-a-list", "token", "base_url")

    def test_update_control_program_empty_token(self):
        """Should raise ValueError for empty token"""
        with pytest.raises(ValueError, match="EXEDRA token cannot be empty"):
            ExedraService.update_control_program("prog-123", [], "", "base_url")

    def test_update_control_program_empty_base_url(self):
        """Should raise ValueError for empty base_url"""
        with pytest.raises(ValueError, match="EXEDRA base URL cannot be empty"):
            ExedraService.update_control_program("prog-123", [], "token", "")

    @patch('src.services.exedra_service.ExedraService.get_control_program')
    def test_update_control_program_get_fails(self, mock_get):
        """Should raise RuntimeError if cannot retrieve existing program"""
        mock_get.side_effect = RuntimeError("Failed to get program")

        with pytest.raises(RuntimeError, match="Cannot retrieve existing program"):
            ExedraService.update_control_program(
                "prog-123", [], "token", "https://exedra.test"
            )

    @patch('src.services.exedra_service.ExedraService.get_control_program')
    @patch('src.services.exedra_service.requests.put')
    def test_update_control_program_put_fails(self, mock_put, mock_get):
        """Should raise RuntimeError if PUT request fails"""
        mock_get.return_value = {"id": "prog-123", "name": "Test", "tenant": "hyperion"}
        mock_put.side_effect = requests.RequestException("Update failed")

        with pytest.raises(RuntimeError, match="Failed to update control program"):
            ExedraService.update_control_program(
                "prog-123", [], "token", "https://exedra.test"
            )


class TestCreateCommand:
    """Test create_command method"""

    def test_create_command_default_values(self):
        """Should create command with default base and offset"""
        command = ExedraService.create_command(level=50)

        assert command["level"] == 50
        assert command["base"] == "midnight"
        assert command["offset"] == 0
        assert "id" in command
        assert command["id"].startswith("50-midnight-0-")

    def test_create_command_with_all_parameters(self):
        """Should create command with all custom parameters"""
        command = ExedraService.create_command(
            level=75,
            base="sunset",
            offset=30,
            command_id="custom-id-123"
        )

        assert command["level"] == 75
        assert command["base"] == "sunset"
        assert command["offset"] == 30
        assert command["id"] == "custom-id-123"

    def test_create_command_level_too_low(self):
        """Should raise ValueError if level < 0"""
        with pytest.raises(ValueError, match="level must be between 0 and 100"):
            ExedraService.create_command(level=-1)

    def test_create_command_level_too_high(self):
        """Should raise ValueError if level > 100"""
        with pytest.raises(ValueError, match="level must be between 0 and 100"):
            ExedraService.create_command(level=101)

    def test_create_command_invalid_base(self):
        """Should raise ValueError for invalid base value"""
        with pytest.raises(ValueError, match="base must be 'sunset', 'sunrise', or 'midnight'"):
            ExedraService.create_command(level=50, base="invalid")

    def test_create_command_all_bases_valid(self):
        """Should accept all valid base values"""
        for base in ["sunset", "sunrise", "midnight"]:
            command = ExedraService.create_command(level=50, base=base)
            assert command["base"] == base


class TestValidateCommands:
    """Test validate_commands method"""

    def test_validate_commands_valid_list(self):
        """Should return True for valid command list"""
        commands = [
            {"id": "cmd-1", "level": 50, "base": "midnight", "offset": 0},
            {"id": "cmd-2", "level": 75, "base": "sunset", "offset": -30}
        ]

        result = ExedraService.validate_commands(commands)
        assert result is True

    def test_validate_commands_empty_list(self):
        """Should return True for empty list"""
        result = ExedraService.validate_commands([])
        assert result is True

    def test_validate_commands_not_a_list(self):
        """Should raise ValueError if not a list"""
        with pytest.raises(ValueError, match="commands must be a list"):
            ExedraService.validate_commands("not-a-list")

    def test_validate_commands_command_not_dict(self):
        """Should raise ValueError if command is not a dictionary"""
        with pytest.raises(ValueError, match="Command 0 must be a dictionary"):
            ExedraService.validate_commands([123])

    def test_validate_commands_missing_level(self):
        """Should raise ValueError if command missing level field"""
        commands = [{"base": "midnight", "offset": 0}]

        with pytest.raises(ValueError, match="Command 0 missing required field: level"):
            ExedraService.validate_commands(commands)

    def test_validate_commands_missing_base(self):
        """Should raise ValueError if command missing base field"""
        commands = [{"level": 50, "offset": 0}]

        with pytest.raises(ValueError, match="Command 0 missing required field: base"):
            ExedraService.validate_commands(commands)

    def test_validate_commands_missing_offset(self):
        """Should raise ValueError if command missing offset field"""
        commands = [{"level": 50, "base": "midnight"}]

        with pytest.raises(ValueError, match="Command 0 missing required field: offset"):
            ExedraService.validate_commands(commands)

    def test_validate_commands_invalid_level_type(self):
        """Should raise ValueError if level is not an integer"""
        commands = [{"level": "50", "base": "midnight", "offset": 0}]

        with pytest.raises(ValueError, match="Command 0 level must be integer 0-100"):
            ExedraService.validate_commands(commands)

    def test_validate_commands_level_out_of_range(self):
        """Should raise ValueError if level is out of 0-100 range"""
        commands = [{"level": 101, "base": "midnight", "offset": 0}]

        with pytest.raises(ValueError, match="Command 0 level must be integer 0-100"):
            ExedraService.validate_commands(commands)

    def test_validate_commands_invalid_base(self):
        """Should raise ValueError if base is invalid"""
        commands = [{"level": 50, "base": "invalid", "offset": 0}]

        with pytest.raises(ValueError, match="Command 0 base must be 'sunset', 'sunrise', or 'midnight'"):
            ExedraService.validate_commands(commands)

    def test_validate_commands_invalid_offset_type(self):
        """Should raise ValueError if offset is not an integer"""
        commands = [{"level": 50, "base": "midnight", "offset": "0"}]

        with pytest.raises(ValueError, match="Command 0 offset must be an integer"):
            ExedraService.validate_commands(commands)


class TestCreateScheduleFromSteps:
    """Test create_schedule_from_steps method"""

    def test_create_schedule_from_steps_valid(self):
        """Should convert schedule steps to EXEDRA commands"""
        steps = [
            {"time": "00:00", "dim": 30},
            {"time": "06:00", "dim": 50},
            {"time": "18:00", "dim": 80}
        ]

        commands = ExedraService.create_schedule_from_steps(steps)

        assert len(commands) == 3
        assert commands[0]["level"] == 30
        assert commands[0]["base"] == "midnight"
        assert commands[0]["offset"] == 0
        assert commands[1]["level"] == 50
        assert commands[1]["offset"] == 360  # 6 hours * 60
        assert commands[2]["level"] == 80
        assert commands[2]["offset"] == 1080  # 18 hours * 60

    def test_create_schedule_from_steps_skips_empty_time(self):
        """Should skip steps with empty time"""
        steps = [
            {"time": "00:00", "dim": 30},
            {"time": "", "dim": 50},
            {"time": "12:00", "dim": 70}
        ]

        commands = ExedraService.create_schedule_from_steps(steps)

        assert len(commands) == 2
        assert commands[0]["level"] == 30
        assert commands[1]["level"] == 70

    def test_create_schedule_from_steps_invalid_time_format(self):
        """Should raise ValueError for invalid time format"""
        steps = [{"time": "invalid", "dim": 50}]

        with pytest.raises(ValueError, match="Invalid schedule step"):
            ExedraService.create_schedule_from_steps(steps)

    def test_create_schedule_from_steps_missing_dim(self):
        """Should handle missing dim field (defaults to 0)"""
        steps = [{"time": "00:00"}]

        commands = ExedraService.create_schedule_from_steps(steps)

        assert len(commands) == 1
        assert commands[0]["level"] == 0

    def test_create_schedule_from_steps_empty_list(self):
        """Should return empty list for empty input"""
    commands = ExedraService.create_schedule_from_steps([])
    assert not commands


class TestSendDeviceCommand:
    """Test send_device_command method"""

    @patch('src.services.exedra_service.requests.put')
    def test_send_device_command_set_dimming_level_success(self, mock_put):
        """Should send setDimmingLevel command successfully"""
        # Arrange
        device_id = "device-123"
        token = "test-token"
        base_url = "https://exedra.test"
        level = 75

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "deviceId": device_id}
        mock_put.return_value = mock_response

        # Act
        result = ExedraService.send_device_command(
            device_id, "setDimmingLevel", level, token, base_url
        )

        # Assert
        assert result["status"] == "success"
        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert call_args[1]["json"]["deviceId"] == device_id
        assert call_args[1]["json"]["command"] == "setDimmingLevel"
        assert call_args[1]["json"]["level"] == level

    def test_send_device_command_empty_token(self):
        """Should raise ValueError for empty token"""
        with pytest.raises(ValueError, match="EXEDRA token cannot be empty"):
            ExedraService.send_device_command("device-123", "setDimmingLevel", 50, "", "base_url")

    def test_send_device_command_empty_base_url(self):
        """Should raise ValueError for empty base_url"""
        with pytest.raises(ValueError, match="EXEDRA base URL cannot be empty"):
            ExedraService.send_device_command("device-123", "setDimmingLevel", 50, "token", "")

    def test_send_device_command_set_dimming_no_level(self):
        """Should raise ValueError if setDimmingLevel command has no level"""
        with pytest.raises(ValueError, match="setDimmingLevel requires level 0-100"):
            ExedraService.send_device_command(
                "device-123", "setDimmingLevel", None, "token", "https://exedra.test"
            )

    def test_send_device_command_set_dimming_level_out_of_range(self):
        """Should raise ValueError if level is out of range"""
        with pytest.raises(ValueError, match="setDimmingLevel requires level 0-100"):
            ExedraService.send_device_command(
                "device-123", "setDimmingLevel", 101, "token", "https://exedra.test"
            )

    @patch('src.services.exedra_service.requests.put')
    def test_send_device_command_api_error_with_json(self, mock_put):
        """Should raise HTTPError on API error with JSON response"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Device not found"}
        mock_put.return_value = mock_response

        with pytest.raises(requests.HTTPError, match="EXEDRA device command failed: 400"):
            ExedraService.send_device_command(
                "device-123", "setDimmingLevel", 50, "token", "https://exedra.test"
            )

    @patch('src.services.exedra_service.requests.put')
    def test_send_device_command_api_error_with_text(self, mock_put):
        """Should raise HTTPError on API error with text response"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Internal Server Error"
        mock_put.return_value = mock_response

        with pytest.raises(requests.HTTPError, match="EXEDRA device command failed: 500"):
            ExedraService.send_device_command(
                "device-123", "setDimmingLevel", 50, "token", "https://exedra.test"
            )


class TestGetDeviceDimmingLevel:
    """Test get_device_dimming_level method"""

    @patch('src.services.exedra_service.requests.get')
    def test_get_device_dimming_level_success(self, mock_get):
        """Should retrieve device dimming level successfully"""
        device_id = "device-123"
        token = "test-token"
        base_url = "https://exedra.test"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deviceId": device_id, "dimmingLevel": 75}
        mock_get.return_value = mock_response

        result = ExedraService.get_device_dimming_level(device_id, token, base_url)

        assert result["dimmingLevel"] == 75
        # Verify mock called correctly (verify value depends on EXEDRA_VERIFY_SSL setting)
        call_args = mock_get.call_args
        assert call_args[0][0] == f"{base_url}/api/v2/streetlight/{device_id}/dimminglevel"
        assert call_args[1]["headers"]["Authorization"] == f"Bearer {token}"
        assert call_args[1]["timeout"] == 30.0

    @patch('src.services.exedra_service.requests.get')
    def test_get_device_dimming_level_with_refresh(self, mock_get):
        """Should handle refresh_device parameter (no-op currently)"""
        device_id = "device-123"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dimmingLevel": 60}
        mock_get.return_value = mock_response

        result = ExedraService.get_device_dimming_level(
            device_id, "token", "https://exedra.test", refresh_device=True
        )

        assert result["dimmingLevel"] == 60

    def test_get_device_dimming_level_empty_token(self):
        """Should raise ValueError for empty token"""
        with pytest.raises(ValueError, match="EXEDRA token cannot be empty"):
            ExedraService.get_device_dimming_level("device-123", "", "base_url")

    def test_get_device_dimming_level_empty_base_url(self):
        """Should raise ValueError for empty base_url"""
        with pytest.raises(ValueError, match="EXEDRA base URL cannot be empty"):
            ExedraService.get_device_dimming_level("device-123", "token", "")

    @patch('src.services.exedra_service.requests.get')
    def test_get_device_dimming_level_api_error(self, mock_get):
        """Should raise HTTPError on API error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": "Device not found"}
        mock_get.return_value = mock_response

        with pytest.raises(requests.HTTPError, match="EXEDRA get dimming level failed: 404"):
            ExedraService.get_device_dimming_level("device-123", "token", "https://exedra.test")


class TestCommissionDevice:
    """Test commission_device method"""

    @patch('src.services.exedra_service.requests.post')
    def test_commission_device_success(self, mock_post):
        """Should commission device successfully"""
        device_id = "device-123"
        token = "test-token"
        base_url = "https://exedra.test"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "commissioned", "deviceId": device_id}
        mock_post.return_value = mock_response

        result = ExedraService.commission_device(device_id, token, base_url)

        assert result["status"] == "commissioned"
        mock_post.assert_called_once()

    @patch('src.services.exedra_service.requests.post')
    def test_commission_device_with_data(self, mock_post):
        """Should commission device with custom commissioning data"""
        device_id = "device-123"
        commission_data = {"mode": "automatic", "retries": 3}

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"status": "commissioned"}
        mock_post.return_value = mock_response

        result = ExedraService.commission_device(
            device_id, "token", "https://exedra.test", commission_data=commission_data
        )

        assert result["status"] == "commissioned"
        call_args = mock_post.call_args
        assert call_args[1]["json"] == commission_data

    @patch('src.services.exedra_service.requests.post')
    def test_commission_device_custom_timeout(self, mock_post):
        """Should use custom timeout for commissioning"""
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"status": "pending"}
        mock_post.return_value = mock_response

        ExedraService.commission_device(
            "device-123", "token", "https://exedra.test", timeout=300.0
        )

        call_args = mock_post.call_args
        assert call_args[1]["timeout"] == 300.0

    def test_commission_device_empty_token(self):
        """Should raise ValueError for empty token"""
        with pytest.raises(ValueError, match="EXEDRA token cannot be empty"):
            ExedraService.commission_device("device-123", "", "base_url")

    def test_commission_device_empty_base_url(self):
        """Should raise ValueError for empty base_url"""
        with pytest.raises(ValueError, match="EXEDRA base URL cannot be empty"):
            ExedraService.commission_device("device-123", "token", "")

    @patch('src.services.exedra_service.requests.post')
    def test_commission_device_api_error(self, mock_post):
        """Should raise HTTPError on API error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Commissioning failed"}
        mock_post.return_value = mock_response

        with pytest.raises(requests.HTTPError, match="EXEDRA device commissioning failed: 500"):
            ExedraService.commission_device("device-123", "token", "https://exedra.test")


class TestGetDeviceSchedule:
    """Test get_device_schedule method"""

    @patch('src.services.exedra_service.requests.get')
    def test_get_device_schedule_success(self, mock_get):
        """Should retrieve device schedule successfully"""
        device_id = "device-123"
        token = "test-token"
        base_url = "https://exedra.test"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": device_id,
            "schedule": [{"time": "00:00", "level": 50}]
        }
        mock_get.return_value = mock_response

        result = ExedraService.get_device_schedule(device_id, token, base_url)

        assert result["id"] == device_id
        assert "schedule" in result
        # Verify mock called correctly (verify value depends on EXEDRA_VERIFY_SSL setting)
        call_args = mock_get.call_args
        assert call_args[0][0] == f"{base_url}/api/v2/calendars/{device_id}"
        assert call_args[1]["headers"]["Authorization"] == f"Bearer {token}"
        assert call_args[1]["timeout"] == 30.0

    def test_get_device_schedule_empty_token(self):
        """Should raise ValueError for empty token"""
        with pytest.raises(ValueError, match="EXEDRA token cannot be empty"):
            ExedraService.get_device_schedule("device-123", "", "base_url")

    def test_get_device_schedule_empty_base_url(self):
        """Should raise ValueError for empty base_url"""
        with pytest.raises(ValueError, match="EXEDRA base URL cannot be empty"):
            ExedraService.get_device_schedule("device-123", "token", "")

    @patch('src.services.exedra_service.requests.get')
    def test_get_device_schedule_api_error(self, mock_get):
        """Should raise HTTPError on API error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": "Schedule not found"}
        mock_get.return_value = mock_response

        with pytest.raises(requests.HTTPError, match="EXEDRA get schedule failed: 404"):
            ExedraService.get_device_schedule("device-123", "token", "https://exedra.test")
