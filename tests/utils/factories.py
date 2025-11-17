"""Factory helpers shared across test modules."""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from src.db.models import ApiClient, Project


def create_project_with_client(
    db_session: Session,
    *,
    project_kwargs: Optional[Dict] = None,
    api_client_kwargs: Optional[Dict] = None,
) -> Tuple[Project, ApiClient]:
    """Create and persist a project plus API client for tests."""
    project_data = {
        "project_id": str(uuid.uuid4()),
        "code": "TEST-001",
        "name": "Test Project",
    }
    if project_kwargs:
        project_data.update(project_kwargs)

    project = Project(**project_data)
    db_session.add(project)
    db_session.commit()

    client_data = {
        "api_client_id": str(uuid.uuid4()),
        "project_id": project.project_id,
        "name": "Test Client",
        "status": "active",
    }
    if api_client_kwargs:
        client_overrides = api_client_kwargs.copy()
        if "project_id" not in client_overrides:
            client_overrides["project_id"] = project.project_id
        client_data.update(client_overrides)

    api_client = ApiClient(**client_data)
    db_session.add(api_client)
    db_session.commit()

    return project, api_client
