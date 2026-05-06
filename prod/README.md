# FireBridge Production Endpoints

Endpoints intended for the actual wallpanel deployment. They use a flat topic layout (`${base_topic}/<feature>/...`) and short Home Assistant names, in contrast to the example endpoints under `../examples/` which prefix everything with `example_`.

## Mounting in production

The shipped `compose.yml` mounts `./examples` for the demo experience. To use these instead, swap the volume in `compose.yml`:

```yaml
volumes:
  - ./prod:/config/endpoints:ro
```

Or override per-run:

```bash
CONFIG_DIR=/config/endpoints docker compose run --rm -v ./prod:/config/endpoints:ro firebridge serve
```

## Endpoints

| File | Kind | HA Component | Notes |
|---|---|---|---|
| `display-pin.yaml` | action | switch | Wakes / sleeps display, enters `UNLOCK_PIN` on wake. Disables auto-sleep while on. |
| `immersive-mode.yaml` | action | select | `full` / `navigation` / `status` / `reset` via Android `policy_control`. |
| `brightness.yaml` | action | number (slider 0–255) | `settings put system screen_brightness`. |
| `media-volume.yaml` | action | number (slider 0–15) | `media volume --stream 3 --set <n>`. |
| `open-url.yaml` | action | text | Opens an `http(s)://` URL via `am start` intent. Rejects non-http URLs. |
| `foreground-app.yaml` | sensor | sensor (cron 1/min) | Publishes the foreground package name, or `off` when the display is off / dozing. |
| `wifi-killswitch.yaml` | action | button | One-way disable: `svc wifi disable`. Guarded by payload `KILL_WIFI`; no enable counterpart by design. |
| `shutdown.yaml` | action | button | `reboot -p`. Guarded by payload `SHUTDOWN`. |

## Required environment variables

- `UNLOCK_PIN` — read by `display-pin.yaml` from the env, marked `secret: true` so it is redacted in dry-runs and reports.
- All standard `MQTT_*` and `DEVICE_*` settings from `.env-example`.

## Safety guards

The `wifi-killswitch` and `shutdown` endpoints both declare a `choice` input bound to a single accepted token (`KILL_WIFI` / `SHUTDOWN`). The Home Assistant button discovery sets `payload_press` to the same token, so the buttons fire correctly while ad-hoc MQTT publishes with arbitrary payloads are rejected before any ADB command runs.
