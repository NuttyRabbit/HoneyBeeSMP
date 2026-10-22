#!/bin/sh
# luckperms-groups.sh — set up the server's permission groups.
#
# The groups are:
#
#   default   everyone. The claim limits here are the ones Open Parties
#             and Claims uses when a player has no override, and they are
#             set in minecraft/server-config/openpartiesandclaims-server.toml.
#   trusted   players we trust: more land and more chunk loaders.
#   mod       moderators.
#   admin     the owner.
#
# The groups inherit downwards, so "mod" gets everything "trusted" has.
#
# Vanilla commands are a separate matter. Minecraft checks a player's
# *permission level* for the commands they type, not a permission node -
# the "minecraft.command.gamemode" node only matters for command blocks
# and functions. So no amount of LuckPerms will let a non-operator run
# /gamemode; the accounts that need those powers have to be operators.
# That is what "op" is for:
#
#     ./scripts/crafty.sh cmd <server-id> "op <player>"
#
# What LuckPerms is for here is the claim limits, and the Open Parties
# and Claims admin modes - which the operators get anyway, but which
# this makes explicit and which a non-operator moderator could have.
#
# Usage:
#   ./scripts/luckperms-groups.sh <server-id> [owner]
#
# The owner may be given as a name or as a UUID. A UUID is better: it
# works even for a player who has never joined, because LuckPerms looks
# names up through the Mojang API and will not create a record for
# somebody it has never seen. Get the UUID from the server's ops.json.
#
# The owner also needs to be a server operator, for the vanilla commands:
#
#     ./scripts/crafty.sh cmd <server-id> "op <player>"

set -eu

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

SERVER_ID=${1:-}
OWNER=${2:-}

[ -n "$SERVER_ID" ] || {
	echo "usage: $0 <server-id> [owner]" >&2
	exit 2
}

# Send a LuckPerms command to the server's console.
lp() {
	./scripts/crafty.sh cmd "$SERVER_ID" "luckperms $*" > /dev/null
}

# The groups, in the order they should be created.
GROUPS="trusted mod admin"

# --- The groups themselves ---------------------------------------------------
for group in $GROUPS; do
	lp "creategroup $group"
done

# --- What each group inherits ------------------------------------------------
lp "group mod parent add trusted"
lp "group admin parent add mod"

# --- Claim limits ------------------------------------------------------------
# These override the base limits in the Open Parties and Claims config, per
# group. The base is 400 chunks and 8 chunk loaders; "trusted" roughly
# doubles the land and the loaders, which is what a player who has been
# around a while usually wants.
#
# A chunk is 16x16 blocks, so 800 chunks is about 450 blocks square.
lp "group trusted permission set xaero.pac_max_claims 800"
lp "group trusted permission set xaero.pac_max_forceloads 16"
lp "group trusted permission set xaero.pac_max_claiming_anchors 5"
lp "group trusted permission set xaero.pac_claiming_anchor_range 32"
lp "group trusted permission set xaero.pac_max_player_groups 10"
lp "group trusted permission set xaero.pac_player_group_space 128"

# --- Moderator powers --------------------------------------------------------
# The Open Parties and Claims moderator mode: see and moderate other
# people's claims, and teleport to them.
lp "group mod permission set xaero.pac_claims_moderator_mode true"
lp "group mod permission set xaero.pac_claims_teleport true"

# --- Administrator powers ----------------------------------------------------
# Claim admin mode, making claims for other people, and running the party
# and claim commands as somebody else.
lp "group admin permission set xaero.pac_claims_admin_mode true"
lp "group admin permission set xaero.pac_parties_admin_mode true"
lp "group admin permission set xaero.pac_server_claims true"
lp "group admin permission set xaero.pac_claims_impersonation true"
lp "group admin permission set xaero.pac_parties_impersonation true"

# --- The owner ----------------------------------------------------------------
if [ -n "$OWNER" ]; then
	lp "user $OWNER parent add admin"
	echo "put $OWNER in the admin group"
fi

echo "done - the groups are applied. Give it a moment, then check with:"
echo "  ./scripts/crafty.sh cmd $SERVER_ID \"luckperms listgroups\""
echo "  ./scripts/crafty.sh cmd $SERVER_ID \"luckperms group admin info\""
