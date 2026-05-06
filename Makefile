COMPOSE ?= docker compose

.PHONY: help build up up-detached down restart logs ps shell adb-kill

help:
	@echo "Targets:"
	@echo "  build         Build the firebridge image"
	@echo "  up            Free the USB device and start firebridge in the foreground"
	@echo "  up-detached   Same as 'up' but detached"
	@echo "  down          Stop and remove the container"
	@echo "  restart       down + up-detached"
	@echo "  logs          Tail container logs"
	@echo "  ps            Show compose status"
	@echo "  shell         Open a shell in the running container"
	@echo "  adb-kill      Kill the host adb server (releases the USB device)"

build:
	$(COMPOSE) build

up: adb-kill
	$(COMPOSE) up

up-detached: adb-kill
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart: down up-detached

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec firebridge bash

# A host-side adb server holds the USB device exclusively, which prevents the
# container's adb from claiming it ("no devices/emulators found"). Killing it
# before bringing the container up hands ownership over.
adb-kill:
	@if command -v adb >/dev/null 2>&1; then \
		adb kill-server >/dev/null 2>&1 || true; \
	fi
