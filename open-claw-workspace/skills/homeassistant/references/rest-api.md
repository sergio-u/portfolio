# Home Assistant REST API Reference

Source: https://developers.home-assistant.io/docs/api/rest/

HA provides a RESTful API on the same port as the web frontend (default 8123).

All API calls require `Authorization: Bearer TOKEN` header. Returns JSON.

## Status Codes

- 200/201: Success
- 400: Bad Request
- 401: Unauthorized
- 404: Not Found
- 405: Method Not Allowed

## Endpoints

### Read

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/` | API health check |
| GET | `/api/config` | Current HA configuration |
| GET | `/api/states` | All entity states |
| GET | `/api/states/<entity_id>` | Single entity state (404 if missing) |
| GET | `/api/services` | All available services by domain |
| GET | `/api/events` | Event types + listener counts |
| GET | `/api/history/period/<timestamp>` | State history (requires `filter_entity_id`) |
| GET | `/api/logbook/<timestamp>` | Logbook entries |
| GET | `/api/calendars` | List calendar entities |
| GET | `/api/calendars/<entity_id>?start=<ts>&end=<ts>` | Calendar events in range |
| GET | `/api/error_log` | Error log (plaintext) |
| GET | `/api/camera_proxy/<entity_id>` | Camera image data |

### Write

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/states/<entity_id>` | Create/update entity state |
| POST | `/api/services/<domain>/<service>` | Call a service |
| POST | `/api/events/<event_type>` | Fire an event |
| POST | `/api/template` | Render a Jinja2 template |
| POST | `/api/config/core/check_config` | Validate configuration.yaml |
| POST | `/api/intent/handle` | Handle an intent |
| DELETE | `/api/states/<entity_id>` | Delete an entity |

### Config Store (undocumented but functional)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config/scene/config/<scene_id>` | Read scene config by numeric ID |
| POST | `/api/config/scene/config/<scene_id>` | Update scene config by numeric ID |

### History Parameters

- `filter_entity_id=<ids>` (required, comma-separated)
- `end_time=<timestamp>` (optional, URL-encoded)
- `minimal_response` (optional, faster)
- `no_attributes` (optional, faster)
- `significant_changes_only` (optional)

### Service Call Notes

- `POST /api/services/<domain>/<service>` returns changed states
- Add `?return_response` for services that return data
- Some services require `return_response`, some reject it — 400 if mismatched
