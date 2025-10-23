# Adaptive Lighting API Implementation

This document summarizes the API endpoints we've implemented based on your specification.

## Architecture Overview

The API follows a clean layered architecture:
- **API Layer**: FastAPI routers with path-based tenancy (`/v1/{project_code}/...`)
- **Security Layer**: Bearer token authentication with scope-based authorization
- **Schemas Layer**: Pydantic models for request/response validation
- **Database Layer**: SQLAlchemy models matching your PostgreSQL design
- **Business Logic**: Command validation, guardrails, and audit logging

## Implemented Endpoints

### 1. Sensor Data Ingestion
- `POST /v1/{project_code}/sensor/ingest` - Unified sensor data ingestion
- `GET /v1/{project_code}/sensor/{external_id}` - Get sensor metadata

**Features:**
- Accepts vehicle counts, pedestrian counts, and speed data in single payload
- Stores in separate tables (vehicle_reading, ped_reading, speed_reading) for performance
- Deduplication via unique constraints on sensor_id + timestamp
- Hash-based integrity checking
- Comprehensive audit logging

### 2. Lighting Commands
- `POST /v1/{project_code}/command/realtime` - Immediate dimming commands
- `POST /v1/{project_code}/command/schedule` - Schedule-based dimming

**Features:**
- Mode-aware behavior (optimize vs passthrough)
- Basic API hygiene validation (0-100% dimming, time format)
- Policy guardrails for optimize mode (requires command:override scope)
- Idempotency key support
- Command queuing for EXEDRA relay (placeholder for background service)

### 3. Asset Management
- `GET /v1/{project_code}/asset/state` - Current asset state query
- `GET /v1/{project_code}/asset/schedule` - Current active schedule
- `GET /v1/{project_code}/asset/{external_id}` - Asset metadata
- `PUT /v1/{project_code}/asset/{external_id}/mode` - Change control mode

**Features:**
- Validation endpoints for asset state queries
- Control mode switching (optimize ↔ passthrough)
- Immediate effect on subsequent command handling

### 4. Admin Operations
- `PUT /v1/{project_code}/admin/policy` - Update policy configuration
- `GET /v1/{project_code}/admin/policy` - Get current policy
- `POST /v1/{project_code}/admin/kill-switch` - Emergency kill switch
- `GET /v1/{project_code}/admin/kill-switch` - Kill switch status
- `GET /v1/{project_code}/admin/audit` - Audit log retrieval

**Features:**
- Policy management for optimize mode guardrails
- Emergency kill switch with project isolation
- Comprehensive audit trail with filtering and pagination

## Security Implementation

### Authentication & Authorization
- Bearer token authentication via `Authorization: Bearer <token>` header
- Scope-based authorization system
- Project-level tenancy isolation
- Optional HMAC signature verification (framework in place)

### Required Scopes
- `ingest:write` - Sensor data ingestion
- `command:realtime.write` - Real-time commands
- `command:schedule.write` - Schedule commands
- `command:override` - Commands to optimize mode assets
- `asset:read` - Asset state queries
- `metadata:read` - Asset/sensor metadata
- `config:write` - Control mode changes
- `policy:write` - Policy updates
- `policy:read` - Policy retrieval
- `ops:emergency` - Kill switch control
- `ops:read` - Operations data access
- `audit:read` - Audit log access

### Guardrails Implementation
1. **API Hygiene** (all modes): Basic validation (0-100% dimming, time formats, data types)
2. **Policy Guardrails** (optimize mode only): Rate limiting, min/max constraints, time restrictions
3. **Emergency Controls**: Kill switch for halting optimize mode operations

## Data Model Alignment

The implementation aligns perfectly with your SQLAlchemy models:
- Uses your UUID primary keys and foreign key relationships
- Leverages JSONB for flexible metadata and schedule storage
- Implements your indexing strategy for performance
- Follows your audit logging design

## Next Steps for Testing

1. **Database Setup**: Ensure your PostgreSQL database is running with the adaptive_owner and adaptive_app roles
2. **Sample Data**: Create test projects, API clients, sensors, and assets
3. **API Keys**: Generate test API keys with appropriate scopes
4. **Integration Testing**: Test the complete flow from sensor ingestion to command execution

## Missing Implementations (As Planned)

- `email_service` - Email notifications
- `adaptive_service` - Core optimization algorithms  
- `exedra_service` - EXEDRA system integration
- Background workers for command relay
- Asset state caching/real-time status

## Error Handling

All endpoints return RFC7807 problem details for errors:
- 400: Bad Request (validation errors)
- 401: Unauthorized (invalid API key)
- 403: Forbidden (insufficient scopes)
- 404: Not Found (missing resources)
- 422: Unprocessable Entity (policy violations)

The API is now ready for initial testing and can be extended with the background services when you're ready to implement the optimization algorithms and EXEDRA integration.