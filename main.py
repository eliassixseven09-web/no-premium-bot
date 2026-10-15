"""
🚀 PREMIUM DISCORD BOT - Single File Edition
Railway-ready. Add DISCORD_TOKEN to env vars and deploy.
"""

import asyncio
import json
import logging
import os
import random
import re
import signal
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# =============================================================================
# ============================ CONFIGURATION ==================================
# =============================================================================

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "transcripts")
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def data_path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def backup_path(guild_id: int) -> str:
    return os.path.join(BACKUP_DIR, f"{guild_id}.json")


# ---------- Role IDs (EDIT THESE) ----------
REQUIRED_ROLES_FOR_PANEL = [1535650014565507225, 1535650018621394944]
RESTOCK_ROLE_ID = 1535650003975147540
DM_ROLE_ID = 1555668778635886685
MODERATION_ROLE_ID = 1555668778635886685
TICKET_SETUP_ROLE_ID = 1555668778635886685
TICKET_STAFF_ROLE_ID = 1535650011151601724
TICKET_CATEGORY_ID = 1535650054910775307
KEY_DROP_CHANNEL_ID = 1535650094442090557
PREMIUM_ROLE_ID = 1535650014565507225
JEW_MODE_ROLE_ID = 1558065787351204033

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0")) or None

# ---------- Economy ----------
MESSAGES_PER_CREDIT = 150
DAILY_REWARD = 5
ROB_COOLDOWN = 7200
ROB_SUCCESS_RATE = 0.4
ROB_MAX_STEAL = 500

# ---------- Automod ----------
AUTOMOD_ENABLED = True
SPAM_THRESHOLD = 5
SPAM_INTERVAL = 5
MAX_MENTIONS = 5
MAX_CAPS_PERCENT = 70
BAD_WORDS = []

# ---------- Anti-Nuke ----------
ANTINUKE_ENABLED = True
ANTINUKE_CHANNEL_DELETE_THRESHOLD = 2     # how many deletions...
ANTINUKE_CHANNEL_DELETE_WINDOW = 5        # ...within this many seconds → ban
ANTINUKE_CHANNEL_CREATE_THRESHOLD = 5     # mass channel creation
ANTINUKE_CHANNEL_CREATE_WINDOW = 10
ANTINUKE_ROLE_DELETE_THRESHOLD = 2
ANTINUKE_ROLE_DELETE_WINDOW = 5
ANTINUKE_BAN_THRESHOLD = 3                # mass bans
ANTINUKE_BAN_WINDOW = 10
ANTINUKE_KICK_THRESHOLD = 3               # mass kicks
ANTINUKE_KICK_WINDOW = 10

# ---------- Ticket ----------
DEFAULT_DM_AMOUNT = 1
DEFAULT_DM_REASON = "Invalid reason"
MAX_TXT_FILE_SIZE = 5 * 1024 * 1024

COMMAND_PREFIXES = ["!", "a!"]

PORT = int(os.getenv("PORT", "8080"))
ENABLE_WEB_SERVER = os.getenv("ENABLE_WEB_SERVER", "true").lower() == "true"

COLOR_PRIMARY = 0x5865F2
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_ERROR = 0xED4245
COLOR_GOLD = 0xF1C40F
COLOR_PREMIUM = 0xFFD700

# =============================================================================
# ============================== LOGGING ======================================
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("bot")

# =============================================================================
# ============================ FILE PATHS =====================================
# =============================================================================

KEYS_FILE = data_path("keys.json")
USED_FILE = data_path("used_keys.json")
TICKETS_FILE = data_path("tickets.json")
FEEDBACK_FILE = data_path("ticket_feedback.json")
WARNINGS_FILE = data_path("warnings.json")
WALLAHIS_FILE = data_path("wallahis.json")
INVINC_FILE = data_path("invinc.json")
CREDITS_FILE = data_path("credits.json")
MESSAGE_COUNTS_FILE = data_path("message_counts.json")
AFK_FILE = data_path("afk.json")
GIVEAWAYS_FILE = data_path("giveaways.json")
RR_FILE = data_path("reaction_roles.json")
COOLDOWNS_FILE = data_path("cooldowns.json")

# =============================================================================
# ============================ SAFE JSON I/O ==================================
# =============================================================================

def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
        except OSError as e:
            log.error(f"Could not create {path}: {e}")
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error(f"Could not read {path}: {e}")
        return default


def save_json(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        log.error(f"Could not save {path}: {e}")


# =============================================================================
# =========================== STATE HELPERS ===================================
# =============================================================================

def _load_guild_state(path: str, guild_id: int) -> dict:
    state = load_json(path, {})
    if not isinstance(state, dict):
        state = {}
    gs = state.setdefault(str(guild_id), {})
    if not isinstance(gs, dict):
        gs = {}
        state[str(guild_id)] = gs
    return state


def get_int_balance(path: str, guild_id: int, user_id: int) -> int:
    state = _load_guild_state(path, guild_id)
    v = state[str(guild_id)].get(str(user_id), 0)
    return v if isinstance(v, int) and v > 0 else 0


def set_int_balance(path: str, guild_id: int, user_id: int, amount: int) -> None:
    state = _load_guild_state(path, guild_id)
    gs = state[str(guild_id)]
    if amount > 0:
        gs[str(user_id)] = amount
    else:
        gs.pop(str(user_id), None)
    save_json(path, state)


def add_int_balance(path: str, guild_id: int, user_id: int, amount: int) -> int:
    current = get_int_balance(path, guild_id, user_id)
    new = max(0, current + amount)
    set_int_balance(path, guild_id, user_id, new)
    return new


def get_credit_balance(g, u): return get_int_balance(CREDITS_FILE, g, u)
def set_credit_balance(g, u, a): return set_int_balance(CREDITS_FILE, g, u, a)
def add_credit_balance(g, u, a): return add_int_balance(CREDITS_FILE, g, u, a)

def get_wallahi_count(g, u): return get_int_balance(WALLAHIS_FILE, g, u)
def set_wallahi_count(g, u, a): return set_int_balance(WALLAHIS_FILE, g, u, a)
def add_wallahi_credits(g, u, a): return add_int_balance(WALLAHIS_FILE, g, u, a)


def has_active_invinc(guild_id: int, user_id: int) -> bool:
    state = _load_guild_state(INVINC_FILE, guild_id)
    gs = state[str(guild_id)]
    val = gs.get(str(user_id))
    if not isinstance(val, str):
        return False
    try:
        expiry = datetime.fromisoformat(val)
    except ValueError:
        gs.pop(str(user_id), None)
        save_json(INVINC_FILE, state)
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry > datetime.now(timezone.utc):
        return True
    gs.pop(str(user_id), None)
    save_json(INVINC_FILE, state)
    return False


# =============================================================================
# ============================ HELPERS ========================================
# =============================================================================

def has_role(member: discord.Member, role_id: int) -> bool:
    return isinstance(member, discord.Member) and any(r.id == role_id for r in member.roles)


def has_any_role(member: discord.Member, role_ids) -> bool:
    if not isinstance(member, discord.Member):
        return False
    ids = {r.id for r in member.roles}
    return any(rid in ids for rid in role_ids)


def is_jew_mode(member) -> bool:
    return has_role(member, JEW_MODE_ROLE_ID)


def is_mod(member) -> bool:
    return has_role(member, MODERATION_ROLE_ID)


def embed(title: str, description: str = "", color: int = COLOR_PRIMARY) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.timestamp = datetime.now(timezone.utc)
    return e


def success_embed(title: str, description: str = "") -> discord.Embed:
    return embed(f"✅ {title}", description, COLOR_SUCCESS)


def error_embed(title: str, description: str = "") -> discord.Embed:
    return embed(f"❌ {title}", description, COLOR_ERROR)


def warning_embed(title: str, description: str = "") -> discord.Embed:
    return embed(f"⚠️ {title}", description, COLOR_WARNING)


def parse_duration(value: str) -> timedelta:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(value) < 2:
        raise ValueError("Use `10m`, `2h`, or `1d`.")
    amt_text, unit = value[:-1], value[-1].lower()
    if not amt_text.isdecimal() or unit not in units:
        raise ValueError("Use `10m`, `2h`, or `1d`.")
    secs = int(amt_text) * units[unit]
    if secs < 1 or secs > 28 * 86400:
        raise ValueError("Duration must be between 1s and 28d.")
    return timedelta(seconds=secs)


# =============================================================================
# ============================= BOT CLASS =====================================
# =============================================================================

class PremiumBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.reactions = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(*COMMAND_PREFIXES),
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True
            ),
        )
        self.start_time = datetime.now(timezone.utc)
        self.snipe_cache: dict[int, dict] = {}
        self.edit_snipe_cache: dict[int, dict] = {}
        self.spam_tracker = defaultdict(lambda: deque(maxlen=10))
        # Antinuke trackers: guild_id -> deque of (timestamp, actor_id)
        self.an_channel_delete = defaultdict(lambda: deque(maxlen=20))
        self.an_channel_create = defaultdict(lambda: deque(maxlen=20))
        self.an_role_delete = defaultdict(lambda: deque(maxlen=20))
        self.an_ban = defaultdict(lambda: deque(maxlen=20))
        self.an_kick = defaultdict(lambda: deque(maxlen=20))
        # Track who invited which bot: bot_id -> inviter_id
        self.bot_inviters: dict[int, int] = {}

    async def setup_hook(self):
        self.add_view(PremiumView())
        self.add_view(TicketOpenView())
        self.add_view(TicketControlView())
        self._restore_rr_views()
        self.check_giveaways.start()
        try:
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} global slash commands")
        except discord.HTTPException as e:
            log.error(f"Slash sync failed: {e}")

    def _restore_rr_views(self):
        data = load_json(RR_FILE, {})
        for mid, info in data.items():
            try:
                view = RRPersistentView(info["guild_id"], int(mid), info.get("roles", []))
                self.add_view(view)
            except Exception as e:
                log.error(f"RR restore failed: {e}")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Guilds: {len(self.guilds)} | Users: {sum(g.member_count or 0 for g in self.guilds)}")
        # Cache bot inviters
        for guild in self.guilds:
            try:
                async for entry in guild.audit_logs(limit=100, action=discord.AuditLogAction.bot_add):
                    self.bot_inviters[entry.target.id] = entry.user.id
            except (discord.Forbidden, discord.HTTPException):
                pass
        try:
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(self.guilds)} servers | /help",
                ),
                status=discord.Status.online,
            )
        except Exception as e:
            log.error(f"Presence failed: {e}")

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        data = load_json(GIVEAWAYS_FILE, {})
        now = datetime.now(timezone.utc)
        changed = False
        for gid, g in list(data.items()):
            if g.get("ended"):
                continue
            try:
                ends_at = datetime.fromisoformat(g["ends_at"])
            except Exception:
                continue
            if ends_at <= now:
                g["ended"] = True
                changed = True
                try:
                    ch = self.get_channel(g["channel_id"])
                    if not ch:
                        continue
                    msg = await ch.fetch_message(g["message_id"])
                    entries = g.get("entries", [])
                    winners = random.sample(entries, min(g.get("winners", 1), len(entries))) if entries else []
                    e = embed("🎉 Giveaway Ended",
                        f"**Prize:** {g['prize']}\n**Winners:** " +
                        (", ".join(f"<@{w}>" for w in winners) if winners else "No entries"),
                        COLOR_GOLD)
                    await msg.edit(embed=e, view=None)
                    if winners:
                        await ch.send(f"🎊 Congratulations {', '.join(f'<@{w}>' for w in winners)}! You won **{g['prize']}**!")
                except Exception as ex:
                    log.error(f"Giveaway end failed: {ex}")
        if changed:
            save_json(GIVEAWAYS_FILE, data)

    @check_giveaways.before_loop
    async def _before_giveaways(self):
        await self.wait_until_ready()


bot = PremiumBot()

# =============================================================================
# =========================== SERVER BACKUP ===================================
# =============================================================================

def _serialize_overwrites(channel: discord.abc.GuildChannel) -> dict:
    """Serialize channel permission overwrites to a JSON-safe dict."""
    out = {}
    for target, ow in channel.overwrites.items():
        allow, deny = ow.pair()
        # Target is Role or Member
        if isinstance(target, discord.Role):
            key = f"role:{target.id}"
        elif isinstance(target, discord.Member):
            key = f"member:{target.id}"
        else:
            continue
        out[key] = {
            "allow": allow.value,
            "deny": deny.value,
        }
    return out


