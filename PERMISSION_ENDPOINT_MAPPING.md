# Complete API Permission-to-Endpoint Mapping

## Asset Permissions

### `asset:read`
**Description**: Read asset state and current operational status
**Endpoints**:
- `GET /v1/{project_code}/asset/state/{exedra_id}` - Get current asset state and dimming level
- `GET /v1/{project_code}/asset/schedule/{exedra_id}` - Get current active schedule

### `asset:metadata`
**Description**: Read asset metadata, configuration details, and specifications
**Endpoints**:
- `GET /v1/{project_code}/asset/{exedra_id}` - Get asset metadata and configuration details

### `asset:create`
**Description**: Create new assets
**Endpoints**:
- `POST /v1/{project_code}/asset/` - Create new assets with EXEDRA integration

### `asset:update`
**Description**: Update asset metadata, configuration, and control mode
**Endpoints**:
- `PUT /v1/{project_code}/asset/{exedra_id}` - Update asset metadata and configuration
- `PUT /v1/{project_code}/asset/mode/{exedra_id}` - Change asset control mode (optimise/passthrough)

### `asset:delete`
**Description**: Delete assets and their associated data
**Endpoints**:
- `DELETE /v1/{project_code}/asset/{exedra_id}` - Delete asset and associated data

### `asset:command`
**Description**: Execute asset commands (schedules and real-time dimming)
**Endpoints**:
- `PUT /v1/{project_code}/asset/schedule/{exedra_id}` - Update asset lighting schedule
- `POST /v1/{project_code}/asset/realtime/{exedra_id}` - Send real-time dimming commands

## Sensor Permissions

### `sensor:read`
**Description**: Read sensor operational status and current readings
**Endpoints**:
- *(Currently no specific endpoints - placeholder for future sensor status endpoints)*

### `sensor:metadata`
**Description**: Read sensor metadata, configuration, and capabilities
**Endpoints**:
- `GET /v1/{project_code}/sensor/{external_id}` - Get sensor metadata and configuration details
- `GET /v1/{project_code}/sensor/type/` - List all sensor types
- `GET /v1/{project_code}/sensor/type/{sensor_type_id}` - Get sensor type details

### `sensor:create`
**Description**: Create new sensors and sensor-to-asset links
**Endpoints**:
- `POST /v1/{project_code}/sensor/` - Create new sensor with asset links

### `sensor:update`
**Description**: Update sensor configuration, metadata, and asset links
**Endpoints**:
- `PUT /v1/{project_code}/sensor/{external_id}` - Update sensor details and asset links

### `sensor:delete`
**Description**: Delete sensors and their associated data
**Endpoints**:
- `DELETE /v1/{project_code}/sensor/{external_id}` - Delete sensor and associated data

### `sensor:ingest`
**Description**: Submit sensor data readings
**Endpoints**:
- `POST /v1/{project_code}/sensor/ingest` - Submit vehicle/pedestrian count and speed data

## Sensor Type Permissions

### `sensor:type:create`
**Description**: Create new sensor types
**Endpoints**:
- `POST /v1/{project_code}/sensor/type` - Create new sensor type

### `sensor:type:update`
**Description**: Update sensor type details and capabilities
**Endpoints**:
- `PUT /v1/{project_code}/sensor/type/{sensor_type_id}` - Update sensor type details

### `sensor:type:delete`
**Description**: Delete sensor types
**Endpoints**:
- `DELETE /v1/{project_code}/sensor/type/{sensor_type_id}` - Delete sensor type

## Administrative Permissions

### `admin:policy:read`
**Description**: Read system policy configurations
**Endpoints**:
- `GET /v1/{project_code}/admin/policy` - Get current policy configuration

### `admin:policy:create`
**Description**: Create new system policies
**Endpoints**:
- `POST /v1/{project_code}/admin/policy` - Create new system policy

### `admin:policy:update`
**Description**: Update existing system policies
**Endpoints**:
- `PUT /v1/{project_code}/admin/policy/{policy_id}` - Update existing policy

### `admin:killswitch`
**Description**: Enable/disable system kill switch
**Endpoints**:
- `POST /v1/{project_code}/admin/kill-switch` - Toggle system kill switch
- `GET /v1/{project_code}/admin/kill-switch` - Get kill switch status

### `admin:audit`
**Description**: Read system audit logs
**Endpoints**:
- `GET /v1/{project_code}/admin/audit-logs` - Retrieve audit log entries

### `admin:credentials`
**Description**: Store and manage client credentials (EXEDRA keys, etc.)
**Endpoints**:
- `POST /v1/{project_code}/admin/exedra-config` - Store client credentials (EXEDRA tokens, etc.)

