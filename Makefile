# Makefile — HoneyBeeSMP monorepo
#
# Thin entry point for common tasks on the server. POSIX sh friendly:
# the server has no node, so nothing here depends on it.
#
# Usage:  make help

SHELL := /bin/sh

REPO_DIR     := $(shell cd "$(dir $(lastword $(MAKEFILE_LIST)))" && pwd)
WEB_SRC      := $(REPO_DIR)/website
WEB_ROOT     := /var/www/honeybeesmp.co.uk
BOT_SRC      := $(REPO_DIR)/bot
BOT_DEST     := /opt/honeybee-discord-bot
CRAFTY_COMPOSE := /opt/crafty/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help deploy deploy-web deploy-bot status check pull sync log crafty-up crafty-down crafty-logs

help: ## Show this help
	@echo "HoneyBeeSMP — available targets:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo

deploy: deploy-web ## Deploy everything that needs deploying

deploy-web: ## Copy website/ to the nginx web root
	@echo "==> deploying website -> $(WEB_ROOT)"
	rsync -a --delete --no-group --no-perms --omit-dir-times --chmod=Fg+rw "$(WEB_SRC)/" "$(WEB_ROOT)/"
	@echo "==> done. $(shell ls -1 $(WEB_ROOT) | wc -l) file(s) in place"

deploy-bot: ## Copy bot/ skeleton to /opt/honeybee-discord-bot (never .env)
	@echo "==> deploying bot -> $(BOT_DEST)"
	rsync -a --no-group --no-perms --omit-dir-times --exclude-from="$(BOT_SRC)/.rsync-exclude" \
		--chmod=Fg+rw "$(BOT_SRC)/" "$(BOT_DEST)/"
	@echo "==> done"

status: ## Show git, service and deploy status
	@echo "== git =="
	@git -C "$(REPO_DIR)" status -sb
	@echo
	@echo "== services =="
	@printf "nginx:  "; systemctl is-active nginx
	@printf "docker: "; systemctl is-active docker
	@printf "crafty: "; sudo docker inspect -f "{{.State.Status}}" crafty_container 2>/dev/null || echo "absent"
	@echo
	@echo "== drift (website vs web root) =="
	@diff -rq "$(WEB_SRC)" "$(WEB_ROOT)" 2>/dev/null && echo "in sync" || true

check: ## Verify the repo is sane before committing/pushing
	@sh "$(REPO_DIR)/scripts/check.sh"

pull: ## Fast-forward from origin
	@git -C "$(REPO_DIR)" pull --ff-only

log: ## Recent commits
	@git -C "$(REPO_DIR)" log --oneline -10

crafty-up: ## Start the Crafty panel
	sudo docker compose -f "$(CRAFTY_COMPOSE)" up -d

crafty-down: ## Stop the Crafty panel
	sudo docker compose -f "$(CRAFTY_COMPOSE)" down

crafty-logs: ## Tail Crafty logs
	sudo docker logs -f crafty_container