def serialize_guild(guild: discord.Guild) -> dict:
    """Snapshot everything important about a guild."""
    data = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "icon_url": guild.icon.url if guild.icon else None,
        "roles": [],
        "categories": [],
        "channels": [],
    }

    # Roles
    for role in guild.roles:
        if role.is_default():
            continue  # skip @everyone
        if role.managed:
            continue  # bot-managed roles can't be re-created
        data["roles"].append({
            "id": role.id,
            "name": role.name,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "permissions": role.permissions.value,
            "position": role.position,
            "is_bot_managed": role.managed,
        })

    # Categories
    for cat in guild.categories:
        data["categories"].append({
            "id": cat.id,
            "name": cat.name,
            "position": cat.position,
            "overwrites": _serialize_overwrites(cat),
        })

    # Channels
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            continue
        entry = {
            "id": ch.id,
            "name": ch.name,
            "type": str(ch.type),
            "position": ch.position,
            "category_id": ch.category.id if ch.category else None,
            "overwrites": _serialize_overwrites(ch),
            "nsfw": getattr(ch, "nsfw", False),
            "topic": getattr(ch, "topic", None),
            "slowmode_delay": getattr(ch, "slowmode_delay", 0),
            "bitrate": getattr(ch, "bitrate", None),
            "user_limit": getattr(ch, "user_limit", None),
        }
        data["channels"].append(entry)

    return data


async def _get_guild_owner_id(guild: discord.Guild) -> Optional[int]:
    if guild.owner_id:
        return guild.owner_id
    try:
        g = await bot.fetch_guild(guild.id, with_counts=False)
        return g.owner_id
    except discord.HTTPException:
        return None


