# Makefile — HoneyBeeSMP monorepo
#
# Thin entry point for common tasks on the server. POSIX sh friendly:
# the server has no node, so nothing here depends on it.
#
# There are two environments:
#   dev   the develop branch, dev.honeybeesmp.co.uk, the DEV MC server
#   live  the main branch, honeybeesmp.co.uk, the LIVE MC server
#
# Usage:  make help

SHELL := /bin/sh

REPO_DIR     := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
WEB_SRC      := $(REPO_DIR)/website
WEB_ROOT     := /var/www/honeybeesmp.co.uk
WEB_ROOT_DEV := /var/www/honeybeesmp.dev
BOT_SRC      := $(REPO_DIR)/bot
CRAFTY_COMPOSE := /opt/crafty/docker-compose.yml

# Crafty server ids, from minecraft/env/*/env.conf
DEV_SERVER  := d48afa12-59a5-496e-829a-1ced86d108b5
LIVE_SERVER := 119045e1-1fac-41a0-83c0-5e2d85ce4c78

.DEFAULT_GOAL := help
.PHONY: help deploy deploy-web deploy-bot deploy-dev deploy-dev-web deploy-dev-bot \
        deploy-mc deploy-mc-dev status check pull log \
        crafty-up crafty-down crafty-logs \
        mc-status mc-status-dev mc-restart mc-restart-dev \
        backup backup-log update update-dev \
        modpack modpack-add modpack-publish modpack-status modpack-verify

help: ## Show this help
	@echo "HoneyBeeSMP — available targets:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo

# --- Deploying --------------------------------------------------------------

deploy: deploy-web deploy-bot deploy-mc ## Deploy everything to the live env

deploy-web: ## Copy website/ to the live nginx web root
	@sh "$(REPO_DIR)/scripts/deploy.sh" live web

deploy-bot: ## Copy bot/ to the live bot directory (never .env)
	@sh "$(REPO_DIR)/scripts/deploy.sh" live bot

deploy-mc: ## Apply the Minecraft config to the live server
	@sh "$(REPO_DIR)/scripts/deploy.sh" live minecraft

deploy-dev: deploy-dev-web deploy-dev-bot ## Deploy the website and bot to dev

deploy-dev-web: ## Copy website/ to the dev nginx web root
	@sh "$(REPO_DIR)/scripts/deploy.sh" dev web

deploy-dev-bot: ## Copy bot/ to the dev bot directory
	@sh "$(REPO_DIR)/scripts/deploy.sh" dev bot

deploy-mc-dev: ## Apply the Minecraft config to the dev server
	@sh "$(REPO_DIR)/scripts/deploy.sh" dev minecraft

# --- Pulling and updating ---------------------------------------------------

update: ## Pull main, check, deploy to live, reload nginx
	@sh "$(REPO_DIR)/scripts/update.sh" live all

update-dev: ## Pull develop, check, deploy to dev, reload nginx
	@sh "$(REPO_DIR)/scripts/update.sh" dev all

pull: ## Fast-forward from origin
	@git -C "$(REPO_DIR)" pull --ff-only

log: ## Recent commits
	@git -C "$(REPO_DIR)" log --oneline -10

check: ## Verify the repo is sane before committing/pushing
	@sh "$(REPO_DIR)/scripts/check.sh"

status: ## Show git, service and deploy status
	@echo "== git =="
	@git -C "$(REPO_DIR)" status -sb
	@echo
	@echo "== services =="
	@printf "nginx:  "; systemctl is-active nginx
	@printf "docker: "; systemctl is-active docker
	@printf "crafty: "; sudo docker inspect -f "{{.State.Status}}" crafty_container 2>/dev/null || echo "absent"
	@echo
	@echo "== drift (website vs live web root) =="
	@diff -rq "$(WEB_SRC)" "$(WEB_ROOT)" 2>/dev/null && echo "in sync" || true

# --- Minecraft servers ------------------------------------------------------

mc-status: ## Is the live Minecraft server running?
	@sh "$(REPO_DIR)/scripts/crafty.sh" status $(LIVE_SERVER)

mc-status-dev: ## Is the dev Minecraft server running?
	@sh "$(REPO_DIR)/scripts/crafty.sh" status $(DEV_SERVER)

mc-restart: ## Restart the live Minecraft server (kicks players)
	@sh "$(REPO_DIR)/scripts/crafty.sh" restart $(LIVE_SERVER)

mc-restart-dev: ## Restart the dev Minecraft server
	@sh "$(REPO_DIR)/scripts/crafty.sh" restart $(DEV_SERVER)

# --- Crafty panel -----------------------------------------------------------

crafty-up: ## Start the Crafty panel
	sudo docker compose -f "$(CRAFTY_COMPOSE)" up -d

crafty-down: ## Stop the Crafty panel
	sudo docker compose -f "$(CRAFTY_COMPOSE)" down

crafty-logs: ## Tail Crafty logs
	sudo docker logs -f crafty_container

# --- Backups ----------------------------------------------------------------

backup: ## Run a backup to Google Drive now
	@sh "$(REPO_DIR)/scripts/backup.sh"

backup-log: ## Show the backup log
	@tail -30 "$(REPO_DIR)/logs/backup.log" 2>/dev/null || echo "no backup log yet"

# --- Modpack ----------------------------------------------------------------

modpack: ## Show what is in the modpack
	@python3 "$(REPO_DIR)/scripts/modpack.py" list

modpack-add: ## Add a mod to the modpack: make modpack-add SLUG=create
	@test -n "$(SLUG)" || { echo "usage: make modpack-add SLUG=<modrinth-slug>"; exit 2; }
	@python3 "$(REPO_DIR)/scripts/modpack.py" add "$(SLUG)" --env dev

modpack-publish: ## Bump the pack version and publish it to Modrinth
	@python3 "$(REPO_DIR)/scripts/modpack.py" bump
	@python3 "$(REPO_DIR)/scripts/publish-modpack.py" publish

modpack-status: ## Show the Modrinth project and its latest version
	@python3 "$(REPO_DIR)/scripts/publish-modpack.py" status

modpack-verify: ## Check the live server's mods against the pack
	@python3 "$(REPO_DIR)/scripts/modpack.py" verify /opt/crafty/servers/119045e1-1fac-41a0-83c0-5e2d85ce4c78/mods
