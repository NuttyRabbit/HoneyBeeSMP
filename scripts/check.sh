#!/bin/sh
# check.sh — pre-commit / CI sanity check.
#
# Verifies the things that actually go wrong in this repo:
#   1. no secrets accidentally staged
#   2. no oversized files (Minecraft data sneaking in)
#   3. website has an index.html
#   4. .gitignore still covers the sensitive paths
#
# Runs with plain sh + git. No node/python needed.
# Exit 0 = OK, 1 = problem found.

set -eu

cd "$(git rev-parse --show-toplevel)"

fail=0
note() { printf '  %s %s\n' "$1" "$2"; }
ok()   { note "OK  " "$1"; }
bad()  { note "FAIL" "$1"; fail=1; }

echo "== check: secrets =="
# Refuse anything that looks like a live credential, by filename.
if git ls-files | grep -qiE '(^|/)\.env$|\.pem$|\.key$|credential|default-creds|\.sqlite'; then
	bad "a tracked file looks like a secret:"
	git ls-files | grep -iE '(^|/)\.env$|\.pem$|\.key$|credential|default-creds|\.sqlite' | sed 's/^/       /'
else
	ok "no secret-looking file names tracked"
fi

# And by content. A filename check alone misses a credential pasted into
# a README or a script, which matters now that this repo is public.
#
# These are the shapes of the secrets this project actually uses:
#   - a Modrinth personal access token   mrp_...
#   - an SSH private key                 -----BEGIN OPENSSH PRIVATE KEY-----
#   - a Google API client secret         GOCSPX-...
#   - a Discord bot token                a long base64-ish string
# The last one is deliberately loose, so it only matches when it is
# clearly labelled as a token.
SECRET_PATTERN='mrp_[A-Za-z0-9]{40,}|BEGIN (OPENSSH|RSA|EC|PGP) PRIVATE KEY|GOCSPX-[A-Za-z0-9_-]{20,}|DISCORD_TOKEN=[A-Za-z0-9._-]{40,}'
# Some files legitimately contain the *shape* of a secret - the workflow
# prints the placeholder in an error message, and the modpack lists
# download URLs. Skip those.
SAFE_CONTENT='mods/mods\.manifest|modrinth-description\.md|check\.sh|deploy\.yml|install-ci-key\.sh'
if git grep -IEn "$SECRET_PATTERN" -- . 2>/dev/null | grep -vE "$SAFE_CONTENT" | head -10 | grep -q .; then
	bad "a tracked file contains something that looks like a credential:"
	git grep -IEn "$SECRET_PATTERN" -- . 2>/dev/null | grep -vE "$SAFE_CONTENT" | head -10 | cut -c1-100 | sed 's/^/       /'
else
	ok "no credential-shaped content in tracked files"
fi

echo "== check: file sizes =="
# 5MB is generous for source; catches stray jars/worlds/backups.
big=$(git ls-files -z | xargs -0 -r du -k 2>/dev/null | awk '$1 > 5120 {print $2}')
if [ -n "$big" ]; then
	bad "tracked file larger than 5MB:"
	echo "$big" | sed 's/^/       /'
else
	ok "no tracked file over 5MB"
fi

echo "== check: website =="
if [ -f website/index.html ]; then
	ok "website/index.html present"
else
	bad "website/index.html is missing"
fi

echo "== check: ignore rules =="
# Representative paths that MUST stay out of the repo. Test the real paths,
# not bare directory names: rules like "logs/" match nested paths, and a bare
# "logs" at the repo root legitimately has no rule.
for p in \
	crafty-panel \
	minecraft-servers \
	discord-bot \
	bot/.env \
	bot/data/state.json \
	bot/logs/run.log \
	servers/d48afa12/world/level.dat \
	crafty/config/default-creds.txt \
	crafty/config/db/crafty.sqlite
do
	if git check-ignore -q --no-index "$p" 2>/dev/null; then
		ok "$p ignored"
	else
		bad "$p is NOT ignored"
	fi
done

# The website source must NOT be ignored.
if git check-ignore -q --no-index website/index.html 2>/dev/null; then
	bad "website/index.html is ignored but should be tracked"
else
	ok "website/index.html tracked"
fi

echo "== check: modpack =="
# The pack index is the source of truth for the mods we run, so it has to
# stay valid and consistent with the environments it is built for.
if [ -f minecraft/modpack/modrinth.index.json ]; then
	if command -v python3 > /dev/null 2>&1; then
		if python3 scripts/modpack.py list > /dev/null 2>&1; then
			ok "modpack index is valid"
		else
			bad "modpack index is not valid - run: python3 scripts/modpack.py list"
		fi
	else
		ok "modpack index present (python3 not available to validate)"
	fi

	# Mod jars must not be committed - they are large binaries that the
	# deploy downloads and verifies by hash.
	if git ls-files | grep -qiE '\.jar$'; then
		bad "a .jar file is tracked - mod jars belong in the pack index, not git:"
		git ls-files | grep -iE '\.jar$' | sed 's/^/       /'
	else
		ok "no .jar files tracked"
	fi
else
	bad "minecraft/modpack/modrinth.index.json is missing"
fi

echo
if [ "$fail" -eq 0 ]; then
	echo "all checks passed"
else
	echo "checks FAILED — fix the above before committing"
fi
exit "$fail"
