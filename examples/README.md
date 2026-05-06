# FireBridge Examples

These YAML files are examples for the generic FireBridge workflow runner. The default `compose.yml` mounts this directory to `/config/endpoints`, so all examples become active MQTT endpoints when running `docker compose build && docker compose up`.

Use them for local dry-runs:

```bash
python3 main.py workflows list --config-dir examples
UNLOCK_PIN=change-me python3 main.py workflows run example_display_pin --payload ON --dry-run --config-dir examples
python3 main.py workflows run example_immersive_mode --payload full --dry-run --config-dir examples
python3 main.py workflows run example_app_selector --payload Settings --dry-run --config-dir examples
```

Important notes:

- `battery-sensor.yaml` includes a classic cron schedule: `* * * * *`, so it runs once per minute and also on service start.
- `immersive-mode.yaml` uses Android `policy_control`. It hides bars, but users can usually reveal them temporarily by swiping from the edge.
- `kiosk-device-owner.yaml` is intentionally guarded by a confirmation payload. Device Owner setup usually requires a freshly reset device without an account configured.
- `app-selector.yaml` uses static MQTT `select` choices. Edit the mapped names and package values in YAML to match the apps installed on your tablet.
- Example endpoint IDs use the `example_` prefix to avoid conflicts with production endpoint IDs.
