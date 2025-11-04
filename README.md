# Adaptive Lighting API Implementation

This document summarizes the comprehensive API implementation with advanced features including multi-tenant credential management, unified audit logging, asset creation with EXEDRA integration, and comprehensive error handling.

## Architecture Overview

The API follows a clean layered architecture:
- **API Layer**: FastAPI routers with path-based tenancy (`/v1/{project_code}/...`)
- **Security Layer**: Bearer token authentication with refined scope-based authorization
- **Multi-tenant Credentials**: Encrypted EXEDRA credential storage per client/environment
- **Unified Logging**: Comprehensive audit logging with RFC 7807 Problem Details error handling
- **Business Logic**: Advanced command validation, guardrails, and EXEDRA integration
- **Database Layer**: SQLAlchemy models with proper constraints and idempotency support

## Implemented Endpoints

### 1. Asset Management
- `POST /v1/{project_code}/asset/` - **NEW**: Create assets with EXEDRA integration
- `GET /v1/{project_code}/asset/state` - Current asset state query
- `GET /v1/{project_code}/asset/schedule` - Current active schedule
- `GET /v1/{project_code}/asset/{external_id}` - Asset metadata
- `PUT /v1/{project_code}/asset/{external_id}/mode` - Change control mode
- `POST /v1/{project_code}/asset/realtime` - Real-time asset commands

**Features:**
- **EXEDRA Asset Creation**: Direct integration with EXEDRA device management
- **Metadata Storage**: Comprehensive device information with control programs
- **Field Clarity**: Clear naming (exedra_id → asset.external_id, exedra_name → asset.name)
- **Validation**: Proper constraints and duplicate prevention
- **Control Mode Management**: Seamless switching between optimize ↔ passthrough

### 2. Sensor Data Ingestion
- `POST /v1/{project_code}/sensor/ingest` - Unified sensor data ingestion
- `GET /v1/{project_code}/sensor/{external_id}` - Get sensor metadata

**Features:**
- Accepts vehicle counts, pedestrian counts, and speed data in single payload
- Stores in separate tables (vehicle_reading, ped_reading, speed_reading) for performance
- Deduplication via unique constraints on sensor_id + timestamp
- Hash-based integrity checking
- Comprehensive audit logging

### 3. Admin Operations
- `PUT /v1/{project_code}/admin/policy` - Update policy configuration
- `GET /v1/{project_code}/admin/policy` - Get current policy
- `POST /v1/{project_code}/admin/kill-switch` - Emergency kill switch
- `GET /v1/{project_code}/admin/kill-switch` - Kill switch status
- `GET /v1/{project_code}/admin/audit` - Audit log retrieval
- `POST /v1/{project_code}/admin/credentials` - Manage EXEDRA credentials
- `GET /v1/{project_code}/admin/credentials` - List available credentials

**Features:**
- **Multi-tenant Credentials**: Encrypted EXEDRA credential management
- **Environment Isolation**: Separate credentials for dev/staging/prod
- **Policy Management**: Advanced guardrails for optimize mode
- **Emergency Controls**: Kill switch with project isolation
- **Comprehensive Audit**: Detailed audit trail with filtering and pagination

## Security Implementation

### Authentication & Authorization
- Bearer token authentication via `Authorization: Bearer <token>` header
- **Refined Scope System**: Simplified and logical permission structure
- Project-level tenancy isolation
- **Encrypted Credential Storage**: Secure multi-tenant credential management

### Required Scopes (Refined Structure)
**Asset Management:**
- `asset:read` - Asset state queries and metadata access
- `asset:metadata` - Asset configuration and metadata management
- `asset:write` - Asset creation and configuration changes
- `asset:command` - Real-time asset command execution

**Sensor Management:**
- `sensor:metadata` - Sensor configuration and metadata access
- `sensor:ingest` - Sensor data ingestion

**Administrative Operations:**
- `admin:audit` - Audit log access and compliance reporting
- `admin:credentials` - EXEDRA credential management
- `admin:*` - Full administrative access (policy, kill-switch, etc.)

### Advanced Security Features
1. **Multi-tenant Credentials**: AES-256 encrypted storage with per-client keys
2. **Environment Isolation**: Separate credential sets for dev/staging/prod
3. **Scope Validation**: Granular permission checking on all endpoints
4. **Audit Trail**: Complete request/response logging with error tracking

### Guardrails Implementation
1. **API Hygiene** (all modes): Basic validation (0-100% dimming, time formats, data types)
2. **Policy Guardrails** (optimize mode only): Rate limiting, min/max constraints, time restrictions
3. **Emergency Controls**: Kill switch for halting optimize mode operations
4. **Constraint Validation**: Database-level integrity checking

