# Gen Bot (Python / discord.py) — User App

A Discord **User App** (installed to your own account, usable in DMs — not a server bot) for selling/distributing purchased keys (e.g. Steam keys you've bought to resell).

## Commands
- `/addservice name price` — (owner only) add a new product
- `/restock service keys` — (owner only) bulk-add keys, separated by newline or comma
- `/gen service` — redeem one key for a service; it's DMed to whoever runs it
- `/stock` — see live stock counts, with a **Claim** button per service
- `/setdailytime hours` — (owner only) set how often the periodic stock DM is sent **and** the claim cooldown. e.g. `1` = hourly DM + 1 claim per person per service per hour; `24` = daily DM + 1 claim per day. Defaults to 24.
- Periodic DM — the bot DMs the owner a stock report with claim buttons at the interval set by `/setdailytime`

### How claiming works
Each stock report DM includes a button per service. Whoever clicks it gets a key DMed to them, and is then blocked from claiming that *same service* again until the interval set by `/setdailytime` has passed (tracked per user, per service, in `store.db`). Different services have independent cooldowns.

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Create your Discord Application**
   - Go to https://discord.com/developers/applications → New Application
   - Under **Bot**, create a bot and copy the token
   - Under **Installation**:
     - Set **Install Contexts** to include **User Install**
     - Copy the install link (includes `integration_type=1`) and use it to install the app to your own account
   - Copy the **Application ID**

3. **Fill in `.env`** (copy `.env.example` → `.env`)
   ```
   DISCORD_TOKEN=...
   OWNER_ID=your_own_discord_user_id   (enable Developer Mode, right-click your name, Copy User ID)
   ```

4. **Run the bot**
   ```
   python bot.py
   ```
   Commands sync automatically on startup (`bot.tree.sync()` in `on_ready`). The first global sync can take up to an hour to show up everywhere; it's instant if you restrict it to a test guild during development.

   On Railway: set the same environment variables in the project's Variables tab, set the start command to `python bot.py`, and make sure `store.db` is on a persistent volume so stock isn't wiped on redeploy.

## Notes
- The owner-only check compares `interaction.user.id` to `OWNER_ID` — only you can `/addservice` and `/restock`.
- `/gen` works for anyone who runs it (useful if customers redeem after paying you manually). If you'd rather only trigger deliveries yourself (you run `/gen` and it DMs a specific customer), say so and I'll add a `user` option instead of DMing the command-runner.
- `integration_types`/`contexts` on each command are what make this a **User App** usable in DMs without being in a server together.
