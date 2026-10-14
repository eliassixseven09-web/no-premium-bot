import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO

# ==================== CONFIG ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- Token loading: VS launchSettings.json + .env fallback ----------
LAUNCH_SETTINGS_FILE = os.path.join(BASE_DIR, "Properties", "launchSettings.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")


def _ingest_env_pair(name: str, value: str) -> None:
    if name.strip() in {"DISCORD_TOKEN", "DISCORD_BOT_TOKEN"} and value:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


if os.path.isfile(LAUNCH_SETTINGS_FILE):
    try:
        with open(LAUNCH_SETTINGS_FILE, encoding="utf-8") as ls_file:
            launch_data = json.load(ls_file)
        for profile in launch_data.get("profiles", {}).values():
            for name, value in profile.get("environmentVariables", {}).items():
                if isinstance(value, str):
                    _ingest_env_pair(name, value)
    except (json.JSONDecodeError, OSError) as error:
        print(f"[!] Could not read launchSettings.json: {error}")

if os.path.isfile(ENV_FILE):
    with open(ENV_FILE, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            name, separator, value = line.partition("=")
            if separator:
                _ingest_env_pair(name, value)

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")

# ---------- Role IDs ----------
REQUIRED_ROLES_FOR_PANEL = [
    1535650014565507225,
    1535650014565507225,
    1535650018621394944,
]
RESTOCK_ROLE_ID = 1535650003975147540
DM_ROLE_ID = 1555668778635886685
MODERATION_ROLE_ID = 1555668778635886685

TICKET_SETUP_ROLE_ID = 1555668778635886685
TICKET_STAFF_ROLE_ID = 1535650011151601724
TICKET_CATEGORY_ID = 1535650054910775307

KEY_DROP_CHANNEL_ID = 1535650094442090557

DEFAULT_DM_AMOUNT = 1
DEFAULT_DM_REASON = "Invalid reason"
MAX_TXT_FILE_SIZE = 5 * 1024 * 1024

KEYS_FILE = os.path.join(BASE_DIR, "keys.json")
USED_FILE = os.path.join(BASE_DIR, "used_keys.json")
TICKETS_FILE = os.path.join(BASE_DIR, "tickets.json")
FEEDBACK_FILE = os.path.join(BASE_DIR, "ticket_feedback.json")
WARNINGS_FILE = os.path.join(BASE_DIR, "warnings.json")
WALLAHIS_FILE = os.path.join(BASE_DIR, "wallahis.json")
INVINC_FILE = os.path.join(BASE_DIR, "invinc.json")
CREDITS_FILE = os.path.join(BASE_DIR, "credits.json")
MESSAGE_COUNTS_FILE = os.path.join(BASE_DIR, "message_counts.json")

MESSAGES_PER_CREDIT = 150
PREMIUM_ROLE_ID = 1535650014565507225
JEW_MODE_ROLE_ID = 1558065787351204033

COMMAND_PREFIXES = ["!", "a!"]

_WALLAHI_PATTERN = re.compile(r"(?<!\w)wallahi(?!\w)", re.IGNORECASE)
_MODERATION_COMMAND_NAMES = {
    "warn", "mute", "unmute", "kick", "ban", "wallahis", "invinc",
    "jew", "credits", "gcredits", "removew", "removec",
}
# ================================================


def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=2)
        return default
    with open(path, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_available_keys():
    return load_json(KEYS_FILE, [])


def save_available_keys(keys):
    save_json(KEYS_FILE, keys)


def get_used_keys():
    return load_json(USED_FILE, [])


def mark_key_used(key, user_id):
    used = get_used_keys()
    used.append({"key": key, "user_id": user_id})
    save_json(USED_FILE, used)


def get_tickets():
    return load_json(TICKETS_FILE, {})


def save_tickets(data):
    save_json(TICKETS_FILE, data)


def get_feedback():
    return load_json(FEEDBACK_FILE, [])


def save_feedback(data):
    save_json(FEEDBACK_FILE, data)


def parse_keys_from_text(text: str):
    return [k.strip() for k in text.split() if k.strip()]


def has_role(member: discord.Member, role_id: int) -> bool:
    return any(r.id == role_id for r in member.roles)


def has_any_role(member: discord.Member, role_ids):
    member_role_ids = {role.id for role in member.roles}
    return any(rid in member_role_ids for rid in role_ids)


def _load_user_state(path: str, guild_id: int) -> dict:
    state = load_json(path, {})
    if not isinstance(state, dict):
        state = {}
    guild_state = state.setdefault(str(guild_id), {})
    if not isinstance(guild_state, dict):
        guild_state = {}
        state[str(guild_id)] = guild_state
    return state


def _get_wallahi_count(guild_id: int, user_id: int) -> int:
    state = _load_user_state(WALLAHIS_FILE, guild_id)
    value = state[str(guild_id)].get(str(user_id), 0)
    return value if isinstance(value, int) and value > 0 else 0


def _set_wallahi_count(guild_id: int, user_id: int, amount: int) -> None:
    state = _load_user_state(WALLAHIS_FILE, guild_id)
    guild_state = state[str(guild_id)]
    if amount > 0:
        guild_state[str(user_id)] = amount
    else:
        guild_state.pop(str(user_id), None)
    save_json(WALLAHIS_FILE, state)


def _add_wallahi_credits(guild_id: int, user_id: int, amount: int) -> int:
    state = _load_user_state(WALLAHIS_FILE, guild_id)
    guild_state = state[str(guild_id)]
    current = guild_state.get(str(user_id), 0)
    if not isinstance(current, int) or current < 0:
        current = 0
    new_balance = max(0, current + amount)
    if new_balance > 0:
        guild_state[str(user_id)] = new_balance
    else:
        guild_state.pop(str(user_id), None)
    save_json(WALLAHIS_FILE, state)
    return new_balance


def _get_credit_balance(guild_id: int, user_id: int) -> int:
    state = _load_user_state(CREDITS_FILE, guild_id)
    value = state[str(guild_id)].get(str(user_id), 0)
    return value if isinstance(value, int) and value > 0 else 0


def _set_credit_balance(guild_id: int, user_id: int, amount: int) -> None:
    state = _load_user_state(CREDITS_FILE, guild_id)
    guild_state = state[str(guild_id)]
    if amount > 0:
        guild_state[str(user_id)] = amount
    else:
        guild_state.pop(str(user_id), None)
    save_json(CREDITS_FILE, state)


def _add_credit_balance(guild_id: int, user_id: int, amount: int) -> int:
    state = _load_user_state(CREDITS_FILE, guild_id)
    guild_state = state[str(guild_id)]
    current = guild_state.get(str(user_id), 0)
    if not isinstance(current, int) or current < 0:
        current = 0
    new_balance = max(0, current + amount)
    if new_balance > 0:
        guild_state[str(user_id)] = new_balance
    else:
        guild_state.pop(str(user_id), None)
    save_json(CREDITS_FILE, state)
    return new_balance


def _has_active_invinc(guild_id: int, user_id: int) -> bool:
    state = _load_user_state(INVINC_FILE, guild_id)
    guild_state = state[str(guild_id)]
    expiry_value = guild_state.get(str(user_id))
    if not isinstance(expiry_value, str):
        return False
    try:
        expiry = datetime.fromisoformat(expiry_value)
    except ValueError:
        guild_state.pop(str(user_id), None)
        save_json(INVINC_FILE, state)
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry > datetime.now(timezone.utc):
        return True
    guild_state.pop(str(user_id), None)
    save_json(INVINC_FILE, state)
    return False


def _has_jew_mode(member: discord.abc.User) -> bool:
    return isinstance(member, discord.Member) and has_role(member, JEW_MODE_ROLE_ID)


def _has_moderation_role(member: discord.abc.User) -> bool:
    return isinstance(member, discord.Member) and has_role(member, MODERATION_ROLE_ID)


def _moderation_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


async def _check_moderator(ctx: commands.Context) -> bool:
    if _has_moderation_role(ctx.author):
        return True
    await ctx.reply(embed=_moderation_embed(
        "Permission Denied",
        "You need the authorized moderator role to use this command.",
        discord.Color.red(),
    ))
    return False


# ========================================================
# ==================== BOT ================================
# ========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class PremiumBot(commands.Bot):
    async def setup_hook(self):
        try:
            self.add_view(PremiumView())
            self.add_view(TicketOpenView())
            self.add_view(TicketControlView())
        except NameError as error:
            print(f"[!] Persistent view registration failed: {error}")
        try:
            synced = await self.tree.sync()
        except discord.HTTPException as error:
            print(f"[!] Slash-command sync failed: {error}")
        else:
            print(f"[+] Synced {len(synced)} slash commands")


bot = PremiumBot(command_prefix=COMMAND_PREFIXES, intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"[+] Logged in as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    if not message.guild and not isinstance(message.channel, discord.DMChannel):
        return

    if isinstance(message.channel, discord.DMChannel):
        if message.author.bot:
            return
        pending = load_json(FEEDBACK_FILE, {})
        if isinstance(pending, dict) and "pending" in pending:
            if pending["pending"].get(str(message.author.id)):
                entry = pending["pending"][str(message.author.id)]
                feedback_log = pending.setdefault("log", [])
                feedback_log.append({
                    "user_id": message.author.id,
                    "ticket_id": entry.get("ticket_id"),
                    "rating": message.content.strip(),
                })
                del pending["pending"][str(message.author.id)]
                save_json(FEEDBACK_FILE, pending)
                await message.channel.send(
                    "✅ Thanks for your feedback! Your response has been recorded."
                )
        return

    if message.author.bot:
        return

    await _track_message_for_credits(message)

    if message.content.startswith(tuple(COMMAND_PREFIXES)):
        await bot.process_commands(message)
        return

    if _WALLAHI_PATTERN.search(message.content):
        await _handle_wallahi_message(message)
        return

    if message.channel.id != KEY_DROP_CHANNEL_ID:
        await bot.process_commands(message)
        return

    collected_keys = []

    if message.content and message.content.strip():
        collected_keys.extend(parse_keys_from_text(message.content))

    file_keys_count = 0
    for attachment in message.attachments:
        if not attachment.filename.lower().endswith(".txt"):
            continue
        if attachment.size > MAX_TXT_FILE_SIZE:
            await message.reply(
                f"❌ `{attachment.filename}` exceeds the {MAX_TXT_FILE_SIZE // (1024 * 1024)} MB limit. "
                "The original message and file were kept."
            )
            continue
        try:
            raw_bytes = await attachment.read()
        except discord.HTTPException as error:
            await message.reply(f"❌ Couldn't read `{attachment.filename}`: {error}")
            continue
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            await message.reply(
                f"❌ `{attachment.filename}` isn't valid UTF-8 text and was not imported."
            )
            continue
        file_keys = parse_keys_from_text(text)
        collected_keys.extend(file_keys)
        file_keys_count += len(file_keys)

    if not collected_keys:
        await bot.process_commands(message)
        return

    keys = get_available_keys()
    keys.extend(collected_keys)
    save_available_keys(keys)

    embed = discord.Embed(
        title="📥 Keys Detected",
        description=f"Found **{len(collected_keys)}** key(s) and added them to the stock.",
        color=discord.Color.blurple(),
    )
    if file_keys_count > 0:
        embed.add_field(
            name="From File(s)",
            value=f"`{file_keys_count}` key(s) read from attached .txt file(s)",
            inline=False,
        )
    embed.add_field(name="Total Stock", value=str(len(keys)), inline=False)
    embed.set_footer(text=f"Added by {message.author} • Original message and file kept")

    try:
        await message.channel.send(embed=embed)
    except discord.HTTPException:
        pass

    await bot.process_commands(message)


# ========================================================
# ============== PREMIUM PANEL ===========================
# ========================================================

async def panel_logic(target):
    embed = discord.Embed(
        title="✨ Premium Panel ✨",
        description=(
            "Click the button below to claim your **Premium Key**.\n\n"
            "> 🎁 Each key can be used **once**.\n"
            "> 🔒 You must have the required role to claim a key.\n"
            "> ⏳ Keys are limited — restocked regularly."
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Premium System")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    view = PremiumView()

    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed, view=view)
    else:
        await target.send(embed=embed, view=view)


class PremiumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Get Premium Key",
        style=discord.ButtonStyle.success,
        emoji="🔑",
        custom_id="premium_get_key",
    )
    async def get_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user

        if not has_any_role(member, REQUIRED_ROLES_FOR_PANEL):
            await interaction.response.send_message(
                "❌ You don't have the required role to claim a premium key.",
                ephemeral=True,
            )
            return

        used = get_used_keys()
        if any(entry["user_id"] == member.id for entry in used):
            await interaction.response.send_message(
                "⚠️ You have already claimed a premium key.",
                ephemeral=True,
            )
            return

        keys = get_available_keys()
        if not keys:
            await interaction.response.send_message(
                "📦 **Out of stock!** No premium keys are available right now.",
                ephemeral=True,
            )
            return

        key = keys.pop(0)
        save_available_keys(keys)
        mark_key_used(key, member.id)

        try:
            dm_embed = discord.Embed(
                title="🔑 Your Premium Key",
                description=f"```{key}```\n\nKeep this key safe. It can only be used once.",
                color=discord.Color.green(),
            )
            await member.send(embed=dm_embed)
            await interaction.response.send_message(
                "✅ Your premium key has been sent to your DMs!", ephemeral=True
            )
        except discord.Forbidden:
            keys.insert(0, key)
            save_available_keys(keys)
            used = [e for e in get_used_keys() if not (e["user_id"] == member.id and e["key"] == key)]
            save_json(USED_FILE, used)
            await interaction.response.send_message(
                "❌ I couldn't DM you. Please enable **Direct Messages** from server members.",
                ephemeral=True,
            )


# ========================================================
# ==================== TICKET SYSTEM =====================
# ========================================================

def _ticket_key(channel_id: int) -> str:
    return str(channel_id)


def _is_ticket_staff(member: discord.Member) -> bool:
    return has_role(member, TICKET_STAFF_ROLE_ID)


def _build_ticket_embed(data: dict) -> discord.Embed:
    opener_id = data.get("opener_id")
    claimed_by = data.get("claimed_by")
    added = data.get("added_users", [])

    embed = discord.Embed(
        title="🎫 Support Ticket",
        description=(
            f"Welcome <@{opener_id}>!\n"
            "Please describe your issue below.\n\n"
            "**Staff will assist you shortly.**"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Opened by", value=f"<@{opener_id}>", inline=True)
    embed.add_field(
        name="Claimed by",
        value=f"<@{claimed_by}>" if claimed_by else "`Unclaimed`",
        inline=True,
    )
    if added:
        embed.add_field(
            name="Added users",
            value=" ".join(f"<@{uid}>" for uid in added),
            inline=False,
        )
    embed.set_footer(text="Use the buttons below to manage this ticket.")
    return embed


async def _apply_claim_permissions(channel: discord.TextChannel, data: dict):
    guild = channel.guild
    staff_role = guild.get_role(TICKET_STAFF_ROLE_ID)
    opener_id = data.get("opener_id")
    claimed_by = data.get("claimed_by")
    added = data.get("added_users", [])

    if staff_role:
        await channel.set_permissions(
            staff_role,
            view_channel=True,
            send_messages=not bool(claimed_by),
            read_message_history=True,
        )

    if opener_id:
        opener = guild.get_member(opener_id)
        if opener:
            await channel.set_permissions(
                opener,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

    for uid in added:
        u = guild.get_member(uid)
        if u:
            await channel.set_permissions(
                u,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

    if claimed_by:
        claimer = guild.get_member(claimed_by)
        if claimer:
            await channel.set_permissions(
                claimer,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        if staff_role:
            for m in staff_role.members:
                if m.id in {claimed_by, opener_id} or m.id in added:
                    continue
                if m.status == discord.Status.offline:
                    continue
                try:
                    await channel.set_permissions(
                        m,
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True,
                    )
                except discord.HTTPException:
                    continue
    else:
        if staff_role:
            for m in staff_role.members:
                if m.id == opener_id or m.id in added:
                    continue
                try:
                    await channel.set_permissions(m, overwrite=None)
                except discord.HTTPException:
                    continue


async def ticket_setup_logic(target):
    member = target.author if isinstance(target, commands.Context) else target.user

    if not isinstance(member, discord.Member) or not has_role(member, TICKET_SETUP_ROLE_ID):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You don't have permission to setup the ticket panel.",
            color=discord.Color.red(),
        )
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return

    embed = discord.Embed(
        title="🎫 Support Tickets",
        description=(
            "Need help? Click the button below to open a private ticket.\n\n"
            "> 📩 A private channel will be created for you.\n"
            "> 🤝 Staff will assist you as soon as possible.\n"
            "> 🔒 Only you and staff can see it."
        ),
        color=discord.Color.dark_teal(),
    )
    embed.set_footer(text="Click the button to open a ticket")

    view = TicketOpenView()

    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed, view=view)
    else:
        await target.send(embed=embed, view=view)


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="ticket_open",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        if guild is None:
            await interaction.response.send_message(
                "❌ Tickets can only be opened in a server.", ephemeral=True
            )
            return

        tickets = get_tickets()

        for ch_id, data in tickets.items():
            if data.get("opener_id") == member.id and data.get("status") == "open":
                await interaction.response.send_message(
                    f"⚠️ You already have an open ticket: <#{ch_id}>", ephemeral=True
                )
                return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }

        staff_role = guild.get_role(TICKET_STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{member.name}".lower()[:90],
                overwrites=overwrites,
                category=category,
                topic=f"Ticket opened by {member} ({member.id})",
                reason=f"Ticket opened by {member}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to create channels.", ephemeral=True
            )
            return

        tickets[_ticket_key(channel.id)] = {
            "opener_id": member.id,
            "claimed_by": None,
            "added_users": [],
            "status": "open",
        }
        save_tickets(tickets)

        embed = _build_ticket_embed(tickets[_ticket_key(channel.id)])
        view = TicketControlView()

        try:
            await channel.send(
                content=f"{member.mention} {staff_role.mention if staff_role else ''}",
                embed=embed,
                view=view,
            )
        except discord.HTTPException:
            await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}", ephemeral=True
        )


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _refresh(self, interaction: discord.Interaction):
        tickets = get_tickets()
        data = tickets.get(_ticket_key(interaction.channel.id))
        if not data:
            return None
        embed = _build_ticket_embed(data)
        try:
            await interaction.message.edit(embed=embed, view=self)
        except (discord.HTTPException, AttributeError):
            pass
        return data

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not _is_ticket_staff(member):
            await interaction.response.send_message("❌ You don't have permission to claim tickets.", ephemeral=True)
            return
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return
        if data.get("claimed_by"):
            await interaction.response.send_message(f"⚠️ Already claimed by <@{data['claimed_by']}>.", ephemeral=True)
            return
        data["claimed_by"] = member.id
        tickets[key] = data
        save_tickets(tickets)
        await _apply_claim_permissions(interaction.channel, data)
        await interaction.response.send_message(
            f"✅ {member.mention} has claimed this ticket. Only <@{data['opener_id']}> and {member.mention} can chat now.",
            ephemeral=False,
        )
        await self._refresh(interaction)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, emoji="↩️", custom_id="ticket_unclaim")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not _is_ticket_staff(member):
            await interaction.response.send_message("❌ You don't have permission to unclaim tickets.", ephemeral=True)
            return
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return
        if not data.get("claimed_by"):
            await interaction.response.send_message("⚠️ This ticket is not claimed.", ephemeral=True)
            return
        if data["claimed_by"] != member.id:
            await interaction.response.send_message("❌ Only the claimer can unclaim this ticket.", ephemeral=True)
            return
        data["claimed_by"] = None
        tickets[key] = data
        save_tickets(tickets)
        await _apply_claim_permissions(interaction.channel, data)
        await interaction.response.send_message(
            f"↩️ {member.mention} has unclaimed this ticket. All staff can chat again.",
            ephemeral=False,
        )
        await self._refresh(interaction)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.primary, emoji="➕", custom_id="ticket_add")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return
        is_staff = isinstance(member, discord.Member) and _is_ticket_staff(member)
        is_opener = member.id == data["opener_id"]
        is_claimer = member.id == data.get("claimed_by")
        if data.get("claimed_by") and not (is_claimer or is_opener):
            await interaction.response.send_message(
                "❌ Only the claimer or opener can add users to a claimed ticket.",
                ephemeral=True,
            )
            return
        if not (is_staff or is_opener or is_claimer):
            await interaction.response.send_message("❌ You can't add users to this ticket.", ephemeral=True)
            return
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.primary, emoji="➖", custom_id="ticket_remove")
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not _is_ticket_staff(member):
            await interaction.response.send_message("❌ Only staff can remove users from tickets.", ephemeral=True)
            return
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return
        await interaction.response.send_modal(RemoveUserModal())

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return
        is_staff = isinstance(member, discord.Member) and _is_ticket_staff(member)
        is_opener = member.id == data["opener_id"]
        is_claimer = member.id == data.get("claimed_by")
        if not (is_staff or is_opener or is_claimer):
            await interaction.response.send_message("❌ You can't close this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds…", ephemeral=False)
        opener_id = data["opener_id"]
        channel = interaction.channel

        async def _finalize():
            await asyncio.sleep(5)
            tks = get_tickets()
            tks.pop(key, None)
            save_tickets(tks)
            pending = load_json(FEEDBACK_FILE, {})
            if not isinstance(pending, dict):
                pending = {}
            pending.setdefault("pending", {})
            pending.setdefault("log", [])
            pending["pending"][str(opener_id)] = {"ticket_id": key}
            save_json(FEEDBACK_FILE, pending)
            try:
                opener = await bot.fetch_user(opener_id)
                fb_embed = discord.Embed(
                    title="📝 Ticket Feedback",
                    description=(
                        "Your ticket has been closed.\n\n"
                        "Please reply to this DM with a short message about how your ticket went "
                        "(e.g., a rating from 1-5 or any comments)."
                    ),
                    color=discord.Color.gold(),
                )
                await opener.send(embed=fb_embed)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            try:
                await channel.delete(reason="Ticket closed")
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        asyncio.create_task(_finalize())