### `admin:apikey:read`
**Description**: Read API keys and available scopes
**Endpoints**:
- `GET /v1/{project_code}/admin/scopes` - List available scopes and recommended combinations
- `GET /v1/{project_code}/admin/api-key` - Get current API key information and permissions

### `admin:apikey:create`
**Description**: Generate new API keys for clients
**Endpoints**:
- `POST /v1/{project_code}/admin/api-key` - Generate new API keys for clients

### `admin:apikey:update`
**Description**: Update API key details and scopes
**Endpoints**:
- `PUT /v1/{project_code}/admin/api-key/{api_key_id}` - Update API key scopes
- `POST /v1/{project_code}/admin/scopes/sync` - Sync scope catalogue to database

### `admin:apikey:delete`
**Description**: Revoke and delete API keys
**Endpoints**:
- `DELETE /v1/{project_code}/admin/api-key/{api_key_id}` - Revoke API key

---

## Summary by HTTP Method

### GET (Read Operations)
- `asset:read` - Asset state and schedules
- `asset:metadata` - Asset configuration details
- `sensor:metadata` - Sensor configuration details and sensor types
- `admin:policy:read` - Policy configurations
- `admin:killswitch` - Kill switch status
- `admin:audit` - Audit logs
- `admin:apikey:read` - Available scopes and permissions

### POST (Create Operations)
- `asset:create` - Create assets
- `sensor:create` - Create sensors
- `sensor:type:create` - Create sensor types
- `sensor:ingest` - Submit sensor data
- `asset:command` - Real-time commands
- `admin:policy:create` - Create policies
- `admin:killswitch` - Toggle kill switch
- `admin:credentials` - Store credentials
- `admin:apikey:create` - Generate API keys
- `admin:apikey:update` - Sync scope catalogue

### PUT (Update Operations)
- `asset:update` - Update asset details and control modes
- `sensor:update` - Update sensor details
- `sensor:type:update` - Update sensor types
- `asset:command` - Update schedules
- `admin:policy:update` - Update policies
- `admin:apikey:update` - Update API key scopes

### DELETE (Delete Operations)
- `asset:delete` - Delete assets
- `sensor:delete` - Delete sensors
- `sensor:type:delete` - Delete sensor types
- `admin:apikey:delete` - Revoke API keys

---

## Role-Based Endpoint Access Examples

### **Monitoring Service** (`asset:read`, `sensor:read`)
```
✅ GET /asset/state/{id}
✅ GET /asset/schedule/{id}
❌ GET /asset/{id} (needs asset:metadata)
❌ POST /asset/realtime/{id} (needs asset:command)
```

### **Sensor Provider** (`asset:read`, `asset:command`, `sensor:ingest`)
```
✅ GET /asset/state/{id}
✅ GET /asset/schedule/{id}
✅ PUT /asset/schedule/{id}
✅ POST /asset/realtime/{id}
✅ POST /sensor/ingest
❌ GET /asset/{id} (needs asset:metadata)
❌ POST /asset/ (needs asset:create)
```

### **Asset Administrator** (`asset:read`, `asset:metadata`, `asset:create`, `asset:update`, `asset:delete`)
```
✅ GET /asset/state/{id}
✅ GET /asset/schedule/{id}
✅ GET /asset/{id}
✅ POST /asset/
✅ PUT /asset/{id}
✅ PUT /asset/mode/{id}
✅ DELETE /asset/{id}
❌ PUT /asset/schedule/{id} (needs asset:command)
❌ POST /admin/policy (needs admin:policy:write)
```

### **Sensor Administrator** (`sensor:metadata`, `sensor:create`, `sensor:update`, `sensor:delete`, `sensor:type:create`, `sensor:type:update`, `sensor:type:delete`)
```
✅ GET /sensor/{id}
✅ GET /sensor/type/
✅ GET /sensor/type/{id}
✅ POST /sensor/
✅ PUT /sensor/{id}
✅ DELETE /sensor/{id}
✅ POST /sensor/type
✅ PUT /sensor/type/{id}
✅ DELETE /sensor/type/{id}
❌ POST /sensor/ingest (needs sensor:ingest)
```

### **Integration Service** (`asset:read`, `asset:command`, `sensor:read`, `sensor:ingest`)
```
✅ GET /asset/state/{id}
✅ GET /asset/schedule/{id}
✅ PUT /asset/schedule/{id}
✅ POST /asset/realtime/{id}
✅ POST /sensor/ingest
❌ GET /asset/{id} (needs asset:metadata)
❌ POST /asset/ (needs asset:create)
❌ GET /sensor/{id} (needs sensor:metadata)
```