async def serversave_logic(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message(embed=error_embed("Server Only", ""), ephemeral=True)
        return

    owner_id = await _get_guild_owner_id(guild)
    if owner_id is None or interaction.user.id != owner_id:
        await interaction.response.send_message(
            embed=error_embed("Owner Only", "Only the server owner can save the server."),
            ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        data = serialize_guild(guild)
        save_json(backup_path(guild.id), data)
        e = success_embed("Server Saved", "Backup created successfully.")
        e.add_field(name="Guild", value=f"{guild.name} (`{guild.id}`)")
        e.add_field(name="Roles", value=str(len(data["roles"])), inline=True)
        e.add_field(name="Categories", value=str(len(data["categories"])), inline=True)
        e.add_field(name="Channels", value=str(len(data["channels"])), inline=True)
        e.set_footer(text="Use /loadserver to restore")
        await interaction.followup.send(embed=e, ephemeral=True)
    except Exception as ex:
        log.exception(f"serversave failed: {ex}")
        await interaction.followup.send(embed=error_embed("Save Failed", str(ex)[:1024]), ephemeral=True)


def _overwrites_from_data(guild: discord.Guild, ow_data: dict) -> dict:
    """Rebuild a Discord PermissionOverwrite dict from serialized data."""
    result = {}
    for key, payload in ow_data.items():
        try:
            kind, id_str = key.split(":", 1)
            tid = int(id_str)
        except (ValueError, IndexError):
            continue
        target = None
        if kind == "role":
            target = guild.get_role(tid)
        elif kind == "member":
            target = guild.get_member(tid)
        if target is None:
            continue
        result[target] = discord.PermissionOverwrite.from_pair(
            discord.Permissions(payload.get("allow", 0)),
            discord.Permissions(payload.get("deny", 0)),
        )
    return result


async def _loadserver_core(guild: discord.Guild, progress_msg: Optional[discord.Message] = None):
    """Restore a guild from backup. Returns a report dict."""
    path = backup_path(guild.id)
    if not os.path.exists(path):
        return None, "No backup found for this server."

    data = load_json(path, None)
    if not data:
        return None, "Backup file is empty or corrupted."

    report = {"roles_created": 0, "roles_failed": 0,
              "categories_created": 0, "categories_failed": 0,
              "channels_created": 0, "channels_failed": 0,
              "channels_skipped": 0, "errors": []}

    async def _update_progress(text: str):
        if progress_msg:
            try:
                await progress_msg.edit(embed=embed("⏳ Restoring...", text, COLOR_WARNING))
            except discord.HTTPException:
                pass

    # ---- 1. Restore ROLES ----
    await _update_progress("Restoring roles...")
    existing_roles_by_name = {r.name: r for r in guild.roles}
    id_to_role: dict[int, discord.Role] = {}

    # Sort by position ascending so hierarchy is preserved
    for role_data in sorted(data.get("roles", []), key=lambda x: x.get("position", 0)):
        old_id = role_data["id"]
        name = role_data["name"]
        # If role still exists (by name), map it
        if name in existing_roles_by_name:
            id_to_role[old_id] = existing_roles_by_name[name]
            continue
        try:
            # Strip dangerous perms for safety — never grant administrator
            perms_value = role_data.get("permissions", 0)
            # Never grant administrator or manage_guild to restored roles
            dangerous = (discord.Permissions.administrator.value |
                         discord.Permissions.manage_guild.value |
                         discord.Permissions.ban_members.value |
                         discord.Permissions.kick_members.value |
                         discord.Permissions.manage_roles.value |
                         discord.Permissions.manage_channels.value)
            perms_value &= ~dangerous
            new_role = await guild.create_role(
                name=name,
                color=discord.Color(role_data.get("color", 0)),
                hoist=role_data.get("hoist", False),
                mentionable=role_data.get("mentionable", False),
                permissions=discord.Permissions(perms_value),
                reason="Server restore",
            )
            id_to_role[old_id] = new_role
            report["roles_created"] += 1
        except discord.HTTPException as e:
            report["roles_failed"] += 1
            report["errors"].append(f"Role '{name}': {e}")
        await asyncio.sleep(0.3)

    # ---- 2. Restore CATEGORIES ----
    await _update_progress("Restoring categories...")
    id_to_category: dict[int, discord.CategoryChannel] = {}
    existing_cats = {c.name: c for c in guild.categories}

    for cat_data in sorted(data.get("categories", []), key=lambda x: x.get("position", 0)):
        old_id = cat_data["id"]
        name = cat_data["name"]
        if name in existing_cats:
            id_to_category[old_id] = existing_cats[name]
            continue
        try:
            ow = _overwrites_from_data(guild, cat_data.get("overwrites", {}))
            cat = await guild.create_category(
                name=name, overwrites=ow, reason="Server restore",
            )
            id_to_category[old_id] = cat
            report["categories_created"] += 1
        except discord.HTTPException as e:
            report["categories_failed"] += 1
            report["errors"].append(f"Category '{name}': {e}")
        await asyncio.sleep(0.3)

    # ---- 3. Restore CHANNELS ----
    await _update_progress("Restoring channels...")
    existing_channels = {c.name: c for c in guild.channels}

    for ch_data in sorted(data.get("channels", []), key=lambda x: x.get("position", 0)):
        name = ch_data["name"]
        if name in existing_channels:
            report["channels_skipped"] += 1
            continue

        ch_type = ch_data.get("type", "text")
        category_id = ch_data.get("category_id")
        parent = id_to_category.get(category_id) if category_id else None

        try:
            ow = _overwrites_from_data(guild, ch_data.get("overwrites", {}))
        except Exception:
            ow = {}

        try:
            if "voice" in ch_type:
                await guild.create_voice_channel(
                    name=name, overwrites=ow, category=parent,
                    bitrate=ch_data.get("bitrate") or 64000,
                    user_limit=ch_data.get("user_limit") or 0,
                    reason="Server restore",
                )
            elif "forum" in ch_type:
                # Fallback: forums have extra config; create as text
                await guild.create_text_channel(
                    name=name, overwrites=ow, category=parent,
                    topic=ch_data.get("topic") or "", reason="Server restore",
                )
            elif "stage" in ch_type:
                await guild.create_stage_channel(
                    name=name, overwrites=ow, category=parent, reason="Server restore",
                )
            elif "news" in ch_type or "announcement" in ch_type:
                try:
                    await guild.create_text_channel(
                        name=name, overwrites=ow, category=parent,
                        topic=ch_data.get("topic") or "",
                        news=True, reason="Server restore",
                    )
                except Exception:
                    await guild.create_text_channel(
                        name=name, overwrites=ow, category=parent,
                        topic=ch_data.get("topic") or "", reason="Server restore",
                    )
            else:
                # default text
                await guild.create_text_channel(
                    name=name, overwrites=ow, category=parent,
                    topic=ch_data.get("topic") or "",
                    slowmode_delay=ch_data.get("slowmode_delay") or 0,
                    nsfw=ch_data.get("nsfw", False),
                    reason="Server restore",
                )
            report["channels_created"] += 1
        except discord.HTTPException as e:
            report["channels_failed"] += 1
            report["errors"].append(f"Channel '{name}': {e}")
        await asyncio.sleep(0.3)

    return report, None


async def loadserver_logic(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message(embed=error_embed("Server Only", ""), ephemeral=True)
        return
    owner_id = await _get_guild_owner_id(guild)
    if owner_id is None or interaction.user.id != owner_id:
        await interaction.response.send_message(
            embed=error_embed("Owner Only", "Only the server owner can load the server."),
            ephemeral=True)
        return

    if not os.path.exists(backup_path(guild.id)):
        await interaction.response.send_message(
            embed=error_embed("No Backup", "No backup exists. Use `/serversave` first."),
            ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    progress = await interaction.followup.send(
        embed=embed("⏳ Restoring...", "Starting restore.", COLOR_WARNING),
        ephemeral=True, wait=True)

    try:
        report, err = await _loadserver_core(guild, progress)
        if err:
            await progress.edit(embed=error_embed("Restore Failed", err))
            return
        e = success_embed("Server Restored", "Backup loaded successfully.")
        e.add_field(name="Roles created", value=str(report["roles_created"]), inline=True)
        e.add_field(name="Categories", value=str(report["categories_created"]), inline=True)
        e.add_field(name="Channels created", value=str(report["channels_created"]), inline=True)
        e.add_field(name="Channels skipped", value=str(report["channels_skipped"]), inline=True)
        if report["roles_failed"] or report["categories_failed"] or report["channels_failed"]:
            e.add_field(name="Failed", value=(
                f"Roles: {report['roles_failed']} | "
                f"Categories: {report['categories_failed']} | "
                f"Channels: {report['channels_failed']}"
            ), inline=False)
        if report["errors"]:
            err_text = "\n".join(report["errors"][:5])
            e.add_field(name="First errors", value=f"```{err_text[:900]}```", inline=False)
        await progress.edit(embed=e)
    except Exception as ex:
        log.exception(f"loadserver failed: {ex}")
        await progress.edit(embed=error_embed("Restore Failed", str(ex)[:1024]))


# =============================================================================
# =========================== BOT EVENTS ======================================
# =============================================================================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if isinstance(message.channel, discord.DMChannel):
        await _handle_dm_feedback(message)
        return

    if not message.guild:
        return

    await _remove_afk(message)
    await _check_afk(message)
    await _track_message_for_credits(message)

    if await _run_automod(message):
        return

    if re.search(r"(?<!\w)wallahi(?!\w)", message.content, re.IGNORECASE):
        await _handle_wallahi_message(message)
        return

    if message.channel.id == KEY_DROP_CHANNEL_ID:
        await _handle_key_drop(message)
        return

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    bot.snipe_cache[message.channel.id] = {
        "author": str(message.author),
        "author_id": message.author.id,
        "content": message.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    bot.edit_snipe_cache[before.channel.id] = {
        "author": str(before.author),
        "author_id": before.author.id,
        "before": before.content,
        "after": after.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------- ANTINUKE HANDLERS ----------

async def _get_audit_actor(guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
    """Find the most recent audit log entry for a given action + target."""
    try:
        async for entry in guild.audit_logs(limit=10, action=action):
            if entry.target and getattr(entry.target, "id", None) == target_id:
                return entry.user, entry
    except (discord.Forbidden, discord.HTTPException):
        return None, None
    return None, None


async def _antinuke_punish(guild: discord.Guild, actor: discord.abc.User, reason: str, invite_check: bool = False):
    """Ban the actor. If they're a bot, also ban whoever invited them."""
    if actor.id == bot.user.id:
        return
    if actor.id == guild.owner_id:
        return
    # Extra safety: don't act on roles above us
    try:
        member = guild.get_member(actor.id) or await guild.fetch_member(actor.id)
    except (discord.NotFound, discord.HTTPException):
        member = None

    if member and guild.me and member.top_role >= guild.me.top_role:
        log.warning(f"[ANTINUKE] Cannot ban {actor} — role too high.")
        await _antinuke_log(guild, f"⚠️ Could not ban **{actor}** ({actor.id}) — role is above mine.")
        return

    # Ban the actor
    try:
        await guild.ban(actor, reason=f"Anti-Nuke: {reason}", delete_message_days=1)
        await _antinuke_log(guild, f"🔨 Banned **{actor}** (`{actor.id}`) — {reason}")
    except discord.Forbidden:
        await _antinuke_log(guild, f"⚠️ Failed to ban **{actor}** — missing permissions.")
    except discord.HTTPException as e:
        await _antinuke_log(guild, f"⚠️ Error banning **{actor}** — {e}")

    # If a bot, ban the inviter too
    if invite_check and isinstance(actor, (discord.User, discord.Member)) and actor.bot:
        inviter_id = bot.bot_inviters.get(actor.id)
        if not inviter_id:
            # try to look it up now
            try:
                async for entry in guild.audit_logs(limit=50, action=discord.AuditLogAction.bot_add):
                    if entry.target and entry.target.id == actor.id:
                        inviter_id = entry.user.id
                        break
            except (discord.Forbidden, discord.HTTPException):
                pass
        if inviter_id and inviter_id != guild.owner_id and inviter_id != bot.user.id:
            try:
                inviter_member = guild.get_member(inviter_id) or await guild.fetch_member(inviter_id)
            except (discord.NotFound, discord.HTTPException):
                inviter_member = None
            if inviter_member:
                if inviter_member.top_role >= (guild.me.top_role if guild.me else None):
                    await _antinuke_log(guild, f"⚠️ Could not ban inviter <@{inviter_id}> — role too high.")
                else:
                    try:
                        await guild.ban(inviter_member,
                                        reason=f"Anti-Nuke: invited malicious bot {actor}",
                                        delete_message_days=1)
                        await _antinuke_log(guild, f"🔨 Banned inviter <@{inviter_id}> for inviting malicious bot **{actor}**")
                    except (discord.Forbidden, discord.HTTPException) as e:
                        await _antinuke_log(guild, f"⚠️ Could not ban inviter <@{inviter_id}>: {e}")


async def _antinuke_log(guild: discord.Guild, text: str):
    log.info(f"[ANTINUKE] {guild.name}: {text}")
    if not LOG_CHANNEL_ID:
        return
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if not ch:
        return
    try:
        await ch.send(embed=embed("🛡️ Anti-Nuke", text, COLOR_ERROR))
    except discord.HTTPException:
        pass


def _check_threshold(dq: deque, window: int, threshold: int) -> bool:
    """Check if threshold events happened within window seconds."""
    now = time.time()
    # purge old
    while dq and now - dq[0][0] > window:
        dq.popleft()
    return len(dq) >= threshold


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    if not ANTINUKE_ENABLED:
        return
    guild = channel.guild
    actor, entry = await _get_audit_actor(guild, discord.AuditLogAction.channel_delete, channel.id)
    if not actor:
        return
    if actor.id == bot.user.id or actor.id == guild.owner_id:
        return

    dq = bot.an_channel_delete[guild.id]
    dq.append((time.time(), actor.id))

    # Only count deletions by the same actor in the window
    now = time.time()
    same_actor = [(t, uid) for (t, uid) in dq if uid == actor.id and now - t <= ANTINUKE_CHANNEL_DELETE_WINDOW]
    if len(same_actor) >= ANTINUKE_CHANNEL_DELETE_THRESHOLD:
        await _antinuke_log(guild,
            f"🚨 **{actor}** deleted {len(same_actor)} channels in {ANTINUKE_CHANNEL_DELETE_WINDOW}s "
            f"(last: `#{channel.name}`). Banning.")
        await _antinuke_punish(guild, actor,
            f"deleted {len(same_actor)} channels in {ANTINUKE_CHANNEL_DELETE_WINDOW}s",
            invite_check=True)
        dq.clear()


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    if not ANTINUKE_ENABLED:
        return
    guild = channel.guild
    actor, entry = await _get_audit_actor(guild, discord.AuditLogAction.channel_create, channel.id)
    if not actor:
        return
    if actor.id == bot.user.id or actor.id == guild.owner_id:
        return

    dq = bot.an_channel_create[guild.id]
    dq.append((time.time(), actor.id))
    now = time.time()
    same_actor = [(t, uid) for (t, uid) in dq if uid == actor.id and now - t <= ANTINUKE_CHANNEL_CREATE_WINDOW]
    if len(same_actor) >= ANTINUKE_CHANNEL_CREATE_THRESHOLD:
        await _antinuke_log(guild,
            f"🚨 **{actor}** created {len(same_actor)} channels in {ANTINUKE_CHANNEL_CREATE_WINDOW}s. Banning.")
        await _antinuke_punish(guild, actor,
            f"mass channel creation ({len(same_actor)} in {ANTINUKE_CHANNEL_CREATE_WINDOW}s)",
            invite_check=True)
        dq.clear()


@bot.event
async def on_guild_role_delete(role: discord.Role):
    if not ANTINUKE_ENABLED:
        return
    guild = role.guild
    actor, entry = await _get_audit_actor(guild, discord.AuditLogAction.role_delete, role.id)
    if not actor:
        return
    if actor.id == bot.user.id or actor.id == guild.owner_id:
        return
    dq = bot.an_role_delete[guild.id]
    dq.append((time.time(), actor.id))
    now = time.time()
    same_actor = [(t, uid) for (t, uid) in dq if uid == actor.id and now - t <= ANTINUKE_ROLE_DELETE_WINDOW]
    if len(same_actor) >= ANTINUKE_ROLE_DELETE_THRESHOLD:
        await _antinuke_log(guild,
            f"🚨 **{actor}** deleted {len(same_actor)} roles in {ANTINUKE_ROLE_DELETE_WINDOW}s. Banning.")
        await _antinuke_punish(guild, actor,
            f"deleted {len(same_actor)} roles in {ANTINUKE_ROLE_DELETE_WINDOW}s",
            invite_check=True)
        dq.clear()


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    if not ANTINUKE_ENABLED:
        return
    actor, entry = await _get_audit_actor(guild, discord.AuditLogAction.ban, user.id)
    if not actor:
        return
    if actor.id == bot.user.id or actor.id == guild.owner_id:
        return
    dq = bot.an_ban[guild.id]
    dq.append((time.time(), actor.id))
    now = time.time()
    same_actor = [(t, uid) for (t, uid) in dq if uid == actor.id and now - t <= ANTINUKE_BAN_WINDOW]
    if len(same_actor) >= ANTINUKE_BAN_THRESHOLD:
        await _antinuke_log(guild,
            f"🚨 **{actor}** banned {len(same_actor)} members in {ANTINUKE_BAN_WINDOW}s. Banning.")
        await _antinuke_punish(guild, actor,
            f"mass banning ({len(same_actor)} in {ANTINUKE_BAN_WINDOW}s)",
            invite_check=True)
        dq.clear()


@bot.event
async def on_member_remove(member: discord.Member):
    if not ANTINUKE_ENABLED:
        return
    guild = member.guild
    actor, entry = await _get_audit_actor(guild, discord.AuditLogAction.kick, member.id)
    if not actor:
        return
    # Only treat as kick if the audit entry is recent (< 5s)
    try:
        if (datetime.now(timezone.utc) - entry.created_at).total_seconds() > 5:
            return
    except Exception:
        return
    if actor.id == bot.user.id or actor.id == guild.owner_id:
        return
    dq = bot.an_kick[guild.id]
    dq.append((time.time(), actor.id))
    now = time.time()
    same_actor = [(t, uid) for (t, uid) in dq if uid == actor.id and now - t <= ANTINUKE_KICK_WINDOW]
    if len(same_actor) >= ANTINUKE_KICK_THRESHOLD:
        await _antinuke_log(guild,
            f"🚨 **{actor}** kicked {len(same_actor)} members in {ANTINUKE_KICK_WINDOW}s. Banning.")
        await _antinuke_punish(guild, actor,
            f"mass kicking ({len(same_actor)} in {ANTINUKE_KICK_WINDOW}s)",
            invite_check=True)
        dq.clear()


@bot.event
async def on_member_join(member: discord.Member):
    # Track bots that join so we can identify inviter if they later nuke
    if member.bot:
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                if entry.target and entry.target.id == member.id:
                    bot.bot_inviters[member.id] = entry.user.id
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        e = error_embed("Missing Argument",
            f"`{error.param.name}` is required.\n**Usage:** `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        e = error_embed("Invalid Argument", "One of your arguments couldn't be parsed.")
    elif isinstance(error, commands.MissingPermissions):
        e = error_embed("Missing Permissions", "You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        e = error_embed("Bot Missing Permissions", f"I need: `{', '.join(error.missing_permissions)}`")
    elif isinstance(error, commands.CommandOnCooldown):
        e = warning_embed("Slow Down!", f"Try again in **{error.retry_after:.1f}s**.")
    elif isinstance(error, commands.NoPrivateMessage):
        e = error_embed("Server Only", "This command can only be used in a server.")
    else:
        log.exception(f"Command error in {ctx.command}: {error}")
        e = error_embed("Unexpected Error", "Something went wrong.")
    try:
        await ctx.reply(embed=e, mention_author=False)
    except discord.HTTPException:
        pass


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        e = warning_embed("Slow Down!", f"Try again in **{error.retry_after:.1f}s**.")
    elif isinstance(error, app_commands.MissingPermissions):
        e = error_embed("Missing Permissions", "You don't have permission.")
    elif isinstance(error, app_commands.BotMissingPermissions):
        e = error_embed("Bot Missing Permissions", f"I need: `{', '.join(error.missing_permissions)}`")
    else:
        log.exception(f"Slash error: {error}")
        e = error_embed("Unexpected Error", "Something went wrong.")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message(embed=e, ephemeral=True)
    except discord.HTTPException:
        pass


# =============================================================================
# ============================ EVENT HELPERS ==================================
# =============================================================================

async def _handle_dm_feedback(message: discord.Message):
    pending = load_json(FEEDBACK_FILE, {"pending": {}, "log": []})
    if not isinstance(pending, dict):
        return
    p = pending.setdefault("pending", {})
    if str(message.author.id) not in p:
        return
    entry = p[str(message.author.id)]
    pending.setdefault("log", []).append({
        "user_id": message.author.id,
        "ticket_id": entry.get("ticket_id"),
        "rating": message.content.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    del p[str(message.author.id)]
    save_json(FEEDBACK_FILE, pending)
    try:
        await message.channel.send(embed=success_embed("Feedback Received", "Thanks! It's been recorded."))
    except discord.HTTPException:
        pass


async def _handle_key_drop(message: discord.Message):
    def parse(text):
        return [k.strip() for k in text.split() if k.strip()]

    collected = []
    if message.content and message.content.strip():
        collected.extend(parse(message.content))

    file_count = 0
    for att in message.attachments:
        if not att.filename.lower().endswith(".txt"):
            continue
        if att.size > MAX_TXT_FILE_SIZE:
            await message.reply(embed=error_embed("File Too Large", f"`{att.filename}` exceeds 5 MB."))
            continue
        try:
            raw = await att.read()
            text = raw.decode("utf-8")
        except (discord.HTTPException, UnicodeDecodeError):
            await message.reply(embed=error_embed("Bad File", f"Couldn't read `{att.filename}`."))
            continue
        keys = parse(text)
        collected.extend(keys)
        file_count += len(keys)

    if not collected:
        await bot.process_commands(message)
        return

    keys = load_json(KEYS_FILE, [])
    keys.extend(collected)
    save_json(KEYS_FILE, keys)

    e = embed("📥 Keys Detected", f"Found **{len(collected)}** key(s) and added to stock.", COLOR_PRIMARY)
    if file_count:
        e.add_field(name="From File(s)", value=f"`{file_count}` keys", inline=False)
    e.add_field(name="Total Stock", value=str(len(keys)), inline=False)
    e.set_footer(text=f"Added by {message.author}")
    try:
        await message.channel.send(embed=e)
    except discord.HTTPException:
        pass
    await bot.process_commands(message)


async def _handle_wallahi_message(message: discord.Message):
    member = message.author
    g = message.guild.id
    if has_active_invinc(g, member.id):
        await message.channel.send(embed=embed("🛡️ Wallahi Immunity", f"{member.mention} is protected.", COLOR_PRIMARY))
        return
    count = get_wallahi_count(g, member.id)
    uses = len(re.findall(r"(?<!\w)wallahi(?!\w)", message.content, re.IGNORECASE))
    if count >= uses:
        set_wallahi_count(g, member.id, count - uses)
        e = embed("Wallahi Credit Used", f"{member.mention} used **{uses}** credit(s).", COLOR_PRIMARY)
        e.add_field(name="Remaining", value=str(count - uses))
        await message.channel.send(embed=e)
        return
    if count:
        set_wallahi_count(g, member.id, 0)
    duration = timedelta(minutes=15)
    try:
        await member.timeout(duration, reason="Used `wallahi` without credits")
    except discord.Forbidden:
        await message.channel.send(embed=error_embed("Mute Failed", "Check bot permissions."))
        return
    except discord.HTTPException as e:
        await message.channel.send(embed=error_embed("Mute Failed", str(e)))
        return
    e = embed("🔇 Automatic Mute", f"{member.mention} muted for **15 minutes**.", COLOR_WARNING)
    await message.channel.send(embed=e)


async def _track_message_for_credits(message: discord.Message):
    if not isinstance(message.author, discord.Member):
        return
    g = message.guild.id
    state = _load_guild_state(MESSAGE_COUNTS_FILE, g)
    gs = state[str(g)]
    uid = str(message.author.id)
    mc = gs.get(uid, 0)
    if not isinstance(mc, int) or mc < 0:
        mc = 0
    earned = (mc + 1) // MESSAGES_PER_CREDIT
    gs[uid] = (mc + 1) % MESSAGES_PER_CREDIT
    save_json(MESSAGE_COUNTS_FILE, state)
    if earned:
        new_bal = add_credit_balance(g, message.author.id, earned)
        e = embed("💳 Credits Earned", f"You earned **{earned}** credit(s)!", COLOR_GOLD)
        e.add_field(name="Balance", value=str(new_bal))
        try:
            await message.author.send(embed=e)
        except discord.HTTPException:
            pass


async def _run_automod(message: discord.Message) -> bool:
    if not AUTOMOD_ENABLED or not message.guild or message.author.bot:
        return False
    if not isinstance(message.author, discord.Member):
        return False
    if message.author.guild_permissions.manage_messages or message.author.guild_permissions.administrator:
        return False

    content_lower = message.content.lower()

    for w in BAD_WORDS:
        if w and w in content_lower:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} watch your language!", delete_after=5)
            except discord.HTTPException:
                pass
            return True

    if len(message.mentions) > MAX_MENTIONS:
        try:
            await message.delete()
            await message.channel.send(f"{message.author.mention} too many mentions!", delete_after=5)
        except discord.HTTPException:
            pass
        return True

    if len(message.content) > 10:
        caps = sum(1 for c in message.content if c.isupper())
        if caps / len(message.content) * 100 > MAX_CAPS_PERCENT:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} too many caps!", delete_after=5)
            except discord.HTTPException:
                pass
            return True

    key = (message.guild.id, message.author.id)
    dq = bot.spam_tracker[key]
    now = time.time()
    dq.append((now, message.content))
    recent = [t for t, _ in dq if now - t < SPAM_INTERVAL]
    if len(recent) >= SPAM_THRESHOLD:
        try:
            await message.channel.send(f"{message.author.mention} slow down!", delete_after=5)
            await message.author.timeout(
                datetime.now(timezone.utc) + timedelta(seconds=30),
                reason="AutoMod: spamming")
        except discord.HTTPException:
            pass
        dq.clear()
        return True
    return False


async def _remove_afk(message: discord.Message):
    if not message.guild:
        return
    state = _load_guild_state(AFK_FILE, message.guild.id)
    gs = state[str(message.guild.id)]
    uid = str(message.author.id)
    if uid in gs:
        del gs[uid]
        save_json(AFK_FILE, state)
        try:
            await message.channel.send(f"👋 Welcome back {message.author.mention}, removed your AFK.", delete_after=5)
        except discord.HTTPException:
            pass


async def _check_afk(message: discord.Message):
    if not message.guild or not message.mentions:
        return
    state = _load_guild_state(AFK_FILE, message.guild.id)
    gs = state[str(message.guild.id)]
    for mentioned in message.mentions:
        d = gs.get(str(mentioned.id))
        if d:
            ts = datetime.fromisoformat(d["since"])
            e = embed("💤 User is AFK", f"{mentioned.mention} is AFK: **{d.get('reason', 'No reason')}**")
            e.timestamp = ts
            try:
                await message.channel.send(embed=e)
            except discord.HTTPException:
                pass
            break


# =============================================================================
# ============================ PREMIUM SYSTEM =================================
# =============================================================================

async def panel_logic(target):
    e = embed("✨ Premium Panel ✨",
        "Click below to claim your **Premium Key**.\n\n"
        "> 🎁 Each key can be used **once**.\n"
        "> 🔒 You need the required role.\n"
        "> ⏳ Limited stock — restocked regularly.",
        COLOR_PREMIUM)
    e.set_footer(text="Premium System")
    if bot.user:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    view = PremiumView()
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=e, view=view)
    else:
        await target.send(embed=e, view=view)


class PremiumView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Get Premium Key", style=discord.ButtonStyle.success,
                       emoji="🔑", custom_id="premium_get_key")
    async def get_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not has_any_role(member, REQUIRED_ROLES_FOR_PANEL):
            await interaction.response.send_message(
                embed=error_embed("No Access", "You don't have the required role."), ephemeral=True)
            return
        used = load_json(USED_FILE, [])
        if any(e.get("user_id") == member.id for e in used):
            await interaction.response.send_message(
                embed=warning_embed("Already Claimed", "You already claimed a premium key."), ephemeral=True)
            return
        keys = load_json(KEYS_FILE, [])
        if not keys:
            await interaction.response.send_message(
                embed=error_embed("Out of Stock", "No keys available right now."), ephemeral=True)
            return
        key = keys.pop(0)
        save_json(KEYS_FILE, keys)
        used.append({"key": key, "user_id": member.id,
                     "claimed_at": datetime.now(timezone.utc).isoformat()})
        save_json(USED_FILE, used)
        try:
            e = embed("🔑 Your Premium Key", f"```{key}```\nKeep this safe — single use only.", COLOR_SUCCESS)
            await member.send(embed=e)
            await interaction.response.send_message(
                embed=success_embed("Key Sent", "Check your DMs!"), ephemeral=True)
        except discord.Forbidden:
            keys.insert(0, key)
            save_json(KEYS_FILE, keys)
            used = [x for x in used if x.get("key") != key]
            save_json(USED_FILE, used)
            await interaction.response.send_message(
                embed=error_embed("DM Failed", "Enable DMs from server members."), ephemeral=True)


async def restock_logic(target, key_string):
    member = target.author if isinstance(target, commands.Context) else target.user
    if not isinstance(member, discord.Member) or not has_role(member, RESTOCK_ROLE_ID):
        msg = error_embed("Permission Denied", "You can't use this command.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    new_keys = [k.strip() for k in key_string.split(",") if k.strip()]
    if not new_keys:
        msg = error_embed("Invalid Input", "Provide at least one key.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    keys = load_json(KEYS_FILE, [])
    keys.extend(new_keys)
    save_json(KEYS_FILE, keys)
    e = success_embed("Keys Restocked", f"Added **{len(new_keys)}** key(s).")
    e.add_field(name="Total Stock", value=str(len(keys)))
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=e)
    else:
        await target.reply(embed=e)


async def dm_logic(target, user, amount=None, reason=None):
    member = target.author if isinstance(target, commands.Context) else target.user
    amount = amount or DEFAULT_DM_AMOUNT
    reason = reason if reason and reason.strip() else DEFAULT_DM_REASON
    if not isinstance(member, discord.Member) or not has_role(member, DM_ROLE_ID):
        msg = error_embed("Permission Denied", "You can't use this command.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    if amount < 1:
        msg = error_embed("Invalid Amount", "Must be at least 1.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    if user.bot:
        msg = error_embed("Invalid User", "Can't send to bots.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    keys = load_json(KEYS_FILE, [])
    if len(keys) < amount:
        msg = error_embed("Not Enough Stock", f"Requested {amount}, available {len(keys)}.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    sent = keys[:amount]
    save_json(KEYS_FILE, keys[amount:])
    e = embed("🔑 Premium Keys", f"You received **{amount}** key(s).", COLOR_SUCCESS)
    e.add_field(name="Reason", value=reason[:1024], inline=False)
    e.set_footer(text=f"Sent by {member}")
    f = discord.File(BytesIO("\n".join(sent).encode()), filename="premium_keys.txt")
    try:
        await user.send(embed=e, file=f)
    except discord.HTTPException:
        current = load_json(KEYS_FILE, [])
        save_json(KEYS_FILE, sent + current)
        msg = error_embed("DM Failed", f"Couldn't DM {user.mention}.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=msg, ephemeral=True)
        else:
            await target.reply(embed=msg)
        return
    used = load_json(USED_FILE, [])
    used.extend({"key": k, "user_id": user.id} for k in sent)
    save_json(USED_FILE, used)
    e = success_embed("Keys Sent", f"Sent **{amount}** to {user.mention}.")
    e.add_field(name="Remaining", value=str(len(load_json(KEYS_FILE, []))))
    e.add_field(name="Reason", value=reason[:1024])
    e.add_field(name="Sent By", value=member.mention)
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=e, ephemeral=True)
    else:
        await target.reply(embed=e)


async def stock_logic(target):
    keys = load_json(KEYS_FILE, [])
    used = load_json(USED_FILE, [])
    e = embed("📦 Premium Stock", color=COLOR_PRIMARY)
    e.add_field(name="Available", value=str(len(keys)), inline=True)
    e.add_field(name="Claimed", value=str(len(used)), inline=True)
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=e)
    else:
        await target.send(embed=e)


# =============================================================================
# ============================ TICKET SYSTEM ==================================
# =============================================================================

def _tkey(cid): return str(cid)
def _is_ticket_staff(m): return has_role(m, TICKET_STAFF_ROLE_ID)


def build_ticket_embed(data):
    opener = data.get("opener_id")
    claimed = data.get("claimed_by")
    added = data.get("added_users", [])
    priority = data.get("priority", "Normal")
    e = embed("🎫 Support Ticket",
        f"Welcome <@{opener}>!\nDescribe your issue below.\n\n**Staff will assist you shortly.**",
        COLOR_PRIMARY)
    e.add_field(name="Opened by", value=f"<@{opener}>", inline=True)
    e.add_field(name="Claimed by", value=f"<@{claimed}>" if claimed else "`Unclaimed`", inline=True)
    e.add_field(name="Priority", value=priority, inline=True)
    if added:
        e.add_field(name="Added Users", value=" ".join(f"<@{u}>" for u in added), inline=False)
    e.set_footer(text="Use the buttons below to manage this ticket.")
    return e


async def apply_claim_perms(channel, data):
    g = channel.guild
    staff_role = g.get_role(TICKET_STAFF_ROLE_ID)
    opener_id = data.get("opener_id")
    claimed = data.get("claimed_by")
    added = data.get("added_users", [])
    if staff_role:
        await channel.set_permissions(staff_role, view_channel=True,
            send_messages=not bool(claimed), read_message_history=True)
    if opener_id and (op := g.get_member(opener_id)):
        await channel.set_permissions(op, view_channel=True, send_messages=True, read_message_history=True)
    for uid in added:
        if u := g.get_member(uid):
            await channel.set_permissions(u, view_channel=True, send_messages=True, read_message_history=True)
    if claimed:
        if c := g.get_member(claimed):
            await channel.set_permissions(c, view_channel=True, send_messages=True, read_message_history=True)
        if staff_role:
            for mem in staff_role.members:
                if mem.id in {claimed, opener_id, *added}:
                    continue
                try:
                    await channel.set_permissions(mem, view_channel=True, send_messages=False, read_message_history=True)
                except discord.HTTPException:
                    pass
    else:
        if staff_role:
            for mem in staff_role.members:
                if mem.id == opener_id or mem.id in added:
                    continue
                try:
                    await channel.set_permissions(mem, overwrite=None)
                except discord.HTTPException:
                    pass


async def ticket_setup(target):
    member = target.author if isinstance(target, commands.Context) else target.user
    if not isinstance(member, discord.Member) or not has_role(member, TICKET_SETUP_ROLE_ID):
        e = error_embed("Permission Denied", "You can't setup tickets.")
        if isinstance(target, discord.Interaction):
            await target.response.send_message(embed=e, ephemeral=True)
        else:
            await target.reply(embed=e)
        return
    e = embed("🎫 Support Tickets",
        "Click below to open a private ticket.\n\n"
        "> 📩 A private channel will be created.\n"
        "> 🤝 Staff will assist you.\n"
        "> 🔒 Only you and staff can see it.",
        COLOR_PRIMARY)
    e.set_footer(text="Click to open a ticket")
    view = TicketOpenView()
    if isinstance(target, discord.Interaction):
        await target.response.send_message(embed=e, view=view)
    else:
        await target.send(embed=e, view=view)


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary,
                       emoji="🎫", custom_id="ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, _btn):
        g = interaction.guild
        member = interaction.user
        if not g:
            await interaction.response.send_message(embed=error_embed("Server Only", "Open tickets in a server."), ephemeral=True)
            return
        tickets = load_json(TICKETS_FILE, {})
        for cid, d in tickets.items():
            if d.get("opener_id") == member.id and d.get("status") == "open":
                await interaction.response.send_message(
                    embed=warning_embed("Already Open", f"You have an open ticket: <#{cid}>"), ephemeral=True)
                return
        cat = g.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(cat, discord.CategoryChannel):
            cat = None
        ow = {
            g.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        staff = g.get_role(TICKET_STAFF_ROLE_ID)
        if staff:
            ow[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        try:
            ch = await g.create_text_channel(
                name=f"ticket-{member.name}".lower()[:90],
                overwrites=ow, category=cat,
                topic=f"Ticket by {member} ({member.id})",
            )
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("Failed", "I can't create channels."), ephemeral=True)
            return
        tickets[_tkey(ch.id)] = {
            "opener_id": member.id, "claimed_by": None, "added_users": [],
            "status": "open", "priority": "Normal",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        save_json(TICKETS_FILE, tickets)
        e = build_ticket_embed(tickets[_tkey(ch.id)])
        try:
            await ch.send(content=f"{member.mention} {staff.mention if staff else ''}", embed=e, view=TicketControlView())
        except discord.HTTPException:
            await ch.send(embed=e, view=TicketControlView())
        await interaction.response.send_message(
            embed=success_embed("Ticket Created", f"Your ticket: {ch.mention}"), ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    async def _refresh(self, interaction):
        tickets = load_json(TICKETS_FILE, {})
        d = tickets.get(_tkey(interaction.channel.id))
        if not d: return None
        try:
            await interaction.message.edit(embed=build_ticket_embed(d), view=self)
        except (discord.HTTPException, AttributeError):
            pass
        return d

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, _b):
        mem = interaction.user
        if not isinstance(mem, discord.Member) or not _is_ticket_staff(mem):
            await interaction.response.send_message(embed=error_embed("No Access", "Staff only."), ephemeral=True)
            return
        tickets = load_json(TICKETS_FILE, {})
        k = _tkey(interaction.channel.id)
        d = tickets.get(k)
        if not d:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", ""), ephemeral=True)
            return
        if d.get("claimed_by"):
            await interaction.response.send_message(embed=warning_embed("Already Claimed", f"By <@{d['claimed_by']}>"), ephemeral=True)
            return
        d["claimed_by"] = mem.id
        tickets[k] = d
        save_json(TICKETS_FILE, tickets)
        await apply_claim_perms(interaction.channel, d)
        await interaction.response.send_message(embed=success_embed("Claimed", f"{mem.mention} claimed this ticket."))
        await self._refresh(interaction)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, emoji="↩️", custom_id="ticket_unclaim")
    async def unclaim(self, interaction: discord.Interaction, _b):
        mem = interaction.user
        if not isinstance(mem, discord.Member) or not _is_ticket_staff(mem):
            await interaction.response.send_message(embed=error_embed("No Access", "Staff only."), ephemeral=True)
            return
        tickets = load_json(TICKETS_FILE, {})
        k = _tkey(interaction.channel.id)
        d = tickets.get(k)
        if not d or not d.get("claimed_by"):
            await interaction.response.send_message(embed=warning_embed("Not Claimed", ""), ephemeral=True)
            return
        if d["claimed_by"] != mem.id:
            await interaction.response.send_message(embed=error_embed("Not Yours", "Only the claimer can unclaim."), ephemeral=True)
            return
        d["claimed_by"] = None
        tickets[k] = d
        save_json(TICKETS_FILE, tickets)
        await apply_claim_perms(interaction.channel, d)
        await interaction.response.send_message(embed=success_embed("Unclaimed", f"{mem.mention} unclaimed."))
        await self._refresh(interaction)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.primary, emoji="➕", custom_id="ticket_add")
    async def add_user(self, interaction: discord.Interaction, _b):
        tickets = load_json(TICKETS_FILE, {})
        d = tickets.get(_tkey(interaction.channel.id))
        if not d:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", ""), ephemeral=True)
            return
        mem = interaction.user
        is_staff = isinstance(mem, discord.Member) and _is_ticket_staff(mem)
        is_opener = mem.id == d["opener_id"]
        is_claimer = mem.id == d.get("claimed_by")
        if d.get("claimed_by") and not (is_claimer or is_opener):
            await interaction.response.send_message(embed=error_embed("No Access", "Claimer or opener only."), ephemeral=True)
            return
        if not (is_staff or is_opener or is_claimer):
            await interaction.response.send_message(embed=error_embed("No Access", ""), ephemeral=True)
            return
        await interaction.response.send_modal(AddUserModal())

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.primary, emoji="➖", custom_id="ticket_remove")
    async def remove_user(self, interaction: discord.Interaction, _b):
        if not isinstance(interaction.user, discord.Member) or not _is_ticket_staff(interaction.user):
            await interaction.response.send_message(embed=error_embed("No Access", "Staff only."), ephemeral=True)
            return
        await interaction.response.send_modal(RemoveUserModal())

    @discord.ui.button(label="Priority", style=discord.ButtonStyle.primary, emoji="⚡", custom_id="ticket_priority")
    async def priority(self, interaction: discord.Interaction, _b):
        if not isinstance(interaction.user, discord.Member) or not _is_ticket_staff(interaction.user):
            await interaction.response.send_message(embed=error_embed("No Access", "Staff only."), ephemeral=True)
            return
        await interaction.response.send_message(view=PriorityView(), ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, _b):
        tickets = load_json(TICKETS_FILE, {})
        k = _tkey(interaction.channel.id)
        d = tickets.get(k)
        if not d:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", ""), ephemeral=True)
            return
        mem = interaction.user
        is_staff = isinstance(mem, discord.Member) and _is_ticket_staff(mem)
        is_opener = mem.id == d["opener_id"]
        is_claimer = mem.id == d.get("claimed_by")
        if not (is_staff or is_opener or is_claimer):
            await interaction.response.send_message(embed=error_embed("No Access", ""), ephemeral=True)
            return
        await interaction.response.send_message(embed=warning_embed("Closing", "Ticket will close in 5 seconds..."))
        opener_id = d["opener_id"]
        ch = interaction.channel

        async def _finish():
            await asyncio.sleep(5)
            try:
                lines = []
                async for msg in ch.history(limit=1000, oldest_first=True):
                    lines.append(f"[{msg.created_at.isoformat()}] {msg.author}: {msg.content}")
                path = os.path.join(TRANSCRIPT_DIR, f"ticket-{ch.id}.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
            except Exception as e:
                log.error(f"Transcript failed: {e}")
            tks = load_json(TICKETS_FILE, {})
            tks.pop(k, None)
            save_json(TICKETS_FILE, tks)
            fb = load_json(FEEDBACK_FILE, {"pending": {}, "log": []})
            if not isinstance(fb, dict):
                fb = {"pending": {}, "log": []}
            fb.setdefault("pending", {})[str(opener_id)] = {"ticket_id": k}
            fb.setdefault("log", [])
            save_json(FEEDBACK_FILE, fb)
            try:
                op = await bot.fetch_user(opener_id)
                e = embed("📝 Ticket Feedback",
                    "Your ticket closed.\nReply to this DM with a rating (1-5) or comments.",
                    COLOR_GOLD)
                await op.send(embed=e)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            try:
                await ch.delete(reason="Ticket closed")
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        asyncio.create_task(_finish())


class PriorityView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60)

    async def _set(self, interaction, level):
        tickets = load_json(TICKETS_FILE, {})
        k = _tkey(interaction.channel.id)
        d = tickets.get(k)
        if not d:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", ""), ephemeral=True)
            return
        d["priority"] = level
        tickets[k] = d
        save_json(TICKETS_FILE, tickets)
        await interaction.response.send_message(embed=success_embed("Priority Set", f"Set to **{level}**"), ephemeral=True)
        try:
            async for msg in interaction.channel.history(limit=20):
                if msg.author == bot.user and msg.embeds and msg.components:
                    await msg.edit(embed=build_ticket_embed(d), view=TicketControlView())
                    break
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Low", style=discord.ButtonStyle.secondary)
    async def low(self, i, _b): await self._set(i, "Low")
    @discord.ui.button(label="Normal", style=discord.ButtonStyle.primary)
    async def normal(self, i, _b): await self._set(i, "Normal")
    @discord.ui.button(label="High", style=discord.ButtonStyle.danger)
    async def high(self, i, _b): await self._set(i, "High")
    @discord.ui.button(label="Urgent", style=discord.ButtonStyle.danger, emoji="🚨")
    async def urgent(self, i, _b): await self._set(i, "Urgent")


class AddUserModal(discord.ui.Modal, title="Add User to Ticket"):
    uid = discord.ui.TextInput(label="User ID", placeholder="Paste user ID", required=True, max_length=25)

    async def on_submit(self, interaction: discord.Interaction):
        tickets = load_json(TICKETS_FILE, {})
        k = _tkey(interaction.channel.id)
        d = tickets.get(k)
        if not d:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", ""), ephemeral=True)
            return
        mem = interaction.user
        is_opener = mem.id == d.get("opener_id")
        is_claimer = mem.id == d.get("claimed_by")
        if d.get("claimed_by") and not (is_claimer or is_opener):
            await interaction.response.send_message(embed=error_embed("No Access", "Claimer or opener only."), ephemeral=True)
            return
        try:
            uid = int(str(self.uid.value).strip())
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Invalid ID", ""), ephemeral=True)
            return
        target = interaction.guild.get_member(uid)
        if target is None:
            try:
                target = await bot.fetch_user(uid)
            except (discord.NotFound, discord.HTTPException):
                await interaction.response.send_message(embed=error_embed("Not Found", ""), ephemeral=True)
                return
        try:
            await interaction.channel.set_permissions(target, view_channel=True, send_messages=True, read_message_history=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("Failed", "Can't modify channel."), ephemeral=True)
            return
        added = d.get("added_users", [])
        if uid not in added:
            added.append(uid)
        d["added_users"] = added
        tickets[k] = d
        save_json(TICKETS_FILE, tickets)
        await interaction.response.send_message(embed=success_embed("Added", f"Added <@{uid}>"))
        try:
            async for msg in interaction.channel.history(limit=20):
                if msg.author == bot.user and msg.embeds and msg.components:
                    await msg.edit(embed=build_ticket_embed(d), view=TicketControlView())
                    break
        except discord.HTTPException:
            pass


class RemoveUserModal(discord.ui.Modal, title="Remove User from Ticket"):
    uid = discord.ui.TextInput(label="User ID", placeholder="Paste user ID", required=True, max_length=25)

    async def on_submit(self, interaction: discord.Interaction):
        tickets = load_json(TICKETS_FILE, {})
        k = _tkey(interaction.channel.id)
        d = tickets.get(k)
        if not d:
            await interaction.response.send_message(embed=error_embed("Not a Ticket", ""), ephemeral=True)
            return
        try:
            uid = int(str(self.uid.value).strip())
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Invalid ID", ""), ephemeral=True)
            return
        added = d.get("added_users", [])
        if uid not in added:
            await interaction.response.send_message(embed=warning_embed("Not Added", ""), ephemeral=True)
            return
        added.remove(uid)
        d["added_users"] = added
        tickets[k] = d
        save_json(TICKETS_FILE, tickets)
        target = interaction.guild.get_member(uid)
        if target is None:
            try:
                target = await bot.fetch_user(uid)
            except Exception:
                target = None
        if target:
            try:
                await interaction.channel.set_permissions(target, overwrite=None)
            except discord.Forbidden:
                pass
        await interaction.response.send_message(embed=success_embed("Removed", f"Removed <@{uid}>"))
        try:
            async for msg in interaction.channel.history(limit=20):
                if msg.author == bot.user and msg.embeds and msg.components:
                    await msg.edit(embed=build_ticket_embed(d), view=TicketControlView())
                    break
        except discord.HTTPException:
            pass


# =============================================================================
# =========================== MODERATION COMMANDS =============================
# =============================================================================

async def _check_mod(ctx):
    if is_mod(ctx.author):
        return True
    await ctx.reply(embed=error_embed("Permission Denied", "Moderator role required."))
    return False


async def _send_mod_dm(member, action, mod, reason, length):
    e = embed(f"Server Moderation: {action}",
        f"You were {action.lower()} in **{member.guild.name}**.", COLOR_WARNING)
    e.add_field(name="Reason", value=(reason or "None")[:1024])
    e.add_field(name="Length", value=length[:1024])
    e.add_field(name="Moderator", value=str(mod)[:1024])
    try:
        await member.send(embed=e)
        return True
    except discord.HTTPException:
        return False


async def _reply_result(ctx, title, desc, reason, dm_sent, color=COLOR_SUCCESS):
    e = embed(title, desc, color)
    e.add_field(name="Reason", value=(reason or "None")[:1024])
    e.add_field(name="DM", value="Sent" if dm_sent else "Failed (DMs closed)")
    await ctx.reply(embed=e)


@bot.command(name="warn")
@commands.guild_only()
async def warn_cmd(ctx, member: discord.Member, *, reason="No reason"):
    if not await _check_mod(ctx): return
    warns = load_json(WARNINGS_FILE, [])
    warns.append({"guild_id": ctx.guild.id, "user_id": member.id,
                  "moderator_id": ctx.author.id, "reason": reason,
                  "created_at": datetime.now(timezone.utc).isoformat()})
    save_json(WARNINGS_FILE, warns)
    count = sum(1 for w in warns if w.get("guild_id") == ctx.guild.id and w.get("user_id") == member.id)
    dm = await _send_mod_dm(member, "Warned", ctx.author, reason, "N/A")
    e = embed("⚠️ User Warned", f"{member.mention} has **{count}** warning(s).", COLOR_WARNING)
    e.add_field(name="Reason", value=reason[:1024])
    e.add_field(name="DM", value="Sent" if dm else "Failed")
    await ctx.reply(embed=e)


@bot.command(name="warnings")
@commands.guild_only()
async def warnings_cmd(ctx, member: discord.Member):
    if not await _check_mod(ctx): return
    warns = [w for w in load_json(WARNINGS_FILE, [])
             if w.get("guild_id") == ctx.guild.id and w.get("user_id") == member.id]
    if not warns:
        await ctx.reply(embed=embed("No Warnings", f"{member.mention} has no warnings."))
        return
    e = embed(f"Warnings for {member}", color=COLOR_WARNING)
    for i, w in enumerate(warns[:25], 1):
        e.add_field(name=f"#{i} — <t:{int(datetime.fromisoformat(w['created_at']).timestamp())}:R>",
                    value=f"By <@{w['moderator_id']}>\n{w['reason'][:200]}", inline=False)
    await ctx.reply(embed=e)


@bot.command(name="mute")
@commands.guild_only()
async def mute_cmd(ctx, member: discord.Member, duration: str, *, reason="No reason"):
    if not await _check_mod(ctx): return
    try:
        t = parse_duration(duration)
    except ValueError as e:
        await ctx.reply(embed=error_embed("Bad Duration", str(e)))
        return
    try:
        await member.timeout(t, reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=error_embed("Failed", "Check bot permissions."))
        return
    dm = await _send_mod_dm(member, "Muted", ctx.author, reason, duration)
    await _reply_result(ctx, "🔇 User Muted", f"{member.mention} muted for **{duration}**.", reason, dm)


@bot.command(name="unmute")
@commands.guild_only()
async def unmute_cmd(ctx, member: discord.Member, *, reason="No reason"):
    if not await _check_mod(ctx): return
    try:
        await member.timeout(None, reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=error_embed("Failed", "Check permissions."))
        return
    dm = await _send_mod_dm(member, "Unmuted", ctx.author, reason, "Removed")
    await _reply_result(ctx, "🔊 User Unmuted", f"{member.mention} unmuted.", reason, dm)


@bot.command(name="kick")
@commands.guild_only()
async def kick_cmd(ctx, member: discord.Member, *, reason="No reason"):
    if not await _check_mod(ctx): return
    try:
        await member.kick(reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=error_embed("Failed", "Check permissions."))
        return
    dm = await _send_mod_dm(member, "Kicked", ctx.author, reason, "N/A")
    await _reply_result(ctx, "👢 User Kicked", f"{member.mention} kicked.", reason, dm)


@bot.command(name="ban")
@commands.guild_only()
async def ban_cmd(ctx, member: discord.Member, *, reason="No reason"):
    if not await _check_mod(ctx): return
    try:
        await member.ban(reason=f"{ctx.author}: {reason}"[:512])
    except discord.Forbidden:
        await ctx.reply(embed=error_embed("Failed", "Check permissions."))
        return
    dm = await _send_mod_dm(member, "Banned", ctx.author, reason, "Permanent")
    await _reply_result(ctx, "🔨 User Banned", f"{member.mention} banned.", reason, dm)


@bot.command(name="purge")
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
async def purge_cmd(ctx, amount: int = 10, member: discord.Member = None):
    if amount < 1 or amount > 1000:
        await ctx.reply(embed=error_embed("Invalid Amount", "1-1000 only."))
        return
    def check(msg):
        return member is None or msg.author == member
    deleted = await ctx.channel.purge(limit=amount + 1, check=check)
    await ctx.send(embed=success_embed("Purged", f"Deleted **{len(deleted) - 1}** messages."), delete_after=5)


@bot.command(name="wallahis")
@commands.guild_only()
async def wallahis_cmd(ctx, member: discord.Member, amount: int):
    if not await _check_mod(ctx): return
    if amount < 1:
        await ctx.reply(embed=error_embed("Invalid Amount", "Must be >= 1."))
        return
    total = get_wallahi_count(ctx.guild.id, member.id) + amount
    set_wallahi_count(ctx.guild.id, member.id, total)
    e = success_embed("Wallahi Added", f"Added **{amount}** to {member.mention}.")
    e.add_field(name="Balance", value=str(total))
    await ctx.reply(embed=e)


@bot.command(name="removew")
@commands.guild_only()
async def removew_cmd(ctx, member: discord.Member, amount: int):
    if not await _check_mod(ctx): return
    if amount < 1:
        await ctx.reply(embed=error_embed("Invalid", ">= 1"))
        return
    before = get_wallahi_count(ctx.guild.id, member.id)
    new = add_wallahi_credits(ctx.guild.id, member.id, -amount)
    e = success_embed("Removed", f"Removed **{before - new}** from {member.mention}.")
    e.add_field(name="Balance", value=str(new))
    await ctx.reply(embed=e)


@bot.command(name="removec")
@commands.guild_only()
async def removec_cmd(ctx, member: discord.Member, amount: int):
    if not await _check_mod(ctx): return
    if amount < 1:
        await ctx.reply(embed=error_embed("Invalid", ">= 1"))
        return
    before = get_credit_balance(ctx.guild.id, member.id)
    new = add_credit_balance(ctx.guild.id, member.id, -amount)
    e = success_embed("Removed", f"Removed **{before - new}** from {member.mention}.")
    e.add_field(name="Balance", value=str(new))
    await ctx.reply(embed=e)


@bot.command(name="gcredits")
@commands.guild_only()
async def gcredits_cmd(ctx, member: discord.Member, amount: int):
    if not await _check_mod(ctx): return
    if amount < 1:
        await ctx.reply(embed=error_embed("Invalid", ">= 1"))
        return
    new = add_credit_balance(ctx.guild.id, member.id, amount)
    await ctx.reply(embed=success_embed("Granted", f"Gave **{amount}** to {member.mention}. New: **{new}**"))


@bot.command(name="invinc")
@commands.guild_only()
async def invinc_cmd(ctx, member: discord.Member, length: str, *, reason: str):
    if not await _check_mod(ctx): return
    try:
        d = parse_duration(length)
    except ValueError as e:
        await ctx.reply(embed=error_embed("Bad Duration", str(e)))
        return
    expires = datetime.now(timezone.utc) + d
    state = _load_guild_state(INVINC_FILE, ctx.guild.id)
    state[str(ctx.guild.id)][str(member.id)] = expires.isoformat()
    save_json(INVINC_FILE, state)
    e = success_embed("🛡️ Immunity Granted", f"{member.mention} protected for **{length}**.")
    e.add_field(name="Reason", value=reason[:1024])
    e.add_field(name="Expires", value=discord.utils.format_dt(expires, "R"))
    await ctx.reply(embed=e)


# =============================================================================
# ============================ ECONOMY SYSTEM =================================
# =============================================================================

def _get_cd(guild_id, user_id, key):
    state = load_json(COOLDOWNS_FILE, {})
    return state.get(f"{guild_id}:{user_id}:{key}")


def _set_cd(guild_id, user_id, key, iso):
    state = load_json(COOLDOWNS_FILE, {})
    state[f"{guild_id}:{user_id}:{key}"] = iso
    save_json(COOLDOWNS_FILE, state)


@bot.command(name="credits", aliases=["bal", "balance"])
@commands.guild_only()
async def credits_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    bal = get_credit_balance(ctx.guild.id, target.id)
    bal_text = "∞ (Jew Mode)" if is_jew_mode(target) else f"{bal:,}"
    e = embed(f"💳 {target.display_name}'s Balance", color=COLOR_GOLD)
    e.add_field(name="Credits", value=bal_text)
    e.add_field(name="Wallahis", value=str(get_wallahi_count(ctx.guild.id, target.id)))
    e.set_thumbnail(url=target.display_avatar.url)
    await ctx.reply(embed=e)


@bot.command(name="daily")
@commands.guild_only()
async def daily_cmd(ctx):
    g, u = ctx.guild.id, ctx.author.id
    last = _get_cd(g, u, "daily")
    now = datetime.now(timezone.utc)
    if last:
        last_dt = datetime.fromisoformat(last)
        if now - last_dt < timedelta(hours=24):
            rem = timedelta(hours=24) - (now - last_dt)
            h, r = divmod(int(rem.total_seconds()), 3600)
            mi = r // 60
            await ctx.reply(embed=warning_embed("Already Claimed", f"Come back in **{h}h {mi}m**."))
            return
    new = add_credit_balance(g, u, DAILY_REWARD)
    _set_cd(g, u, "daily", now.isoformat())
    e = success_embed("💰 Daily Reward", f"You received **{DAILY_REWARD}** credits!")
    e.add_field(name="New Balance", value=str(new))
    await ctx.reply(embed=e)


@bot.command(name="rob")
@commands.guild_only()
async def rob_cmd(ctx, member: discord.Member):
    if not is_jew_mode(ctx.author):
        await ctx.reply(embed=error_embed("Access Denied", "Only **Jew Mode** users can rob."))
        return
    if member.id == ctx.author.id or member.bot:
        await ctx.reply(embed=error_embed("Invalid Target", ""))
        return
    g, u = ctx.guild.id, ctx.author.id
    last = _get_cd(g, u, "rob")
    now = datetime.now(timezone.utc)
    if last:
        last_dt = datetime.fromisoformat(last)
        if now - last_dt < timedelta(seconds=ROB_COOLDOWN):
            rem = timedelta(seconds=ROB_COOLDOWN) - (now - last_dt)
            await ctx.reply(embed=warning_embed("Cooldown", f"Wait **{int(rem.total_seconds())}s**."))
            return
    victim_bal = get_credit_balance(g, member.id)
    if victim_bal < 100:
        await ctx.reply(embed=warning_embed("Too Poor", "Target has less than 100 credits."))
        return
    _set_cd(g, u, "rob", now.isoformat())
    if random.random() < ROB_SUCCESS_RATE:
        stolen = min(random.randint(50, ROB_MAX_STEAL), victim_bal // 2)
        add_credit_balance(g, member.id, -stolen)
        add_credit_balance(g, u, stolen)
        e = success_embed("🦹 Rob Successful", f"You robbed **{stolen}** credits from {member.mention}!")
    else:
        fine = min(random.randint(20, 150), get_credit_balance(g, u))
        add_credit_balance(g, u, -fine)
        e = error_embed("🚨 Rob Failed", f"You got caught and paid a **{fine}** credit fine!")
    await ctx.reply(embed=e)


@bot.command(name="pay")
@commands.guild_only()
async def pay_cmd(ctx, member: discord.Member, amount: int):
    if member.id == ctx.author.id or member.bot:
        await ctx.reply(embed=error_embed("Invalid Target", ""))
        return
    if amount < 1:
        await ctx.reply(embed=error_embed("Invalid Amount", ""))
        return
    g = ctx.guild.id
    bal = get_credit_balance(g, ctx.author.id)
    if not is_jew_mode(ctx.author) and bal < amount:
        await ctx.reply(embed=error_embed("Not Enough", f"You have **{bal}**."))
        return
    if not is_jew_mode(ctx.author):
        add_credit_balance(g, ctx.author.id, -amount)
    add_credit_balance(g, member.id, amount)
    await ctx.reply(embed=success_embed("💸 Payment Sent", f"Sent **{amount}** to {member.mention}."))


@bot.command(name="gamble")
@commands.guild_only()
async def gamble_cmd(ctx, amount: int):
    if amount < 1:
        await ctx.reply(embed=error_embed("Invalid Amount", ""))
        return
    g = ctx.guild.id
    bal = get_credit_balance(g, ctx.author.id)
    if not is_jew_mode(ctx.author) and bal < amount:
        await ctx.reply(embed=error_embed("Not Enough", ""))
        return
    if random.random() < 0.45:
        if not is_jew_mode(ctx.author):
            add_credit_balance(g, ctx.author.id, amount)
        else:
            add_credit_balance(g, ctx.author.id, amount * 2)
        e = success_embed("🎰 You Won!", f"Doubled your bet! **+{amount}**")
    else:
        if not is_jew_mode(ctx.author):
            add_credit_balance(g, ctx.author.id, -amount)
        e = error_embed("🎰 You Lost", f"Lost **{amount}** credits.")
    await ctx.reply(embed=e)


@bot.command(name="leaderboard", aliases=["lb", "top"])
@commands.guild_only()
async def leaderboard_cmd(ctx):
    state = _load_guild_state(CREDITS_FILE, ctx.guild.id)
    gs = state[str(ctx.guild.id)]
    sorted_users = sorted(((int(k), v) for k, v in gs.items() if isinstance(v, int)), key=lambda x: x[1], reverse=True)[:10]
    e = embed("🏆 Credit Leaderboard", color=COLOR_GOLD)
    for i, (uid, bal) in enumerate(sorted_users, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"#{i}"
        e.add_field(name=f"{medal} <@{uid}>", value=f"**{bal:,}** credits", inline=False)
    if not sorted_users:
        e.description = "No data yet."
    await ctx.reply(embed=e)


@bot.command(name="buy")
@commands.guild_only()
async def buy_cmd(ctx):
    bal = get_credit_balance(ctx.guild.id, ctx.author.id)
    e = embed("🛒 Shop",
        "• **Premium role:** 150 credits\n• **Wallahis:** 1 credit each",
        COLOR_GOLD)
    e.add_field(name="Your Credits", value="∞" if is_jew_mode(ctx.author) else f"{bal:,}")
    view = BuyMenuView(ctx.guild, ctx.author)
    view.message = await ctx.reply(embed=e, view=view)


@bot.command(name="jew")
@commands.guild_only()
async def jew_cmd(ctx, member: discord.Member):
    if not await _check_mod(ctx): return
    role = ctx.guild.get_role(JEW_MODE_ROLE_ID)
    if not role:
        await ctx.reply(embed=error_embed("No Role", "Jew Mode role missing."))
        return
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.reply(embed=success_embed("Removed", f"Removed Jew Mode from {member.mention}."))
    else:
        await member.add_roles(role)
        await ctx.reply(embed=success_embed("Granted", f"Gave {member.mention} Jew Mode (unlimited credits)."))


class BuyWallahiModal(discord.ui.Modal, title="Buy Wallahis"):
    amount = discord.ui.TextInput(label="How many?", placeholder="Amount", min_length=1, max_length=9)

    def __init__(self, guild, member):
        super().__init__()
        self.guild = guild
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        if not str(self.amount.value).isdecimal():
            await interaction.response.send_message(embed=error_embed("Invalid", "Whole number."), ephemeral=True)
            return
        amt = int(str(self.amount.value))
        if amt < 1:
            await interaction.response.send_message(embed=error_embed("Invalid", ">= 1"), ephemeral=True)
            return
        bal = get_credit_balance(self.guild.id, self.member.id)
        unlimited = is_jew_mode(self.member)
        if not unlimited and bal < amt:
            await interaction.response.send_message(embed=error_embed("Not Enough", f"Need **{amt}**, have **{bal}**."), ephemeral=True)
            return
        if not unlimited:
            add_credit_balance(self.guild.id, self.member.id, -amt)
        total = get_wallahi_count(self.guild.id, self.member.id) + amt
        set_wallahi_count(self.guild.id, self.member.id, total)
        await interaction.response.send_message(
            embed=success_embed("Purchased", f"Bought **{amt}** Wallahis. Total: **{total}**"), ephemeral=True)


class BuyMenuView(discord.ui.View):
    def __init__(self, guild, member):
        super().__init__(timeout=180)
        self.guild = guild
        self.member = member
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id == self.member.id:
            return True
        await interaction.response.send_message(embed=error_embed("Not Yours", ""), ephemeral=True)
        return False

    @discord.ui.button(label="Buy Premium (150)", style=discord.ButtonStyle.primary)
    async def buy_premium(self, interaction, _b):
        bal = get_credit_balance(self.guild.id, self.member.id)
        unlimited = is_jew_mode(self.member)
        if not unlimited and bal < 150:
            await interaction.response.send_message(embed=error_embed("Not Enough", ""), ephemeral=True)
            return
        role = self.guild.get_role(PREMIUM_ROLE_ID)
        if not role:
            await interaction.response.send_message(embed=error_embed("Unavailable", ""), ephemeral=True)
            return
        if role in self.member.roles:
            await interaction.response.send_message(embed=warning_embed("Already Owned", ""), ephemeral=True)
            return
        try:
            await self.member.add_roles(role, reason="Premium purchase")
        except discord.HTTPException:
            await interaction.response.send_message(embed=error_embed("Failed", ""), ephemeral=True)
            return
        if not unlimited:
            add_credit_balance(self.guild.id, self.member.id, -150)
        await interaction.response.send_message(embed=success_embed("Purchased", "You got Premium!"), ephemeral=True)

    @discord.ui.button(label="Buy Wallahis", style=discord.ButtonStyle.success)
    async def buy_wallahis(self, interaction, _b):
        await interaction.response.send_modal(BuyWallahiModal(self.guild, self.member))


# =============================================================================
# ============================ GIVEAWAY SYSTEM ================================
# =============================================================================

class GiveawayView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = gid

    @discord.ui.button(label="Enter", style=discord.ButtonStyle.success,
                       emoji="🎉", custom_id="giveaway_enter")
    async def enter(self, interaction: discord.Interaction, _b):
        data = load_json(GIVEAWAYS_FILE, {})
        g = data.get(self.gid)
        if not g or g.get("ended"):
            await interaction.response.send_message(embed=error_embed("Ended", ""), ephemeral=True)
            return
        entries = g.setdefault("entries", [])
        if interaction.user.id in entries:
            entries.remove(interaction.user.id)
            save_json(GIVEAWAYS_FILE, data)
            await interaction.response.send_message(embed=warning_embed("Removed", "You left the giveaway."), ephemeral=True)
        else:
            entries.append(interaction.user.id)
            save_json(GIVEAWAYS_FILE, data)
            await interaction.response.send_message(embed=success_embed("Entered!", "Good luck!"), ephemeral=True)


@bot.command(name="gstart")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def gstart_cmd(ctx, duration: str, winners: int, *, prize: str):
    try:
        amt = int(duration[:-1])
        unit = duration[-1].lower()
        secs = amt * {"s":1, "m":60, "h":3600, "d":86400}[unit]
    except Exception:
        await ctx.reply(embed=error_embed("Bad Duration", "Use `10m`, `1h`, `1d`."))
        return
    if winners < 1:
        await ctx.reply(embed=error_embed("Invalid", "Winners >= 1"))
        return
    ends_at = datetime.now(timezone.utc) + timedelta(seconds=secs)
    e = embed("🎉 Giveaway!", f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** {discord.utils.format_dt(ends_at, 'R')}", COLOR_GOLD)
    e.set_footer(text=f"Hosted by {ctx.author}")
    msg = await ctx.send(embed=e)
    gid = f"{ctx.channel.id}:{msg.id}"
    view = GiveawayView(gid)
    await msg.edit(view=view)
    data = load_json(GIVEAWAYS_FILE, {})
    data[gid] = {
        "channel_id": ctx.channel.id, "message_id": msg.id,
        "prize": prize, "winners": winners, "ends_at": ends_at.isoformat(),
        "entries": [], "host_id": ctx.author.id, "ended": False,
    }
    save_json(GIVEAWAYS_FILE, data)


# =============================================================================
# ========================== REACTION ROLES ===================================
# =============================================================================

class RRPersistentView(discord.ui.View):
    def __init__(self, guild_id: int, message_id: int, roles: list):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.message_id = message_id
        for entry in roles:
            emoji = entry.get("emoji")
            rid = entry["role_id"]
            label = entry.get("label") or f"Role {rid}"
            btn = discord.ui.Button(
                label=label[:80],
                emoji=emoji if emoji else None,
                style=discord.ButtonStyle.secondary,
                custom_id=f"rr:{guild_id}:{message_id}:{rid}",
            )
            btn.callback = self._make_cb(rid)
            self.add_item(btn)

    def _make_cb(self, role_id: int):
        async def cb(interaction: discord.Interaction):
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message(embed=error_embed("Role Missing", ""), ephemeral=True)
                return
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(embed=success_embed("Removed", f"Removed {role.mention}"), ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(embed=success_embed("Added", f"Added {role.mention}"), ephemeral=True)
        return cb


@bot.command(name="reactionrole", aliases=["rr"])
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def rr_cmd(ctx, message_id: int, role: discord.Role, emoji: str = "✅", *, label: str = None):
    try:
        msg = await ctx.channel.fetch_message(message_id)
    except discord.HTTPException:
        await ctx.reply(embed=error_embed("Message Not Found", ""))
        return
    data = load_json(RR_FILE, {})
    entry = data.setdefault(str(message_id), {
        "guild_id": ctx.guild.id, "channel_id": ctx.channel.id, "roles": []
    })
    entry["roles"].append({"role_id": role.id, "emoji": emoji, "label": label or role.name})
    save_json(RR_FILE, data)
    view = RRPersistentView(ctx.guild.id, message_id, entry["roles"])
    await msg.edit(view=view)
    await ctx.reply(embed=success_embed("Reaction Role Added", f"Added {role.mention} with {emoji}"))


# =============================================================================
# ============================ UTILITY COMMANDS ===============================
# =============================================================================

@bot.command(name="ping")
async def ping_cmd(ctx):
    latency = round(bot.latency * 1000)
    e = embed("🏓 Pong!", color=COLOR_SUCCESS)
    e.add_field(name="Latency", value=f"`{latency}ms`")
    await ctx.reply(embed=e)


@bot.command(name="help")
async def help_cmd(ctx, *, cmd=None):
    if cmd:
        c = bot.get_command(cmd)
        if not c:
            await ctx.reply(embed=error_embed("Not Found", f"No command `{cmd}`."))
            return
        e = embed(f"📖 {c.name}", c.help or "No description.", COLOR_PRIMARY)
        e.add_field(name="Usage", value=f"`{ctx.prefix}{c.name} {c.signature}`")
        if c.aliases:
            e.add_field(name="Aliases", value=", ".join(c.aliases))
        await ctx.reply(embed=e)
        return
    e = embed("📖 Help", "Use `/` slash commands or prefixes: `!`, `a!`", COLOR_PRIMARY)
    cats = {}
    for c in bot.commands:
        if c.hidden:
            continue
        cog = c.cog_name or "Other"
        cats.setdefault(cog, []).append(c.name)
    for cat, cmds in cats.items():
        e.add_field(name=f"**{cat}**", value=", ".join(f"`{c}`" for c in sorted(cmds))[:1024], inline=False)
    await ctx.reply(embed=e)


@bot.command(name="userinfo", aliases=["ui", "whois"])
@commands.guild_only()
async def userinfo_cmd(ctx, member: discord.Member = None):
    t = member or ctx.author
    e = embed(f"👤 {t}", color=t.color.value if t.color else COLOR_PRIMARY)
    e.set_thumbnail(url=t.display_avatar.url)
    e.add_field(name="ID", value=str(t.id), inline=True)
    e.add_field(name="Bot", value=str(t.bot), inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(t.created_at, "R"), inline=True)
    if t.joined_at:
        e.add_field(name="Joined", value=discord.utils.format_dt(t.joined_at, "R"), inline=True)
    roles = [r.mention for r in t.roles[1:]][:20]
    e.add_field(name="Roles", value=" ".join(roles) or "None", inline=False)
    await ctx.reply(embed=e)


@bot.command(name="serverinfo", aliases=["si"])
@commands.guild_only()
async def serverinfo_cmd(ctx):
    g = ctx.guild
    e = embed(f"🏠 {g.name}", color=COLOR_PRIMARY)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="ID", value=str(g.id), inline=True)
    e.add_field(name="Owner", value=g.owner.mention if g.owner else "?", inline=True)
    e.add_field(name="Members", value=str(g.member_count), inline=True)
    e.add_field(name="Channels", value=str(len(g.channels)), inline=True)
    e.add_field(name="Roles", value=str(len(g.roles)), inline=True)
    e.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"), inline=True)
    e.add_field(name="Boost Level", value=str(g.premium_tier), inline=True)
    e.add_field(name="Boosts", value=str(g.premium_subscription_count), inline=True)
    await ctx.reply(embed=e)


@bot.command(name="avatar", aliases=["av"])
async def avatar_cmd(ctx, member: discord.Member = None):
    t = member or ctx.author
    e = embed(f"🖼️ {t.display_name}'s Avatar", color=COLOR_PRIMARY)
    e.set_image(url=t.display_avatar.url)
    await ctx.reply(embed=e)


@bot.command(name="banner")
async def banner_cmd(ctx, member: discord.Member = None):
    t = member or ctx.author
    try:
        user = await bot.fetch_user(t.id)
    except discord.HTTPException:
        user = t
    if not user.banner:
        await ctx.reply(embed=error_embed("No Banner", f"{t.mention} has no banner."))
        return
    e = embed(f"🖼️ {t.display_name}'s Banner", color=COLOR_PRIMARY)
    e.set_image(url=user.banner.url)
    await ctx.reply(embed=e)


@bot.command(name="snipe")
@commands.guild_only()
async def snipe_cmd(ctx):
    s = bot.snipe_cache.get(ctx.channel.id)
    if not s:
        await ctx.reply(embed=error_embed("Nothing to Snipe", ""))
        return
    e = embed("🔫 Sniped Message", s["content"] or "*[no content]*", COLOR_WARNING)
    e.set_author(name=s["author"])
    e.timestamp = datetime.fromisoformat(s["timestamp"])
    await ctx.reply(embed=e)


@bot.command(name="editsnipe", aliases=["esnipe"])
@commands.guild_only()
async def editsnipe_cmd(ctx):
    s = bot.edit_snipe_cache.get(ctx.channel.id)
    if not s:
        await ctx.reply(embed=error_embed("Nothing to Snipe", ""))
        return
    e = embed("✏️ Edited Message", color=COLOR_WARNING)
    e.set_author(name=s["author"])
    e.add_field(name="Before", value=s["before"][:1024] or "*empty*", inline=False)
    e.add_field(name="After", value=s["after"][:1024] or "*empty*", inline=False)
    await ctx.reply(embed=e)


@bot.command(name="poll")
@commands.guild_only()
async def poll_cmd(ctx, question: str, *options):
    if len(options) < 2:
        await ctx.reply(embed=error_embed("Need Options", "Provide at least 2 options."))
        return
    if len(options) > 10:
        await ctx.reply(embed=error_embed("Too Many", "Max 10 options."))
        return
    e = embed("📊 " + question, color=COLOR_PRIMARY)
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    for i, opt in enumerate(options):
        e.add_field(name=emojis[i], value=opt, inline=False)
    msg = await ctx.send(embed=e)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])


@bot.command(name="remind")
async def remind_cmd(ctx, duration: str, *, text: str):
    try:
        secs = int(duration[:-1]) * {"s":1, "m":60, "h":3600, "d":86400}[duration[-1].lower()]
    except Exception:
        await ctx.reply(embed=error_embed("Bad Duration", "Use `10m`, `1h`."))
        return
    if secs < 1 or secs > 7*86400:
        await ctx.reply(embed=error_embed("Invalid", "1s - 7d."))
        return
    await ctx.reply(embed=success_embed("⏰ Reminder Set", f"I'll remind you in **{duration}**."))
    async def _r():
        await asyncio.sleep(secs)
        try:
            e = embed("⏰ Reminder", text, COLOR_GOLD)
            await ctx.author.send(embed=e)
        except discord.HTTPException:
            try:
                await ctx.send(f"{ctx.author.mention} ⏰ {text}")
            except discord.HTTPException:
                pass
    asyncio.create_task(_r())


@bot.command(name="afk")
@commands.guild_only()
async def afk_cmd(ctx, *, reason="AFK"):
    state = _load_guild_state(AFK_FILE, ctx.guild.id)
    state[str(ctx.guild.id)][str(ctx.author.id)] = {
        "reason": reason[:200],
        "since": datetime.now(timezone.utc).isoformat(),
    }
    save_json(AFK_FILE, state)
    await ctx.reply(embed=success_embed("💤 AFK Set", f"You're now AFK: **{reason[:200]}**"))


# =============================================================================
# ============================ SLASH COMMANDS =================================
# =============================================================================

@bot.tree.command(name="premiumpanel", description="Show the premium key panel")
async def premiumpanel_slash(interaction: discord.Interaction):
    await panel_logic(interaction)


@bot.tree.command(name="restock", description="Restock premium keys")
@app_commands.describe(key="Key(s) separated by comma")
async def restock_slash(interaction: discord.Interaction, key: str):
    await restock_logic(interaction, key)


@bot.tree.command(name="dm", description="DM keys from stock to a user")
async def dm_slash(interaction: discord.Interaction, user: discord.Member,
                   amount: int = DEFAULT_DM_AMOUNT, reason: str = None):
    await dm_logic(interaction, user, amount, reason)


@bot.tree.command(name="stock", description="Check premium stock")
async def stock_slash(interaction: discord.Interaction):
    await stock_logic(interaction)


@bot.tree.command(name="ticket", description="Send the ticket panel")
async def ticket_slash(interaction: discord.Interaction):
    await ticket_setup(interaction)


@bot.tree.command(name="ping", description="Bot latency")
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed("🏓 Pong!", f"Latency: `{round(bot.latency*1000)}ms`"))


@bot.tree.command(name="balance", description="Check your balance")
async def balance_slash(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    bal = get_credit_balance(interaction.guild.id, target.id)
    bal_text = "∞ (Jew Mode)" if is_jew_mode(target) else f"{bal:,}"
    e = embed(f"💳 {target.display_name}'s Balance", color=COLOR_GOLD)
    e.add_field(name="Credits", value=bal_text)
    e.add_field(name="Wallahis", value=str(get_wallahi_count(interaction.guild.id, target.id)))
    e.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="daily", description="Claim your daily 5 credits")
async def daily_slash(interaction: discord.Interaction):
    g, u = interaction.guild.id, interaction.user.id
    last = _get_cd(g, u, "daily")
    now = datetime.now(timezone.utc)
    if last:
        last_dt = datetime.fromisoformat(last)
        if now - last_dt < timedelta(hours=24):
            rem = timedelta(hours=24) - (now - last_dt)
            h, r = divmod(int(rem.total_seconds()), 3600)
            mi = r // 60
            await interaction.response.send_message(embed=warning_embed("Already Claimed", f"Come back in **{h}h {mi}m**."), ephemeral=True)
            return
    new = add_credit_balance(g, u, DAILY_REWARD)
    _set_cd(g, u, "daily", now.isoformat())
    e = success_embed("💰 Daily Reward", f"You received **{DAILY_REWARD}** credits!")
    e.add_field(name="New Balance", value=str(new))
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="removew", description="Remove wallahi credits")
async def removew_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_mod(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Access", ""), ephemeral=True)
        return
    if amount < 1:
        await interaction.response.send_message(embed=error_embed("Invalid", ">= 1"), ephemeral=True)
        return
    before = get_wallahi_count(interaction.guild.id, member.id)
    new = add_wallahi_credits(interaction.guild.id, member.id, -amount)
    e = success_embed("Removed", f"Removed **{before - new}** from {member.mention}.")
    e.add_field(name="Balance", value=str(new))
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="removec", description="Remove credits")
async def removec_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_mod(interaction.user):
        await interaction.response.send_message(embed=error_embed("No Access", ""), ephemeral=True)
        return
    if amount < 1:
        await interaction.response.send_message(embed=error_embed("Invalid", ">= 1"), ephemeral=True)
        return
    before = get_credit_balance(interaction.guild.id, member.id)
    new = add_credit_balance(interaction.guild.id, member.id, -amount)
    e = success_embed("Removed", f"Removed **{before - new}** from {member.mention}.")
    e.add_field(name="Balance", value=str(new))
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="pay", description="Pay another user credits")
async def pay_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if member.id == interaction.user.id or member.bot:
        await interaction.response.send_message(embed=error_embed("Invalid Target", ""), ephemeral=True)
        return
    if amount < 1:
        await interaction.response.send_message(embed=error_embed("Invalid Amount", ""), ephemeral=True)
        return
    g = interaction.guild.id
    bal = get_credit_balance(g, interaction.user.id)
    if not is_jew_mode(interaction.user) and bal < amount:
        await interaction.response.send_message(embed=error_embed("Not Enough", f"You have **{bal}**."), ephemeral=True)
        return
    if not is_jew_mode(interaction.user):
        add_credit_balance(g, interaction.user.id, -amount)
    add_credit_balance(g, member.id, amount)
    await interaction.response.send_message(embed=success_embed("💸 Payment Sent", f"Sent **{amount}** to {member.mention}."))


@bot.tree.command(name="serversave", description="Save the server (owner only)")
async def serversave_slash(interaction: discord.Interaction):
    await serversave_logic(interaction)


@bot.tree.command(name="loadserver", description="Restore the server from backup (owner only)")
async def loadserver_slash(interaction: discord.Interaction):
    await loadserver_logic(interaction)


@bot.tree.command(name="botinfo", description="Bot information")
async def botinfo_slash(interaction: discord.Interaction):
    e = embed("🤖 Bot Info", color=COLOR_PRIMARY)
    e.add_field(name="Bot", value=str(bot.user))
    e.add_field(name="Guilds", value=str(len(bot.guilds)))
    e.add_field(name="Users", value=str(sum(g.member_count or 0 for g in bot.guilds)))
    e.add_field(name="Uptime", value=str(datetime.now(timezone.utc) - bot.start_time).split(".")[0])
    if bot.user:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=e)


# =============================================================================
# ============================ WEB SERVER =====================================
# =============================================================================

async def _run_web_server():
    if not ENABLE_WEB_SERVER:
        return
    try:
        from aiohttp import web
    except ImportError:
        log.warning("aiohttp not installed, skipping web server")
        return

    async def health(request):
        return web.json_response({
            "status": "ok",
            "bot": str(bot.user) if bot.user else "starting",
            "guilds": len(bot.guilds),
            "uptime": str(datetime.now(timezone.utc) - bot.start_time),
        })

    async def root(request):
        return web.Response(text="Premium Bot is running 🚀")

    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"Web server listening on port {PORT}")


# =============================================================================
# ============================== MAIN =========================================
# =============================================================================

async def main():
    if not TOKEN:
        log.critical("Missing DISCORD_TOKEN! Set it in env vars.")
        sys.exit(1)

    asyncio.create_task(_run_web_server())

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _shutdown():
        log.info("Shutdown signal received...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    try:
        await bot.start(TOKEN)
    except discord.LoginFailure:
        log.critical("Invalid token!")
    except Exception as e:
        log.exception(f"Bot crashed: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