## Data Model & Architecture

### Database Implementation
The implementation perfectly aligns with your SQLAlchemy models:
- **UUID Primary Keys**: Consistent identifier strategy across all tables
- **Foreign Key Relationships**: Proper relational integrity with cascade handling
- **JSONB Metadata**: Flexible storage for device configurations and schedules
- **Indexing Strategy**: Optimized queries with strategic index placement
- **Constraint Enforcement**: Database-level validation and duplicate prevention

### Advanced Features
- **Idempotency Support**: Prevents duplicate operations via unique constraints
- **Multi-tenant Isolation**: Complete data separation by project
- **Encrypted Storage**: Secure credential management with AES-256 encryption
- **Audit Trail**: Comprehensive logging with technical and user-facing details

## Error Handling & Logging

### RFC 7807 Problem Details
All endpoints return standardized error responses:
- **400**: Bad Request - Validation errors with specific field details
- **401**: Unauthorized - Invalid API key or authentication failure
- **403**: Forbidden - Insufficient scopes for requested operation
- **404**: Not Found - Missing resources (assets, sensors, projects)
- **422**: Unprocessable Entity - Policy violations or business rule conflicts
- **500**: Internal Server Error - Unexpected system errors
- **503**: Service Unavailable - External service failures (EXEDRA, database)

### Dual Error Tracking
- **Technical Details**: Full exception information for debugging and monitoring
- **User-Facing Messages**: Clear, actionable error descriptions for API consumers
- **Audit Compliance**: Complete request/response logging for regulatory requirements

### Exception Coverage
Comprehensive handlers for all common error scenarios:
- `ValueError` - Business logic violations
- `IntegrityError` - Database constraint violations with user-friendly messages
- `ValidationError` - Request data validation failures
- `HTTPException` - API-level errors with proper status codes
- `RequestException` - External service communication failures
- `DatabaseError` / `SQLAlchemyError` - Database connectivity and operation errors

## Getting Started

### Database Setup
1. Ensure PostgreSQL is running with `adaptive_owner` and `adaptive_app` roles
2. Run the database migrations to create all tables and constraints
3. Execute the constraint fix: `fix_schedule_provider_constraint.sql`
4. Update scope catalogue: `update_scope_catalogue.sql`

### Sample Data Creation
1. **Projects**: Create test projects with unique codes (e.g., 'scs-dev', 'scs-prod')
2. **API Clients**: Generate clients with appropriate scope assignments
3. **EXEDRA Credentials**: Set up encrypted credentials for each environment
4. **Assets & Sensors**: Create test devices with proper EXEDRA mappings

### API Testing Workflow
1. **Asset Creation**: Use the new asset creation endpoint with EXEDRA integration
2. **Credential Management**: Test multi-tenant credential storage and retrieval
3. **Sensor Ingestion**: Verify data ingestion with proper validation
4. **Error Scenarios**: Test comprehensive error handling and audit logging

## Current Implementation Status

### ✅ Completed Features
- **Multi-tenant Architecture**: Complete project isolation with secure credential management
- **Asset Management**: Full CRUD operations with EXEDRA integration
- **Unified Logging**: Comprehensive audit system with dual error tracking
- **Advanced Security**: Refined scope system with granular permissions
- **Error Handling**: RFC 7807 compliant responses with full exception coverage
- **Database Integration**: Proper constraints, idempotency, and performance optimization

### 🚧 Pending Implementation (As Designed)
- **Background Services**: EXEDRA command relay and optimization workers
- **Real-time Features**: Asset state caching and live status updates
- **Email Notifications**: Alert system for policy violations and system events
- **Advanced Analytics**: Optimization algorithm integration

### 🔄 Recent Architectural Improvements
- **Logging Consolidation**: 5 separate files → 1 unified system
- **Permission Refinement**: Simplified scope structure with logical groupings
- **Error Message Clarity**: User-friendly messages with technical debugging details
- **Field Naming**: Clear EXEDRA field mapping (exedra_id, exedra_name, etc.)
- **Constraint Alignment**: Database and application validation synchronization

## API Documentation

The API is fully documented with OpenAPI/Swagger and includes:
- Interactive endpoint testing via FastAPI's automatic documentation
- Comprehensive schema definitions with validation rules
- Example requests and responses for all endpoints
- Detailed error response documentation with problem details format

Access the interactive API documentation at: `http://localhost:8000/docs`