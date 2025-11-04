from typing import List, Dict
from sqlalchemy.orm import Session

from src.db.models import ScopeCatalogue


class ScopeService:
    """Service for managing API scopes and permissions"""

    # Comprehensive scope definitions
    SCOPE_DEFINITIONS = {
        # Asset Operations
        "asset:read": {
            "description": "Read asset state and current operational status",
            "category": "asset"
        },
        "asset:metadata": {
            "description": "Read asset metadata, configuration details, and specifications",
            "category": "asset"
        },
        "asset:write": {
            "description": "Create assets and update metadata, configuration, and control mode",
            "category": "asset"
        },
        "asset:command": {
            "description": "Execute asset commands (schedules and real-time dimming)",
            "category": "asset"
        },

        # Sensor Operations
        "sensor:read": {
            "description": "Read sensor operational status and current readings",
            "category": "sensor"
        },
        "sensor:metadata": {
            "description": "Read sensor metadata, configuration, and capabilities",
            "category": "sensor"
        },
        "sensor:write": {
            "description": "Update sensor configuration and metadata",
            "category": "sensor"
        },
        "sensor:ingest": {
            "description": "Submit sensor data readings",
            "category": "sensor"
        },

        # Administrative Operations
        "admin:policy:read": {
            "description": "Read system policy configurations",
            "category": "admin"
        },
        "admin:policy:write": {
            "description": "Create and update system policies",
            "category": "admin"
        },
        "admin:killswitch": {
            "description": "Enable/disable system kill switch",
            "category": "admin"
        },
        "admin:audit": {
            "description": "Read system audit logs",
            "category": "admin"
        },
        "admin:credentials": {
            "description": "Store and manage client credentials (EXEDRA keys, etc.)",
            "category": "admin"
        },
        "admin:apikeys:write": {
            "description": "Generate and manage API keys for clients",
            "category": "admin"
        }
    }

    @staticmethod
    def get_all_scopes(db: Session = None) -> Dict[str, Dict[str, str]]:
        """
        Get all scopes from database with their descriptions and categories
        
        Args:
            db: Database session
            
        Returns:
            Dictionary mapping scope_code -> {description, category}
        """
        if db is None:
            # Fallback to static definitions if no DB session
            return ScopeService.SCOPE_DEFINITIONS

        scopes = db.query(ScopeCatalogue).all()
        return {
            scope.scope_code: {
                "description": scope.description,
                "category": scope.category
            }
            for scope in scopes
        }

    @staticmethod
    def get_scopes_by_category(category: str, db: Session = None) -> Dict[str, Dict[str, str]]:
        """
        Get all scopes in a specific category from database
        
        Args:
            category: Category to filter by
            db: Database session
            
        Returns:
            Dictionary of scopes in the specified category
        """
        if db is None:
            # Fallback to static definitions if no DB session
            return {
                scope: details for scope, details in ScopeService.SCOPE_DEFINITIONS.items()
                if details["category"] == category
            }

        scopes = db.query(ScopeCatalogue).filter(ScopeCatalogue.category == category).all()
        return {
            scope.scope_code: {
                "description": scope.description,
                "category": scope.category
            }
            for scope in scopes
        }

    @staticmethod
    def validate_scopes(scopes: List[str], db: Session = None) -> tuple[bool, List[str]]:
        """
        Validate that all provided scopes exist in database
        
        Args:
            scopes: List of scope codes to validate
            db: Database session
            
        Returns:
            Tuple of (all_valid, invalid_scopes)
        """
        if db is None:
            # Fallback to static definitions if no DB session
            invalid_scopes = [
                scope for scope in scopes
                if scope not in ScopeService.SCOPE_DEFINITIONS
            ]
            return len(invalid_scopes) == 0, invalid_scopes

        # Get all valid scope codes from database
        valid_scope_codes = {scope.scope_code for scope in db.query(ScopeCatalogue).all()}

        invalid_scopes = [
            scope for scope in scopes
            if scope not in valid_scope_codes
        ]
        return len(invalid_scopes) == 0, invalid_scopes

    @staticmethod
    def get_valid_scope_codes(db: Session) -> set[str]:
        """
        Get all valid scope codes from database
        
        Args:
            db: Database session
        Returns:
            Set of valid scope codes
        """
        return {scope.scope_code for scope in db.query(ScopeCatalogue).all()}

    @staticmethod
    def get_recommended_scopes() -> Dict[str, List[str]]:
        """Get recommended scope combinations for common use cases"""
        return {
            "asset_readonly": [
                "asset:read"
            ],
            "asset_metadata_viewer": [
                "asset:read",
                "asset:metadata"
            ],
            "asset_administrator": [
                "asset:read",
                "asset:metadata",
                "asset:write"
            ],
            "asset_operator": [
                "asset:read",
                "asset:command"
            ],
            "asset_full_control": [
                "asset:read",
                "asset:metadata",
                "asset:write", 
                "asset:command"
            ],
            "sensor_client": [
                "sensor:read",
                "sensor:ingest"
            ],
            "sensor_metadata_viewer": [
                "sensor:read",
                "sensor:metadata"
            ],
            "sensor_administrator": [
                "sensor:read",
                "sensor:metadata",
                "sensor:write",
                "sensor:ingest"
            ],
            "system_admin": [
                "admin:policy:read",
                "admin:policy:write", 
                "admin:killswitch",
                "admin:audit",
                "admin:credentials",
                "admin:apikeys:write"
            ],
            "integration_service": [
                "asset:read",
                "asset:command",
                "sensor:read",
                "sensor:ingest"
            ],
            "monitoring_service": [
                "asset:read",
                "sensor:read"
            ]
        }

    @staticmethod
    def sync_catalogue_to_database(db: Session) -> int:
        """
        Sync the scope definitions to the database catalogue
        
        Args:
            db: Database session
            
        Returns:
            Number of scopes inserted/updated
        """
        count = 0
        for scope_code, details in ScopeService.SCOPE_DEFINITIONS.items():
            # Check if scope already exists
            existing = db.query(ScopeCatalogue).filter(
                ScopeCatalogue.scope_code == scope_code
            ).first()

            if existing:
                # Update existing
                existing.description = details["description"]
                existing.category = details["category"]
            else:
                # Create new
                scope = ScopeCatalogue(
                    scope_code=scope_code,
                    description=details["description"],
                    category=details["category"]
                )
                db.add(scope)
                count += 1

        db.commit()
        return count
