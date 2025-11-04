# Complete API Permission-to-Endpoint Mapping

## Asset Permissions

### `asset:read`
**Description**: Read asset state and current operational status
**Endpoints**:
- `GET /v1/{project_code}/asset/state?asset_external_id={id}` - Get current asset state and dimming level
- `GET /v1/{project_code}/asset/schedule?asset_external_id={id}` - Get current active schedule

### `asset:metadata`
**Description**: Read asset metadata, configuration details, and specifications
**Endpoints**:
- `GET /v1/{project_code}/asset/{external_id}` - Get asset metadata and configuration details

### `asset:write`
**Description**: Create assets and update metadata, configuration, and control mode
**Endpoints**:
- `POST /v1/{project_code}/asset/` - Create new assets with EXEDRA integration (using exedra_id, exedra_name, etc.)
- `PUT /v1/{project_code}/asset/mode/{external_id}` - Change asset control mode (optimise/passthrough)

### `asset:command`
**Description**: Execute asset commands (schedules and real-time dimming)
**Endpoints**:
- `PUT /v1/{project_code}/asset/schedule?asset_external_id={id}` - Update asset lighting schedule
- `POST /v1/{project_code}/asset/realtime` - Send real-time dimming commands

## Sensor Permissions

### `sensor:read`
**Description**: Read sensor operational status and current readings
**Endpoints**:
- *(Currently no specific endpoints - placeholder for future sensor status endpoints)*

### `sensor:metadata`
**Description**: Read sensor metadata, configuration, and capabilities
**Endpoints**:
- `GET /v1/{project_code}/sensor/{external_id}` - Get sensor metadata and configuration details

### `sensor:write`
**Description**: Update sensor configuration and metadata
**Endpoints**:
- *(Currently no specific endpoints - placeholder for future sensor configuration endpoints)*

### `sensor:ingest`
**Description**: Submit sensor data readings
**Endpoints**:
- `POST /v1/{project_code}/sensor/ingest` - Submit vehicle/pedestrian count and speed data

## Administrative Permissions

### `admin:policy:read`
**Description**: Read system policy configurations
**Endpoints**:
- `GET /v1/{project_code}/admin/policy` - Get current policy configuration

### `admin:policy:write`
**Description**: Create and update system policies
**Endpoints**:
- `POST /v1/{project_code}/admin/policy` - Create or update system policy

### `admin:killswitch`
**Description**: Enable/disable system kill switch
**Endpoints**:
- `POST /v1/{project_code}/admin/killswitch` - Toggle system kill switch

### `admin:audit`
**Description**: Read system audit logs
**Endpoints**:
- `GET /v1/{project_code}/admin/audit` - Retrieve audit log entries

### `admin:credentials`
**Description**: Store and manage client credentials (EXEDRA keys, etc.)
**Endpoints**:
- `POST /v1/{project_code}/admin/credentials` - Store client credentials (EXEDRA tokens, etc.)

### `admin:apikeys:write`
**Description**: Generate and manage API keys for clients
**Endpoints**:
- `POST /v1/{project_code}/admin/apikey` - Generate new API keys for clients

---

## Summary by HTTP Method

### GET (Read Operations)
- `asset:read` - Asset state and schedules
- `asset:metadata` - Asset configuration details
- `sensor:metadata` - Sensor configuration details  
- `admin:policy:read` - Policy configurations
- `admin:audit` - Audit logs

### POST (Create/Action Operations)
- `asset:write` - Create assets
- `asset:command` - Real-time commands
- `sensor:ingest` - Submit sensor data
- `admin:policy:write` - Create policies
- `admin:killswitch` - Toggle kill switch
- `admin:credentials` - Store credentials
- `admin:apikeys:write` - Generate API keys

### PUT (Update Operations)
- `asset:write` - Update asset control modes
- `asset:command` - Update schedules

---

## Role-Based Endpoint Access Examples

### **Monitoring Service** (`asset:read`, `sensor:read`)
```
✅ GET /asset/state
✅ GET /asset/schedule
❌ GET /asset/{id} (needs asset:metadata)
❌ POST /asset/realtime (needs asset:command)
```

### **Sensor Provider** (`asset:read`, `asset:command`, `sensor:ingest`)
```
✅ GET /asset/state
✅ GET /asset/schedule
✅ PUT /asset/schedule
✅ POST /asset/realtime
✅ POST /sensor/ingest
❌ GET /asset/{id} (needs asset:metadata)
❌ POST /asset/ (needs asset:write)
```

### **Asset Administrator** (`asset:read`, `asset:metadata`, `asset:write`)
```
✅ GET /asset/state
✅ GET /asset/schedule  
✅ GET /asset/{id}
✅ POST /asset/
✅ PUT /asset/mode/{id}
❌ PUT /asset/schedule (needs asset:command)
❌ POST /admin/policy (needs admin:policy:write)
```