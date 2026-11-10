import os
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import db

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

intents = discord.Intents.default()
# No privileged intents needed for slash commands + DMs

bot = commands.Bot(command_prefix="!", intents=intents)


def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID


def get_interval_hours() -> float:
    return float(db.get_setting("interval_hours", "24"))


def format_remaining(seconds: float) -> str:
    seconds = int(seconds)
    hrs, rem = divmod(seconds, 3600)
    mins, _ = divmod(rem, 60)
    if hrs:
        return f"{hrs}h {mins}m"
    return f"{mins}m"


class ClaimView(discord.ui.View):
    """Persistent view: one button per service, custom_id encodes the service id
    so it keeps working across restarts without needing to resend the message."""

    def __init__(self, services):
        super().__init__(timeout=None)
        for svc in services:
            self.add_item(ClaimButton(svc["id"], svc["name"]))


class ClaimButton(discord.ui.Button):
    def __init__(self, service_id: int, service_name: str):
        super().__init__(
            label=f"Claim: {service_name}",
            style=discord.ButtonStyle.primary,
            custom_id=f"claim:{service_id}",
        )
        self.service_id = service_id
        self.service_name = service_name

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        interval_hours = get_interval_hours()

        last_claim = db.get_last_claim(user_id, self.service_id)
        if last_claim:
            elapsed = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(last_claim)).total_seconds()
            wait = interval_hours * 3600 - elapsed
            if wait > 0:
                return await interaction.response.send_message(
                    f"You already claimed **{self.service_name}** recently. "
                    f"Try again in {format_remaining(wait)}.",
                    ephemeral=True,
                )

        key = db.get_available_key(self.service_id)
        if not key:
            return await interaction.response.send_message(
                f'No stock left for "{self.service_name}".', ephemeral=True
            )

        now = datetime.datetime.utcnow().isoformat()
        db.mark_redeemed(key["id"], user_id, now)

        try:
            await interaction.user.send(f"Here's your key for **{self.service_name}**:\n`{key['code']}`")
        except discord.Forbidden:
            db.rollback_redeem(key["id"])
            return await interaction.response.send_message(
                "Couldn't DM you — check your privacy settings and try again.", ephemeral=True
            )

        db.set_last_claim(user_id, self.service_id, now)
        await interaction.response.send_message("Sent to your DMs!", ephemeral=True)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    # Register commands as installable to a user account (not just servers)
    # This is done once via sync; integration_types/contexts are set per-command below.
    await bot.tree.sync()

    # Re-register a persistent view so existing claim buttons in old messages keep working
    bot.add_view(ClaimView(db.list_services()))

    restart_stock_dm_loop()
    print("Commands synced.")


def restart_stock_dm_loop():
    """(Re)starts the periodic DM loop at the interval stored in settings."""
    if periodic_stock_dm.is_running():
        periodic_stock_dm.cancel()
    periodic_stock_dm.change_interval(hours=get_interval_hours())
    periodic_stock_dm.start()


@tasks.loop(hours=24)  # actual interval is set at runtime via restart_stock_dm_loop()
async def periodic_stock_dm():
    try:
        owner = await bot.fetch_user(OWNER_ID)
        services = db.list_services()
        view = ClaimView(services) if services else None
        await owner.send(f"**Stock report:**\n{db.stock_summary()}", view=view)
    except Exception as e:
        print(f"Failed to send periodic stock DM: {e}")


# --- Commands ---
# integration_types={app_commands.AppIntegrationType.user_install} makes this
# usable as a User App (installed to your account, usable in DMs anywhere).
# Add guild_install too if you also want it addable to servers.

USER_APP = {
    "integration_types": {app_commands.AppIntegrationType.user_install},
    "contexts": {
        app_commands.AppCommandContext.guild,
        app_commands.AppCommandContext.bot_dm,
        app_commands.AppCommandContext.private_channel,
    },
}


@bot.tree.command(name="addservice", description="Add a new service/product (owner only)", **USER_APP)
@app_commands.describe(name="Service name, e.g. Elden Ring", price="Price (optional, for your reference)")
async def addservice(interaction: discord.Interaction, name: str, price: str = None):
    if not is_owner(interaction):
        return await interaction.response.send_message("Not authorized.", ephemeral=True)

    try:
        db.add_service(name, price, str(interaction.user.id))
        await interaction.response.send_message(f'Service "{name}" added.', ephemeral=True)
    except Exception as e:
        if "UNIQUE" in str(e):
            await interaction.response.send_message(f'Service "{name}" already exists.', ephemeral=True)
        else:
            print(e)
            await interaction.response.send_message("Error adding service.", ephemeral=True)


@bot.tree.command(name="restock", description="Add keys to a service (owner only)", **USER_APP)
@app_commands.describe(service="Exact service name", keys="Keys separated by newline or comma")
async def restock(interaction: discord.Interaction, service: str, keys: str):
    if not is_owner(interaction):
        return await interaction.response.send_message("Not authorized.", ephemeral=True)

    svc = db.get_service(service)
    if not svc:
        return await interaction.response.send_message(
            f'Service "{service}" not found. Use /addservice first.', ephemeral=True
        )

    codes = [c.strip() for c in keys.replace(",", "\n").split("\n") if c.strip()]
    db.add_keys(svc["id"], codes)
    await interaction.response.send_message(f'Added {len(codes)} key(s) to "{service}".', ephemeral=True)


@bot.tree.command(name="gen", description="Redeem a key for a service", **USER_APP)
@app_commands.describe(service="Exact service name")
async def gen(interaction: discord.Interaction, service: str):
    svc = db.get_service(service)
    if not svc:
        return await interaction.response.send_message(f'Service "{service}" not found.', ephemeral=True)

    key = db.get_available_key(svc["id"])
    if not key:
        return await interaction.response.send_message(f'No stock left for "{service}".', ephemeral=True)

    db.mark_redeemed(key["id"], str(interaction.user.id), datetime.datetime.utcnow().isoformat())

    try:
        await interaction.user.send(f"Here's your key for **{service}**:\n`{key['code']}`")
        await interaction.response.send_message("Sent to your DMs!", ephemeral=True)
    except discord.Forbidden:
        db.rollback_redeem(key["id"])
        await interaction.response.send_message(
            "Couldn't DM you — check your privacy settings and try again.", ephemeral=True
        )


@bot.tree.command(name="stock", description="Check current stock levels", **USER_APP)
async def stock(interaction: discord.Interaction):
    services = db.list_services()
    view = ClaimView(services) if services else None
    await interaction.response.send_message(db.stock_summary(), view=view, ephemeral=True)


@bot.tree.command(
    name="setdailytime",
    description="Set how often the stock DM goes out, and the claim cooldown (owner only)",
    **USER_APP,
)
@app_commands.describe(hours="Interval in hours, e.g. 1 for hourly, 24 for daily")
async def setdailytime(interaction: discord.Interaction, hours: float):
    if not is_owner(interaction):
        return await interaction.response.send_message("Not authorized.", ephemeral=True)
    if hours <= 0:
        return await interaction.response.send_message("Hours must be greater than 0.", ephemeral=True)

    db.set_setting("interval_hours", str(hours))
    restart_stock_dm_loop()
    await interaction.response.send_message(
        f"Stock DM interval and claim cooldown set to {hours} hour(s).", ephemeral=True
    )


bot.run(TOKEN)
