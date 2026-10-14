---
name: homeassistant
description: >
  Control and configure Home Assistant devices, scenes, automations, and entities.
  Simple operations (lights, media, scripts, queries) use the MCP server. Advanced
  operations (scene editing, config store, history, service discovery) fall back to
  the REST API. Use when the user says "turn on the lights", "set a scene",
  "edit scene", "home assistant", "HA", "smart home", "check the lights",
  "activate scene", "what's the temperature", "play music on speaker",
  "create a scene", "update scene", "home automation", or references any
  Home Assistant entity or device.
---

# Home Assistant

Control and configure Home Assistant via MCP (simple ops) and REST API (advanced ops).

## Execution

### MCP Tools (simple operations)

Use for everyday device control, queries, and triggering existing scripts/scenes:

```bash
mcporter call homeassistant.<tool> [args]
```

Available MCP tools include: `HassTurnOn`, `HassTurnOff`, `HassLightSet`, `HassMediaSearchAndPlay`,
`HassMediaPause`, `HassMediaUnpause`, `HassSetVolume`, `HassBroadcast`, `HassListAddItem`,
`todo_get_items`, `GetLiveContext`, `GetDateTime`, and various named scripts/scenes.

Run `mcporter list homeassistant` for full tool signatures. Do not duplicate MCP tool docs here.

### REST API (advanced operations)

Use when MCP tools don't cover the operation — scene config editing, entity inspection,
history queries, service discovery, arbitrary service calls, automation management.

```python
import requests, json, os

BASE = "http://<homeassistant-host>:8123"
TOKEN = os.environ.get("HOME_ASSISTANT_TOKEN", "<from mcporter config>")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Example: read scene config
r = requests.get(f"{BASE}/api/config/scene/config/{scene_id}", headers=H)

# Example: call a service
r = requests.post(f"{BASE}/api/services/{domain}/{service}", headers=H, json=payload)
```

See `references/rest-api.md` for the full endpoint reference.

#### Token Resolution

The token is stored in `config/mcporter.json` under `mcpServers.homeassistant.env.HOME_ASSISTANT_TOKEN`.
Read it from there when making REST API calls — never hardcode it in scripts.

```python
import json
with open(os.path.expanduser("~/.openclaw/workspace/config/mcporter.json")) as f:
    TOKEN = json.load(f)["mcpServers"]["homeassistant"]["env"]["HOME_ASSISTANT_TOKEN"]
```

## When to Use MCP vs REST API

| Need | Use |
|------|-----|
| Turn lights on/off, set brightness/color | MCP `HassTurnOn` / `HassLightSet` |
| Play/pause media | MCP `HassMediaSearchAndPlay` / `HassMediaPause` |
| Query current device state | MCP `GetLiveContext` |
| Trigger existing scenes/scripts | MCP `HassTurnOn` with scene name |
| Read/edit scene configuration | REST API `/api/config/scene/config/<id>` |
| List all entities/services | REST API `/api/states` or `/api/services` |
| Call arbitrary services | REST API `/api/services/<domain>/<service>` |
| Query history/logbook | REST API `/api/history/period/` |
| Render templates | REST API `/api/template` |
| Create/delete scenes | REST API `scene.create` / `scene.delete` via service call |

## Common REST API Patterns

### Scene Config (read)

```python
r = requests.get(f"{BASE}/api/config/scene/config/{scene_id}", headers=H)
scene = r.json()  # {id, name, icon, entities: {entity_id: {state, brightness, ...}}}
```

### Scene Config (update)

```python
payload = {
    "id": scene_id,
    "name": "Scene Name",
    "icon": "mdi:icon-name",
    "entities": {
        "light.example": {"state": "on", "brightness": 255},
        "light.other": {"state": "off"}
    }
}
r = requests.post(f"{BASE}/api/config/scene/config/{scene_id}", headers=H, json=payload)
# Returns {"result": "ok"} on success
```

### Activate a Scene

```python
r = requests.post(f"{BASE}/api/services/scene/turn_on", headers=H,
                   json={"entity_id": "scene.work"})
```

### Service Call

```python
r = requests.post(f"{BASE}/api/services/{domain}/{service}", headers=H, json=service_data)
```

### List All Scenes

```python
r = requests.get(f"{BASE}/api/states", headers=H)
scenes = [s for s in r.json() if s["entity_id"].startswith("scene.")]
```

## Reference

| Entity | Name | ID / Entity ID |
|--------|------|----------------|
| Scene | After work | `1719380903027` / `scene.after_work` |
| Scene | Movie Mode | `1728268454957` / `scene.movie_mode` |
| Scene | Work | `1762269164553` / `scene.work` |
| Scene | Movie | `1763516044553` / `scene.movie` |
| Scene | Bed | `1769151762815` / `scene.bed` |

| Config | Value |
|--------|-------|
| Local endpoint | `http://<homeassistant-host>:8123` |
| Nabu Casa endpoint | `https://<your-instance>.ui.nabu.casa` |
| Preferred endpoint | Local (faster) |

> **Maintenance:** Update scene/entity tables as new scenes or devices are added.

## Conventions

- Use MCP tools first for simple operations; only fall back to REST API when needed
- Confirm before destructive operations (deleting scenes, entities, or automations)
- Always verify after config writes (read back the config to confirm)
- Present entity states and scene configs as clean summaries, not raw JSON
- When editing scenes, show the user what will change before writing
- Prefer local endpoint over Nabu Casa for speed
- Never hardcode the auth token — always read from mcporter config

## Authentication

Token stored in `config/mcporter.json` at `mcpServers.homeassistant.env.HOME_ASSISTANT_TOKEN`.
Same token works for both MCP and REST API endpoints.

## Requirements

- `mcporter` for MCP tool access
- `requests` Python library for REST API calls (available in system Python)
- Network access to `<homeassistant-host>:8123` (local) or Nabu Casa remote URL

## Troubleshooting

### MCP tool not found
Run `mcporter list homeassistant` to see available tools. Tool names follow HA intent naming.

### REST API 401
Token may have expired. Check `config/mcporter.json` for the current token value.

### Local endpoint unreachable
Fall back to Nabu Casa remote endpoint. Both accept the same token.

### Scene config endpoint returns 404
The scene ID in the URL must be the numeric `id` from the scene config, not the `entity_id`.
