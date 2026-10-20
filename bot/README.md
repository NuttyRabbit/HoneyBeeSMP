# HoneyBeeSMP Discord Bot

Reserved workspace for the HoneyBeeSMP Discord bot.

## Layout
- `src/`   - bot source code
- `data/`  - persistent data (databases, caches) - gitignored
- `logs/`  - log output - gitignored
- `.env`   - secrets (copy from `.env.example`) - gitignored

## Planned integration
- Crafty Controller API: https://panel.honeybeesmp.co.uk
  (Panel -> Settings/API to generate a token)
- Discord developer portal: https://discord.com/developers/applications

## Next steps (when ready)
1. `cp .env.example .env` and fill in the token.
2. Choose a stack (Node.js via discord.js, or Python via discord.py).
3. Add a systemd unit so the bot runs on boot.
