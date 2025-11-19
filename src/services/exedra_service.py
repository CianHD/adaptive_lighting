import uuid
import warnings
import requests
from typing import List, Dict, Any, Optional
from urllib3.exceptions import InsecureRequestWarning

from src.core.config import settings

# SSL verification setting - should be True in production
EXEDRA_VERIFY_SSL = getattr(settings, 'EXEDRA_VERIFY_SSL', True)

# Only suppress SSL warnings if verification is explicitly disabled (development only)
if not EXEDRA_VERIFY_SSL:
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)
    print("WARNING: EXEDRA SSL verification is disabled. This should only be used in development!")


class ExedraService:
    """Service for interfacing with EXEDRA control programs API"""

    @staticmethod
    def _get_headers(token: str) -> Dict[str, str]:
        """Get standard headers for EXEDRA API requests"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def get_control_program(program_id: str, token: str, base_url: str) -> Dict[str, Any]:
        """
        Retrieve a control program from EXEDRA
        
        Args:
            program_id: The EXEDRA control program ID
            token: Client's EXEDRA API token
            base_url: Client's EXEDRA base URL
            
        Returns:
            Dictionary containing the control program data
            
        Raises:
            requests.HTTPError: If the API request fails
            ValueError: If program_id is invalid
        """
        if not program_id:
            raise ValueError("program_id cannot be empty")

        if not token:
            raise ValueError("EXEDRA token cannot be empty")

        if not base_url:
            raise ValueError("EXEDRA base URL cannot be empty")

        url = f"{base_url}/api/v2/controlprograms/{program_id}"
        headers = ExedraService._get_headers(token)

        try:
            response = requests.get(url, headers=headers, timeout=30, verify=EXEDRA_VERIFY_SSL)
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to retrieve control program {program_id}: {str(e)}") from e

    @staticmethod
    def update_control_program(
        program_id: str,
        commands: List[Dict[str, Any]],
        token: str,
        base_url: str,
        asset_name: str = None,
        description: str = None
    ) -> bool:
        """
        Update a control program in EXEDRA with new commands
        
        Args:
            program_id: The EXEDRA control program ID
            commands: List of command objects to set
            token: Client's EXEDRA API token
            base_url: Client's EXEDRA base URL
            asset_name: Optional asset name for the schedule title
            description: Optional description override
            
        Returns:
            True if update was successful
            
        Raises:
            requests.HTTPError: If the API request fails
            ValueError: If required parameters are invalid
        """
        if not program_id:
            raise ValueError("program_id cannot be empty")
        if not isinstance(commands, list):
            raise ValueError("commands must be a list")
        if not token:
            raise ValueError("EXEDRA token cannot be empty")
        if not base_url:
            raise ValueError("EXEDRA base URL cannot be empty")

        # First get the existing program to preserve metadata
        try:
            existing = ExedraService.get_control_program(program_id, token, base_url)
        except Exception as e:
            raise RuntimeError(f"Cannot retrieve existing program {program_id}: {str(e)}") from e

        # Build the update payload
        payload = {
            "id": program_id,
            "name": f"Adaptive Schedule ({asset_name})" if asset_name else existing.get("name", "Adaptive Schedule"),
            "description": description or f"Adaptive lighting schedule for {asset_name}" if asset_name else existing.get("description", "Adaptive lighting schedule"),
            "color": existing.get("color", "#f7f67e"),  # Default to yellowish
            "commands": commands,
            "isTemplate": existing.get("isTemplate", False),
            "category": existing.get("category"),
            "type": existing.get("type", "control"),
            "onOff": existing.get("onOff", False),
            "midnightMidnight": existing.get("midnightMidnight", False),
            "resourceTemplateInfo": existing.get("resourceTemplateInfo"),
            "tenant": existing.get("tenant", "hyperion"),
        }

        url = f"{base_url}/api/v2/controlprograms/{program_id}"
        headers = ExedraService._get_headers(token)

        try:
            response = requests.put(url, headers=headers, json=payload, timeout=30, verify=EXEDRA_VERIFY_SSL)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to update control program {program_id}: {str(e)}") from e

    @staticmethod
    def create_command(
        level: int,
        base: str = "midnight",
        offset: int = 0,
        command_id: str = None
    ) -> Dict[str, Any]:
        """
        Create an EXEDRA command object
        
        Args:
            level: Dimming level (0-100)
            base: Time base ("sunset", "sunrise", "midnight")
            offset: Offset in minutes from base time
            command_id: Optional specific command ID
            
        Returns:
            Command dictionary for EXEDRA API
        """
        if not 0 <= level <= 100:
            raise ValueError("level must be between 0 and 100")
        if base not in ["sunset", "sunrise", "midnight"]:
            raise ValueError("base must be 'sunset', 'sunrise', or 'midnight'")

        return {
            "id": command_id or f"{level}-{base}-{offset}-{uuid.uuid4().hex[:6]}",
            "level": level,
            "base": base,
            "offset": offset
        }

    @staticmethod
    def validate_commands(commands: List[Dict[str, Any]]) -> bool:
        """
        Validate that commands are properly formatted for EXEDRA
        
        Args:
            commands: List of command dictionaries
            
        Returns:
            True if all commands are valid
            
        Raises:
            ValueError: If any command is invalid
        """
        if not isinstance(commands, list):
            raise ValueError("commands must be a list")

        for i, cmd in enumerate(commands):
            if not isinstance(cmd, dict):
                raise ValueError(f"Command {i} must be a dictionary")

            # Check required fields
            required_fields = ["level", "base", "offset"]
            for field in required_fields:
                if field not in cmd:
                    raise ValueError(f"Command {i} missing required field: {field}")

            # Validate values
            if not isinstance(cmd["level"], int) or not 0 <= cmd["level"] <= 100:
                raise ValueError(f"Command {i} level must be integer 0-100")
            if cmd["base"] not in ["sunset", "sunrise", "midnight"]:
                raise ValueError(f"Command {i} base must be 'sunset', 'sunrise', or 'midnight'")
            if not isinstance(cmd["offset"], int):
                raise ValueError(f"Command {i} offset must be an integer")

        return True

    @staticmethod
    def create_schedule_from_steps(schedule_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert schedule steps (time + dim) to EXEDRA commands
        
        Args:
            schedule_steps: List of {"time": "HH:MM", "dim": 0-100} objects
            
        Returns:
            List of EXEDRA command objects
        """
        commands = []

        for step in schedule_steps:
            try:
                # Parse time string
                time_str = step.get("time", "")
                if not time_str:
                    continue

                hour, minute = map(int, time_str.split(":"))
                dim_level = int(step.get("dim", 0))

                # Convert to minutes since midnight
                offset_minutes = hour * 60 + minute

                # Create EXEDRA command
                command = ExedraService.create_command(
                    level=dim_level,
                    base="midnight",
                    offset=offset_minutes
                )
                commands.append(command)

            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid schedule step {step}: {str(e)}") from e

        return commands

    @staticmethod
    def send_device_command(
        device_id: str,
        command_type: str,
        level: Optional[int],
        duration_seconds: Optional[int],
        token: str,
        base_url: str,
    ) -> Dict[str, Any]:
        """
        Send real-time command to EXEDRA device
        
        Args:
            device_id: EXEDRA device identifier
            command_type: "setDimmingLevel" for now, extensible for future commands
            level: Dimming level 0-100 (required for setDimmingLevel)
            duration_seconds: Duration in seconds for which command should hold
            token: EXEDRA API token
            base_url: EXEDRA base URL
        Returns:
            EXEDRA response data
            
        Raises:
            requests.HTTPError: If request fails
            ValueError: If parameters are invalid
        """
        if not token:
            raise ValueError("EXEDRA token cannot be empty")
        if not base_url:
            raise ValueError("EXEDRA base URL cannot be empty")

        # Validate command
        if command_type == "setDimmingLevel":
            if level is None or not 0 <= level <= 100:
                raise ValueError("setDimmingLevel requires level 0-100")

        # Build payload based on command type
        payload = {
            "id": device_id,
            "command": command_type,
            "level": level,
            "duration": duration_seconds
        }

        # Send command to EXEDRA
        headers = ExedraService._get_headers(token)

        response = requests.put(
            f"{base_url}/api/v1/devices/command",
            json=payload,
            headers=headers,
            verify=EXEDRA_VERIFY_SSL,
            timeout=30.0
        )

        if response.status_code != 200:
            error_msg = f"EXEDRA device command failed: {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data}"
            except (ValueError, requests.JSONDecodeError):
                error_msg += f" - {response.text}"

            raise requests.HTTPError(error_msg)

        result = response.json()
        return result

    @staticmethod
    def get_device_dimming_level(device_id: str, token: str, base_url: str, refresh_device: bool = False) -> Dict[str, Any]:
        """
        Get current dimming level from EXEDRA device
        
        Args:
            device_id: EXEDRA device identifier  
            token: EXEDRA API token
            base_url: EXEDRA base URL
            refresh_device: Whether to refresh device state before querying
        Returns:
            EXEDRA response with current dimming level
            
        Raises:
            requests.HTTPError: If request fails
            ValueError: If parameters are invalid
        """
        if not token:
            raise ValueError("EXEDRA token cannot be empty")
        if not base_url:
            raise ValueError("EXEDRA base URL cannot be empty")

        # Optional: refresh device state first
        if refresh_device:
            # This would trigger device to update its status
            # Implementation depends on EXEDRA refresh mechanism
            pass

        # Get current dimming level
        headers = ExedraService._get_headers(token)

        response = requests.get(
            f"{base_url}/api/v2/streetlight/{device_id}/dimminglevel",
            headers=headers,
            verify=EXEDRA_VERIFY_SSL,
            timeout=30.0
        )

        if response.status_code != 200:
            error_msg = f"EXEDRA get dimming level failed: {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data}"
            except (ValueError, requests.JSONDecodeError):
                error_msg += f" - {response.text}"

            raise requests.HTTPError(error_msg)

        result = response.json()
        return result

    @staticmethod
    def commission_device(device_id: str, token: str, base_url: str,
                        commission_data: Optional[Dict[str, Any]] = None,
                        timeout: float = 180.0) -> Dict[str, Any]:
        """
        Commission EXEDRA device (required for schedule updates)
        
        Args:
            device_id: EXEDRA device identifier
            token: EXEDRA API token
            base_url: EXEDRA base URL
            commission_data: Optional commissioning parameters
            timeout: Request timeout in seconds (default 180s for 3-minute retry attempts)
            
        Returns:
            EXEDRA commissioning response
            
        Raises:
            requests.HTTPError: If request fails
            ValueError: If parameters are invalid
        """
        if not token:
            raise ValueError("EXEDRA token cannot be empty")
        if not base_url:
            raise ValueError("EXEDRA base URL cannot be empty")

        # Commission device
        headers = ExedraService._get_headers(token)
        payload = commission_data or {}

        response = requests.post(
            f"{base_url}/api/v2/devices/{device_id}/commission",
            json=payload,
            headers=headers,
            verify=EXEDRA_VERIFY_SSL,
            timeout=timeout  # Configurable timeout for commissioning
        )

        if response.status_code not in [200, 201, 202]:
            error_msg = f"EXEDRA device commissioning failed: {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data}"
            except (ValueError, requests.JSONDecodeError):
                error_msg += f" - {response.text}"

            raise requests.HTTPError(error_msg)

        result = response.json()
        return result

    @staticmethod
    def get_device_schedule(device_id: str, token: str, base_url: str) -> Dict[str, Any]:
        """
        Get current schedule/calendar for EXEDRA device
        
        Args:
            device_id: EXEDRA device identifier (used as calendar_id)
            token: EXEDRA API token
            base_url: EXEDRA base URL
            
        Returns:
            EXEDRA schedule/calendar data
            
        Raises:
            requests.HTTPError: If request fails
            ValueError: If parameters are invalid
        """
        if not token:
            raise ValueError("EXEDRA token cannot be empty")
        if not base_url:
            raise ValueError("EXEDRA base URL cannot be empty")

        # Get device schedule
        headers = ExedraService._get_headers(token)

        # Note: Using device_id as calendar_id - may need adjustment based on EXEDRA mapping
        response = requests.get(
            f"{base_url}/api/v2/calendars/{device_id}",
            headers=headers,
            verify=EXEDRA_VERIFY_SSL,
            timeout=30.0
        )

        if response.status_code != 200:
            error_msg = f"EXEDRA get schedule failed: {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data}"
            except (ValueError, requests.JSONDecodeError):
                error_msg += f" - {response.text}"

            raise requests.HTTPError(error_msg)

        result = response.json()
        return result