class AddUserModal(discord.ui.Modal, title="Add User to Ticket"):
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Paste the user's ID",
        required=True,
        max_length=25,
    )

    async def on_submit(self, interaction: discord.Interaction):
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return

        member = interaction.user
        is_opener = member.id == data.get("opener_id")
        is_claimer = member.id == data.get("claimed_by")
        if data.get("claimed_by") and not (is_claimer or is_opener):
            await interaction.response.send_message(
                "❌ Only the claimer or opener can add users to a claimed ticket.",
                ephemeral=True,
            )
            return

        try:
            user_id = int(str(self.user_id.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
            return

        guild = interaction.guild
        target = guild.get_member(user_id)
        if target is None:
            try:
                target = await bot.fetch_user(user_id)
            except (discord.NotFound, discord.HTTPException):
                await interaction.response.send_message("❌ User not found.", ephemeral=True)
                return

        try:
            await interaction.channel.set_permissions(
                target,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to modify this channel.",
                ephemeral=True,
            )
            return

        added = data.get("added_users", [])
        if user_id not in added:
            added.append(user_id)
        data["added_users"] = added
        tickets[key] = data
        save_tickets(tickets)

        await interaction.response.send_message(
            f"✅ Added <@{user_id}> to this ticket.",
            ephemeral=False,
        )

        try:
            async for msg in interaction.channel.history(limit=20):
                if msg.author == bot.user and msg.embeds and msg.components:
                    embed = _build_ticket_embed(data)
                    await msg.edit(embed=embed, view=TicketControlView())
                    break
        except discord.HTTPException:
            pass


class RemoveUserModal(discord.ui.Modal, title="Remove User from Ticket"):
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Paste the user's ID",
        required=True,
        max_length=25,
    )

    async def on_submit(self, interaction: discord.Interaction):
        tickets = get_tickets()
        key = _ticket_key(interaction.channel.id)
        data = tickets.get(key)
        if not data:
            await interaction.response.send_message("❌ This channel isn't a ticket.", ephemeral=True)
            return

        try:
            user_id = int(str(self.user_id.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
            return

        added = data.get("added_users", [])
        if user_id not in added:
            await interaction.response.send_message("⚠️ That user isn't in this ticket.", ephemeral=True)
            return

        added.remove(user_id)
        data["added_users"] = added
        tickets[key] = data
        save_tickets(tickets)

        guild = interaction.guild
        target = guild.get_member(user_id)
        if target is None:
            try:
                target = await bot.fetch_user(user_id)
            except (discord.NotFound, discord.HTTPException):
                target = None

        if target is not None:
            try:
                await interaction.channel.set_permissions(target, overwrite=None)
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            f"✅ Removed <@{user_id}> from this ticket.",
            ephemeral=False,
        )

        try:
            async for msg in interaction.channel.history(limit=20):
                if msg.author == bot.user and msg.embeds and msg.components:
                    embed = _build_ticket_embed(data)
                    await msg.edit(embed=embed, view=TicketControlView())
                    break
        except discord.HTTPException:
            pass


# ========================================================
# ==================== SHARED LOGIC ======================
# ========================================================

async def restock_logic(target, key_string):
    member = target.author if isinstance(target, commands.Context) else target.user
    if not isinstance(member, discord.Member) or RESTOCK_ROLE_ID not in {r.id for r in member.roles}:
        embed = discord.Embed(title="❌ Permission Denied", description="You don't have permission to use this command.", color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    new_keys = [k.strip() for k in key_string.split(",") if k.strip()]
    if not new_keys:
        embed = discord.Embed(title="❌ Invalid Input", description="Please provide at least one valid key.", color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    keys = get_available_keys()
    keys.extend(new_keys)
    save_available_keys(keys)
    embed = discord.Embed(title="✅ Keys Restocked", description=f"Added **{len(new_keys)}** key(s) to the stock.", color=discord.Color.green())
    embed.add_field(name="Total Stock", value=str(len(keys)), inline=False)
    embed.add_field(name="Keys Added", value=str(len(new_keys)), inline=False)
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed)
    else:
        await target.reply(embed=embed)


async def dm_logic(target, user: discord.Member, amount: int = None, reason: str = None):
    member = target.author if isinstance(target, commands.Context) else target.user
    if amount is None:
        amount = DEFAULT_DM_AMOUNT
    if not reason or not reason.strip():
        reason = DEFAULT_DM_REASON
    if not isinstance(member, discord.Member) or DM_ROLE_ID not in {r.id for r in member.roles}:
        embed = discord.Embed(title="❌ Permission Denied", description="You don't have permission to use this command.", color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    if amount < 1:
        embed = discord.Embed(title="❌ Invalid Amount", description="Amount must be at least **1**.", color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    if user.bot:
        embed = discord.Embed(title="❌ Invalid User", description="You can't send keys to a bot.", color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    keys = get_available_keys()
    if len(keys) < amount:
        embed = discord.Embed(title="❌ Not Enough Stock", description=(f"Not enough keys in the premium panel stock.\n" f"Requested **{amount}**, available **{len(keys)}**."), color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    sent_keys = keys[:amount]
    remaining = keys[amount:]
    save_available_keys(remaining)
    dm_embed = discord.Embed(title="🔑 Premium Keys", description=(f"You have received **{amount}** premium key(s) from the premium panel stock.\n" "Keep the attached file safe — each key can only be used **once**."), color=discord.Color.green())
    dm_embed.add_field(name="Reason", value=reason[:1024], inline=False)
    dm_embed.set_footer(text=f"Sent by {member}")
    key_file = discord.File(BytesIO("\n".join(sent_keys).encode("utf-8")), filename="premium_keys.txt")
    try:
        await user.send(embed=dm_embed, file=key_file)
    except discord.HTTPException:
        current = get_available_keys()
        save_available_keys(sent_keys + current)
        embed = discord.Embed(title="❌ DM Failed", description=(f"Couldn't DM {user.mention}. They may have DMs disabled.\n" f"Keys have been returned to the panel stock."), color=discord.Color.red())
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=embed, ephemeral=True)
        else:
            await target.reply(embed=embed)
        return
    used = get_used_keys()
    used.extend({"key": key, "user_id": user.id} for key in sent_keys)
    save_json(USED_FILE, used)
    confirm = discord.Embed(title="✅ Keys Sent", description=(f"Successfully DMed **{amount}** key(s) to {user.mention} " f"from the premium panel stock."), color=discord.Color.green())
    confirm.add_field(name="Remaining Panel Stock", value=str(len(get_available_keys())), inline=False)
    confirm.add_field(name="Reason", value=reason[:1024], inline=False)
    confirm.add_field(name="Sent By", value=member.mention, inline=False)
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=confirm, ephemeral=True)
    else:
        await target.reply(embed=confirm)


async def stock_logic(target):
    keys = get_available_keys()
    used = get_used_keys()
    embed = discord.Embed(title="📦 Premium Stock", color=discord.Color.blurple())
    embed.add_field(name="Available Keys", value=str(len(keys)), inline=True)
    embed.add_field(name="Keys Claimed", value=str(len(used)), inline=True)
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=embed)
    else:
        await target.send(embed=embed)


# ========================================================
# ==================== SLASH COMMANDS ====================
# ========================================================

@bot.tree.command(name="premiumpanel", description="Show the premium key panel")
async def premiumpanel(interaction: discord.Interaction):
    await panel_logic(interaction)


@bot.tree.command(name="restock", description="Restock premium keys (Staff only)")
@app_commands.describe(key="The premium key to add (or multiple keys separated by comma)")
async def restock(interaction: discord.Interaction, key: str):
    await restock_logic(interaction, key)


@bot.tree.command(name="dm", description="Take keys from the premium stock and DM them to a user (Staff only)")
@app_commands.describe(user="The user to send keys to", amount="How many keys to take from the premium stock (default: 1)", reason="Reason for sending these keys (default: Invalid reason)")
async def dm(interaction: discord.Interaction, user: discord.Member, amount: int = DEFAULT_DM_AMOUNT, reason: str = None):
    await dm_logic(interaction, user, amount, reason)


@bot.tree.command(name="stock", description="Check how many premium keys are in stock")
async def stock(interaction: discord.Interaction):
    await stock_logic(interaction)


@bot.tree.command(name="ticket", description="Send the ticket panel (Setup staff only)")
async def ticket(interaction: discord.Interaction):
    await ticket_setup_logic(interaction)


@bot.tree.command(name="removew", description="Remove wallahi credits from a user (Staff only)")
@app_commands.describe(member="The user to remove from", amount="How many wallahi credits to remove")
async def removew_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not _has_moderation_role(interaction.user):
        await interaction.response.send_message(
            embed=_moderation_embed(
                "Permission Denied",
                "You need the authorized moderator role to use this command.",
                discord.Color.red(),
            ),
            ephemeral=True,
        )
        return
    if amount < 1:
        await interaction.response.send_message(
            embed=_moderation_embed("Invalid amount", "Amount must be at least **1**.", discord.Color.red()),
            ephemeral=True,
        )
        return
    before = _get_wallahi_count(interaction.guild.id, member.id)
    new_balance = _add_wallahi_credits(interaction.guild.id, member.id, -amount)
    removed = before - new_balance
    embed = _moderation_embed(
        "Wallahi credits removed",
        f"Removed **{removed}** wallahi credit(s) from {member.mention}.",
        discord.Color.orange(),
    )
    embed.add_field(name="Previous balance", value=str(before), inline=True)
    embed.add_field(name="New balance", value=str(new_balance), inline=True)
    if removed < amount:
        embed.set_footer(text=f"Only {removed} of {amount} could be removed.")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="removec", description="Remove credits from a user (Staff only)")
@app_commands.describe(member="The user to remove from", amount="How many credits to remove")
async def removec_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not _has_moderation_role(interaction.user):
        await interaction.response.send_message(
            embed=_moderation_embed(
                "Permission Denied",
                "You need the authorized moderator role to use this command.",
                discord.Color.red(),
            ),
            ephemeral=True,
        )
        return
    if amount < 1:
        await interaction.response.send_message(
            embed=_moderation_embed("Invalid amount", "Amount must be at least **1**.", discord.Color.red()),
            ephemeral=True,
        )
        return
    before = _get_credit_balance(interaction.guild.id, member.id)
    new_balance = _add_credit_balance(interaction.guild.id, member.id, -amount)
    removed = before - new_balance
    embed = _moderation_embed(
        "Credits removed",
        f"Removed **{removed}** credit(s) from {member.mention}.",
        discord.Color.orange(),
    )
    embed.add_field(name="Previous balance", value=str(before), inline=True)
    embed.add_field(name="New balance", value=str(new_balance), inline=True)
    if removed < amount:
        embed.set_footer(text=f"Only {removed} of {amount} could be removed.")
    await interaction.response.send_message(embed=embed)


# ========================================================
# ==================== PREFIX COMMANDS ===================
# ========================================================

@bot.command(name="premiumpanel")
async def premiumpanel_prefix(ctx: commands.Context):
    await panel_logic(ctx)


@bot.command(name="restock")
async def restock_prefix(ctx: commands.Context, *, key: str = None):
    if not key:
        embed = discord.Embed(title="❌ Missing Argument", description="Usage: `!restock <key>` or `!restock <key1>,<key2>,...`", color=discord.Color.red())
        await ctx.reply(embed=embed)
        return
    await restock_logic(ctx, key)


@bot.command(name="dm")
async def dm_prefix(ctx: commands.Context, user: discord.Member = None, amount: int = None, *, reason: str = None):
    if user is None:
        embed = discord.Embed(title="❌ Missing Argument", description="Usage: `!dm @user [amount] [reason]`", color=discord.Color.red())
        await ctx.reply(embed=embed)
        return
    await dm_logic(ctx, user, amount, reason)


@bot.command(name="stock")
async def stock_prefix(ctx: commands.Context):
    await stock_logic(ctx)


@bot.command(name="ticket")
async def ticket_prefix(ctx: commands.Context):
    await ticket_setup_logic(ctx)


async def _send_credit_dm(member: discord.Member, amount: int, balance: int, *, reason: str = "Credits earned") -> bool:
    unlimited = has_role(member, JEW_MODE_ROLE_ID)
    embed = discord.Embed(title="💳 Credits received", description=f"You received **{amount}** credit(s).", color=discord.Color.gold())
    embed.add_field(name="Your balance", value="Unlimited (Jew Mode)" if unlimited else str(balance), inline=False)
    embed.set_footer(text=reason)
    try:
        await member.send(embed=embed)
    except discord.HTTPException as error:
        print(f"[!] Could not DM credits to {member} (ID: {member.id}): {error}")
        return False
    return True


async def _track_message_for_credits(message: discord.Message) -> None:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return
    state = _load_user_state(MESSAGE_COUNTS_FILE, message.guild.id)
    guild_state = state[str(message.guild.id)]
    user_id = str(message.author.id)
    message_count = guild_state.get(user_id, 0)
    if not isinstance(message_count, int) or message_count < 0:
        message_count = 0
    earned = (message_count + 1) // MESSAGES_PER_CREDIT
    guild_state[user_id] = (message_count + 1) % MESSAGES_PER_CREDIT
    save_json(MESSAGE_COUNTS_FILE, state)
    balance = _get_credit_balance(message.guild.id, message.author.id)
    if earned:
        balance += earned
        _set_credit_balance(message.guild.id, message.author.id, balance)
        await _send_credit_dm(message.author, earned, balance, reason=f"Earned for every {MESSAGES_PER_CREDIT} messages sent")


async def _complete_credit_purchase(guild: discord.Guild, member: discord.Member, amount: int, *, premium: bool) -> discord.Embed:
    price = 150 if premium else amount
    unlimited = _has_jew_mode(member)
    balance = _get_credit_balance(guild.id, member.id)
    if not premium and amount < 1:
        return _moderation_embed("Invalid amount", "Choose at least one Wallahi.", discord.Color.red())
    if not unlimited and balance < price:
        return _moderation_embed("Not enough credits", f"You need **{price}** credits, but have **{balance}**.", discord.Color.red())
    if premium:
        role = guild.get_role(PREMIUM_ROLE_ID)
        if role is None:
            return _moderation_embed("Purchase unavailable", "The Premium role is not available in this server.", discord.Color.red())
        if role in member.roles:
            return _moderation_embed("Already owned", "You already have the Premium role.", discord.Color.blurple())
        try:
            await member.add_roles(role, reason="Purchased with credits")
        except discord.HTTPException as error:
            print(f"[!] Could not grant Premium role to {member} (ID: {member.id}): {error}")
            return _moderation_embed("Purchase failed", "I couldn't grant the Premium role. Check my role permissions and hierarchy.", discord.Color.red())
        if not unlimited:
            _set_credit_balance(guild.id, member.id, balance - price)
        dm_embed = _moderation_embed("Premium purchased", f"You bought the Premium role for **{price}** credits.", discord.Color.green())
        dm_embed.add_field(name="Credits remaining", value="Unlimited (Jew Mode)" if unlimited else str(balance - price), inline=False)
        try:
            await member.send(embed=dm_embed)
        except discord.HTTPException as error:
            print(f"[!] Could not DM purchase confirmation to {member} (ID: {member.id}): {error}")
            dm_sent = False
        else:
            dm_sent = True
        response = dm_embed.copy()
        response.add_field(name="Direct message", value="Purchase confirmation sent." if dm_sent else "Could not DM you; check your DM settings.", inline=False)
        return response
    if not unlimited:
        _set_credit_balance(guild.id, member.id, balance - price)
    wallahis = _get_wallahi_count(guild.id, member.id) + price
    _set_wallahi_count(guild.id, member.id, wallahis)
    dm_embed = _moderation_embed("Wallahis purchased", f"You bought **{price}** Wallahi credit(s).", discord.Color.green())
    dm_embed.add_field(name="Wallahi credits", value=str(wallahis), inline=True)
    dm_embed.add_field(name="Credits remaining", value="Unlimited (Jew Mode)" if unlimited else str(balance - price), inline=True)
    try:
        await member.send(embed=dm_embed)
    except discord.HTTPException as error:
        print(f"[!] Could not DM purchase confirmation to {member} (ID: {member.id}): {error}")
        dm_sent = False
    else:
        dm_sent = True
    response = dm_embed.copy()
    response.add_field(name="Direct message", value="Purchase confirmation sent." if dm_sent else "Could not DM you; check your DM settings.", inline=False)
    return response


class BuyWallahiModal(discord.ui.Modal, title="Buy Wallahis"):
    amount = discord.ui.TextInput(label="How many Wallahis do you want?", placeholder="Enter the amount", min_length=1, max_length=9)

    def __init__(self, guild: discord.Guild, member: discord.Member):
        super().__init__()
        self.guild = guild
        self.member = member

    async def on_submit(self, interaction: discord.Interaction) -> None:
        amount_text = self.amount.value.strip()
        if not amount_text.isdecimal():
            await interaction.response.send_message(embed=_moderation_embed("Invalid amount", "Enter a whole number greater than zero.", discord.Color.red()), ephemeral=True)
            return
        amount = int(amount_text)
        result = await _complete_credit_purchase(self.guild, self.member, amount, premium=False)
        await interaction.response.send_message(embed=result, ephemeral=True)


class BuyMenuView(discord.ui.View):
    def __init__(self, guild: discord.Guild, member: discord.Member):
        super().__init__(timeout=180)
        self.guild = guild
        self.member = member
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as error:
                print(f"[!] Could not disable expired buy menu: {error}")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.member.id:
            return True
        await interaction.response.send_message(embed=_moderation_embed("This menu isn't yours", "Use `!buy` to open your own purchase menu.", discord.Color.red()), ephemeral=True)
        return False

    @discord.ui.button(label="Buy Premium Role (150 credits)", style=discord.ButtonStyle.primary)
    async def buy_premium(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        result = await _complete_credit_purchase(self.guild, self.member, 150, premium=True)
        await interaction.response.send_message(embed=result, ephemeral=True)

    @discord.ui.button(label="Buy Wallahis", style=discord.ButtonStyle.success)
    async def buy_wallahis(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(BuyWallahiModal(self.guild, self.member))


@bot.command(name="buy")
@commands.guild_only()
async def buy_prefix(ctx: commands.Context):
    member = ctx.author
    balance = _get_credit_balance(ctx.guild.id, member.id)
    balance_text = "Unlimited (Jew Mode)" if _has_jew_mode(member) else str(balance)
    embed = discord.Embed(title="🛒 Choose what to buy", description=("Choose an option below.\n\n" "• **Premium role:** 150 credits\n" "• **Wallahis:** 1 credit each; choose the amount in the next step"), color=discord.Color.gold())
    embed.add_field(name="Your credits", value=balance_text, inline=False)
    view = BuyMenuView(ctx.guild, member)
    view.message = await ctx.reply(embed=embed, view=view)


@bot.command(name="credits")
@commands.guild_only()
async def credits_prefix(ctx: commands.Context):
    if not await _check_moderator(ctx):
        return
    balance = _get_credit_balance(ctx.guild.id, ctx.author.id)
    embed = _moderation_embed("Your credits", "Your balance is **unlimited** because Jew Mode is active." if _has_jew_mode(ctx.author) else f"You have **{balance}** credit(s).", discord.Color.gold())
    await ctx.reply(embed=embed)


@bot.command(name="jew")
@commands.guild_only()
async def jew_prefix(ctx: commands.Context, member: discord.Member):
    if not await _check_moderator(ctx):
        return
    role = ctx.guild.get_role(JEW_MODE_ROLE_ID)
    if role is None:
        await ctx.reply(embed=_moderation_embed("Role unavailable", "The Jew Mode role is not available in this server.", discord.Color.red()))
        return
    if role in member.roles:
        await ctx.reply(embed=_moderation_embed("Already enabled", f"{member.mention} already has Jew Mode.", discord.Color.blurple()))
        return
    try:
        await member.add_roles(role, reason=f"Granted by {ctx.author}")
    except discord.HTTPException as error:
        print(f"[!] Could not grant Jew Mode to {member} (ID: {member.id}): {error}")
        await ctx.reply(embed=_moderation_embed("Role assignment failed", "I couldn't grant Jew Mode. Check my role permissions and hierarchy.", discord.Color.red()))
        return
    await ctx.reply(embed=_moderation_embed("Jew Mode granted", f"{member.mention} now has unlimited credits.", discord.Color.green()))


@bot.command(name="gcredits")
@commands.guild_only()
async def gcredits_prefix(ctx: commands.Context, member: discord.Member, amount: int):
    if not await _check_moderator(ctx):
        return
    if amount < 1:
        await ctx.reply(embed=_moderation_embed("Invalid amount", "Grant at least one credit.", discord.Color.red()))
        return
    balance = _get_credit_balance(ctx.guild.id, member.id) + amount
    _set_credit_balance(ctx.guild.id, member.id, balance)
    dm_sent = await _send_credit_dm(member, amount, balance, reason=f"Granted by {ctx.author}")
    result = _moderation_embed("Credits granted", f"Granted **{amount}** credit(s) to {member.mention}.", discord.Color.green())
    result.add_field(name="Direct message", value="Credit details sent." if dm_sent else "Could not DM the user (their DMs may be closed).", inline=False)
    await ctx.reply(embed=result)


@bot.command(name="removew")
@commands.guild_only()
async def removew_prefix(ctx: commands.Context, member: discord.Member, amount: int):
    if not await _check_moderator(ctx):
        return
    if amount < 1:
        await ctx.reply(embed=_moderation_embed("Invalid amount", "Amount must be at least **1**.", discord.Color.red()))
        return
    before = _get_wallahi_count(ctx.guild.id, member.id)
    new_balance = _add_wallahi_credits(ctx.guild.id, member.id, -amount)
    removed = before - new_balance
    embed = _moderation_embed("Wallahi credits removed", f"Removed **{removed}** wallahi credit(s) from {member.mention}.", discord.Color.orange())
    embed.add_field(name="Previous balance", value=str(before), inline=True)
    embed.add_field(name="New balance", value=str(new_balance), inline=True)
    if removed < amount:
        embed.set_footer(text=f"Only {removed} of {amount} could be removed.")
    await ctx.reply(embed=embed)


@bot.command(name="removec")
@commands.guild_only()
async def removec_prefix(ctx: commands.Context, member: discord.Member, amount: int):
    if not await _check_moderator(ctx):
        return
    if amount < 1:
        await ctx.reply(embed=_moderation_embed("Invalid amount", "Amount must be at least **1**.", discord.Color.red()))
        return
    before = _get_credit_balance(ctx.guild.id, member.id)
    new_balance = _add_credit_balance(ctx.guild.id, member.id, -amount)
    removed = before - new_balance
    embed = _moderation_embed("Credits removed", f"Removed **{removed}** credit(s) from {member.mention}.", discord.Color.orange())
    embed.add_field(name="Previous balance", value=str(before), inline=True)
    embed.add_field(name="New balance", value=str(new_balance), inline=True)
    if removed < amount:
        embed.set_footer(text=f"Only {removed} of {amount} could be removed.")
    await ctx.reply(embed=embed)


async def _send_moderation_dm(member: discord.Member, action: str, moderator: discord.abc.User, reason: str, length: str) -> bool:
    embed = _moderation_embed(f"Server moderation: {action}", f"You were {action.lower()} in **{member.guild.name}**.", discord.Color.orange())
    embed.add_field(name="Reason", value=reason[:1024] or "No reason provided", inline=False)
    embed.add_field(name="Length", value=length[:1024], inline=False)
    embed.add_field(name="Moderator", value=str(moderator)[:1024], inline=False)
    try:
        await member.send(embed=embed)
    except discord.HTTPException:
        return False
    return True


async def _reply_moderation_result(ctx: commands.Context, title: str, description: str, reason: str, dm_sent: bool, color: discord.Color = discord.Color.green()) -> None:
    embed = _moderation_embed(title, description, color)
    embed.add_field(name="Reason", value=reason[:1024] or "No reason provided", inline=False)
    embed.add_field(name="Direct message", value="Sent as an embed." if dm_sent else "Could not DM the user (their DMs may be closed).", inline=False)
    await ctx.reply(embed=embed)


def _parse_timeout_duration(value: str) -> timedelta:
    units = {"s": 1, "m": 60, "h": 60 * 60, "d": 24 * 60 * 60}
    amount_text, unit = value[:-1], value[-1:].lower()
    if not amount_text.isdecimal() or unit not in units:
        raise ValueError("Use a duration such as `10m`, `2h`, or `1d`.")
    seconds = int(amount_text) * units[unit]
    if seconds < 1 or seconds > 28 * 24 * 60 * 60:
        raise ValueError("Duration must be between 1 second and 28 days.")
    return timedelta(seconds=seconds)


async def _handle_wallahi_message(message: discord.Message) -> None:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return
    member = message.author
    guild_id = message.guild.id
    if _has_active_invinc(guild_id, member.id):
        await message.channel.send(embed=_moderation_embed("Wallahi immunity active", f"{member.mention} is protected from automatic wallahi mutes.", discord.Color.blue()))
        return
    count = _get_wallahi_count(guild_id, member.id)
    uses = len(_WALLAHI_PATTERN.findall(message.content))
    if count >= uses:
        _set_wallahi_count(guild_id, member.id, count - uses)
        embed = _moderation_embed("Wallahi credit used", f"{member.mention} used **{uses}** wallahi credit(s).", discord.Color.blurple())
        embed.add_field(name="Credits remaining", value=str(count - uses), inline=False)
        await message.channel.send(embed=embed)
        return
    if count:
        _set_wallahi_count(guild_id, member.id, 0)
    reason = "Used `wallahi` without any wallahi credits."
    duration = timedelta(minutes=15)
    try:
        await member.timeout(duration, reason=reason)
    except discord.Forbidden:
        await message.channel.send(embed=_moderation_embed("Automatic mute failed", f"Couldn't mute {member.mention}. Check the bot's **Moderate Members** permission and role hierarchy.", discord.Color.red()))
        return
    except discord.HTTPException as error:
        await message.channel.send(embed=_moderation_embed("Automatic mute failed", f"Discord couldn't mute {member.mention}: {error}", discord.Color.red()))
        return
    dm_sent = await _send_moderation_dm(member, "Muted", bot.user or message.guild.me, reason, "15 minutes")
    embed = _moderation_embed("Automatic mute", f"{member.mention} was muted for **15 minutes** for using `wallahi` without credits.", discord.Color.orange())
    embed.add_field(name="Direct message", value="Sent as an embed." if dm_sent else "Could not DM the user (their DMs may be closed).", inline=False)
    await message.channel.send(embed=embed)


@bot.command(name="warn")
@commands.guild_only()
async def warn_prefix(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if not await _check_moderator(ctx):
        return
    warnings = load_json(WARNINGS_FILE, [])
    warnings.append({"guild_id": ctx.guild.id, "user_id": member.id, "moderator_id": ctx.author.id, "reason": reason, "created_at": datetime.now(timezone.utc).isoformat()})
    save_json(WARNINGS_FILE, warnings)
    count = sum(entry.get("guild_id") == ctx.guild.id and entry.get("user_id") == member.id for entry in warnings)
    dm_sent = await _send_moderation_dm(member, "Warned", ctx.author, reason, "Not applicable")
    embed = _moderation_embed("User warned", f"{member.mention} has **{count}** warning(s).", discord.Color.orange())
    embed.add_field(name="Reason", value=reason[:1024] or "No reason provided", inline=False)
    embed.add_field(name="Direct message", value="Sent as an embed." if dm_sent else "Could not DM the user (their DMs may be closed).", inline=False)
    await ctx.reply(embed=embed)


@bot.command(name="mute")
@commands.guild_only()
async def mute_prefix(ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
    if not await _check_moderator(ctx):
        return
    try:
        timeout = _parse_timeout_duration(duration)
    except ValueError as error:
        await ctx.reply(embed=_moderation_embed("Invalid duration", str(error), discord.Color.red()))
        return
    try:
        await member.timeout(timeout, reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=_moderation_embed("Mute failed", "I can't mute that member. Check my **Moderate Members** permission and role hierarchy.", discord.Color.red()))
        return
    except discord.HTTPException as error:
        await ctx.reply(embed=_moderation_embed("Mute failed", f"Discord couldn't apply the mute: {error}", discord.Color.red()))
        return
    dm_sent = await _send_moderation_dm(member, "Muted", ctx.author, reason, duration)
    await _reply_moderation_result(ctx, "User muted", f"{member.mention} was muted for **{duration}**.", reason, dm_sent)


@bot.command(name="unmute")
@commands.guild_only()
async def unmute_prefix(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if not await _check_moderator(ctx):
        return
    try:
        await member.timeout(None, reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=_moderation_embed("Unmute failed", "I can't unmute that member. Check my **Moderate Members** permission and role hierarchy.", discord.Color.red()))
        return
    except discord.HTTPException as error:
        await ctx.reply(embed=_moderation_embed("Unmute failed", f"Discord couldn't remove the mute: {error}", discord.Color.red()))
        return
    dm_sent = await _send_moderation_dm(member, "Unmuted", ctx.author, reason, "Mute removed")
    await _reply_moderation_result(ctx, "User unmuted", f"{member.mention}'s mute was removed.", reason, dm_sent)


@bot.command(name="kick")
@commands.guild_only()
async def kick_prefix(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if not await _check_moderator(ctx):
        return
    try:
        await member.kick(reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=_moderation_embed("Kick failed", "I can't kick that member. Check my **Kick Members** permission and role hierarchy.", discord.Color.red()))
        return
    except discord.HTTPException as error:
        await ctx.reply(embed=_moderation_embed("Kick failed", f"Discord couldn't kick the member: {error}", discord.Color.red()))
        return
    dm_sent = await _send_moderation_dm(member, "Kicked", ctx.author, reason, "Not applicable")
    await _reply_moderation_result(ctx, "User kicked", f"{member.mention} was kicked from the server.", reason, dm_sent)


@bot.command(name="ban")
@commands.guild_only()
async def ban_prefix(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if not await _check_moderator(ctx):
        return
    try:
        await member.ban(reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=_moderation_embed("Ban failed", "I can't ban that member. Check my **Ban Members** permission and role hierarchy.", discord.Color.red()))
        return
    except discord.HTTPException as error:
        await ctx.reply(embed=_moderation_embed("Ban failed", f"Discord couldn't ban the member: {error}", discord.Color.red()))
        return
    dm_sent = await _send_moderation_dm(member, "Banned", ctx.author, reason, "Permanent")
    await _reply_moderation_result(ctx, "User banned", f"{member.mention} was permanently banned.", reason, dm_sent)


@bot.command(name="wallahis")
@commands.guild_only()
async def wallahis_prefix(ctx: commands.Context, member: discord.Member, amount: int):
    if not await _check_moderator(ctx):
        return
    if amount < 1:
        await ctx.reply(embed=_moderation_embed("Invalid amount", "Add at least one wallahi credit.", discord.Color.red()))
        return
    total = _get_wallahi_count(ctx.guild.id, member.id) + amount
    _set_wallahi_count(ctx.guild.id, member.id, total)
    embed = _moderation_embed("Wallahi credits added", f"Added **{amount}** wallahi credit(s) to {member.mention}.", discord.Color.green())
    embed.add_field(name="New balance", value=str(total), inline=False)
    await ctx.reply(embed=embed)


@bot.command(name="invinc")
@commands.guild_only()
async def invinc_prefix(ctx: commands.Context, member: discord.Member, length: str, *, reason: str):
    if not await _check_moderator(ctx):
        return
    try:
        duration = _parse_timeout_duration(length)
    except ValueError as error:
        await ctx.reply(embed=_moderation_embed("Invalid duration", str(error), discord.Color.red()))
        return
    expires_at = datetime.now(timezone.utc) + duration
    state = _load_user_state(INVINC_FILE, ctx.guild.id)
    state[str(ctx.guild.id)][str(member.id)] = expires_at.isoformat()
    save_json(INVINC_FILE, state)
    embed = _moderation_embed("Wallahi immunity granted", f"{member.mention} is protected from automatic wallahi mutes for **{length}**.", discord.Color.green())
    embed.add_field(name="Reason", value=reason[:1024], inline=False)
    embed.add_field(name="Expires", value=discord.utils.format_dt(expires_at, style="R"), inline=False)
    await ctx.reply(embed=embed)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if ctx.command is None or ctx.command.name not in _MODERATION_COMMAND_NAMES:
        raise error
    if isinstance(error, commands.MissingRequiredArgument):
        description = f"Missing required argument: `{error.param.name}`."
    elif isinstance(error, commands.BadArgument):
        description = "I couldn't resolve that user or parse one of the arguments."
    elif isinstance(error, commands.NoPrivateMessage):
        description = "This command can only be used in a server."
    else:
        print(f"[!] Moderation command error in {ctx.command.qualified_name}: {error}")
        description = "The command couldn't be completed because of an unexpected error."
    await ctx.reply(embed=_moderation_embed("Command error", description, discord.Color.red()))


# ==================== RUN ====================
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Missing Discord bot token. Set it in Visual Studio's "
            "Properties/launchSettings.json (environmentVariables) or in a .env file."
        )
    bot.run(TOKEN)
