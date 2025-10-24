import uuid
import warnings
import requests
from typing import List, Dict, Any
from urllib3.exceptions import InsecureRequestWarning

from src.core.config import settings

# Load EXEDRA authentication
EXEDRA_TOKEN = settings.EXEDRA_TOKEN
EXEDRA_BASE_URL = getattr(settings, 'EXEDRA_BASE_URL', 'https://au-scs.oceania-schreder-exedra.com')
# SSL verification setting - should be True in production
EXEDRA_VERIFY_SSL = getattr(settings, 'EXEDRA_VERIFY_SSL', True)

# Only suppress SSL warnings if verification is explicitly disabled (development only)
if not EXEDRA_VERIFY_SSL:
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)
    print("WARNING: EXEDRA SSL verification is disabled. This should only be used in development!")

if not EXEDRA_TOKEN:
    raise RuntimeError("EXEDRA_TOKEN missing from configuration")


class ExedraService:
    """Service for interfacing with EXEDRA control programs API"""

    @staticmethod
    def _get_headers() -> Dict[str, str]:
        """Get standard headers for EXEDRA API requests"""
        return {
            "Authorization": f"Bearer {EXEDRA_TOKEN}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def get_control_program(program_id: str) -> Dict[str, Any]:
        """
        Retrieve a control program from EXEDRA
        
        Args:
            program_id: The EXEDRA control program ID
            
        Returns:
            Dictionary containing the control program data
            
        Raises:
            requests.HTTPError: If the API request fails
            ValueError: If program_id is invalid
        """
        if not program_id:
            raise ValueError("program_id cannot be empty")

        url = f"{EXEDRA_BASE_URL}/api/v1/controlprograms/{program_id}"
        headers = ExedraService._get_headers()

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
        asset_name: str = None,
        description: str = None
    ) -> bool:
        """
        Update a control program in EXEDRA with new commands
        
        Args:
            program_id: The EXEDRA control program ID
            commands: List of command objects to set
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

        # First get the existing program to preserve metadata
        try:
            existing = ExedraService.get_control_program(program_id)
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

        url = f"{EXEDRA_BASE_URL}/api/v1/controlprograms/{program_id}"
        headers = ExedraService._get_headers()

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
