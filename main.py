import re
import discord
import os
from discord.ext import tasks, commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.voice_states = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

UNRANKED_REGEX = re.compile(r"\b(9D|8D)-\d{2}\b")

LEO_ROLES = {
    "Florida Highway Patrol": re.compile(r"\b(1K|2K|3K|4K|5K|6K)-\d{2}\b"),
    "Fort Lauderdale Police Department": re.compile(r"\b(1A|2A|3A|4A|5A|7A)-\d{2}\b"),
    "Broward County Sheriff's Office": re.compile(r"\b(2B|3B|4B|5B|7B|1S)-\d{2}\b")
}

RANKED_REGEX = re.compile(r"\b(1S|1A|2A|3A|4A|5A|7A|2B|3B|4B|5B|7B|1K|2K|3K|4K|5K|6K)-\d{2}\b")

STAFF_PREFIXES = ("!STAFF", "!MOD")


def get_member_department_regexes(member: discord.Member):
    regexes = []
    for role_name, regex in LEO_ROLES.items():
        if discord.utils.get(member.roles, name=role_name):
            regexes.append(regex)
    return regexes


def extract_callsign(name: str):
    cleaned = re.split(r'\s*\|\s*', name)[0]
    return cleaned.strip()


def is_staff(member: discord.Member):
    name_upper = member.display_name.upper()
    return any(name_upper.startswith(prefix) for prefix in STAFF_PREFIXES)


async def log_disconnection(member: discord.Member, reason: str):
    guild = bot.get_guild(GUILD_ID)
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"User `{member.display_name}` was disconnected from VC. Reason: {reason}")


async def validate_member(member: discord.Member):
    if is_staff(member):
        return

    name = extract_callsign(member.display_name)
    dept_regexes = get_member_department_regexes(member)

    # If user has department roles, allow callsign if it matches ANY of them
    if dept_regexes:
        for regex in dept_regexes:
            if regex.search(name):
                return

        try:
            await member.send(
                f"Your callsign `{member.display_name}` is invalid for your department roles. You were removed from the voice channel."
            )
        except discord.Forbidden:
            pass

        if member.voice and member.voice.channel and member.voice.channel.id == VOICE_CHANNEL_ID:
            try:
                await member.move_to(None)
                await log_disconnection(member, "Invalid callsign for department roles")
            except:
                pass
        return

    # No department role but using ranked callsign
    if RANKED_REGEX.search(name):
        if member.voice and member.voice.channel and member.voice.channel.id == VOICE_CHANNEL_ID:
            try:
                await member.send(
                    "You are using a ranked callsign without a LEO role. You were removed from the voice channel."
                )
            except discord.Forbidden:
                pass

            try:
                await member.move_to(None)
                await log_disconnection(member, "Ranked callsign without LEO role")
            except:
                pass

    # Invalid unranked callsign
    elif not UNRANKED_REGEX.search(name):
        if member.voice and member.voice.channel and member.voice.channel.id == VOICE_CHANNEL_ID:
            try:
                await member.send(
                    "Your callsign is invalid. Allowed formats: `9D-##` or `8D-##`."
                )
            except discord.Forbidden:
                pass

            try:
                await member.move_to(None)
                await log_disconnection(member, "Invalid unranked callsign")
            except:
                pass


async def kick_member_by_name(ctx, *, search_name: str):
    search_name = search_name.strip().lower()
    guild = ctx.guild
    member_to_kick = None

    for member in guild.members:
        if is_staff(member):
            continue

        member_name = extract_callsign(member.display_name).lower()

        if search_name in member_name or search_name in member.name.lower():
            member_to_kick = member
            break

    if member_to_kick:
        try:
            await member_to_kick.kick(reason=f"Kicked by {ctx.author}")
            await ctx.send(f"Kicked {member_to_kick.display_name}")
            await log_disconnection(member_to_kick, f"Kicked by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick this member.")
        except Exception as e:
            await ctx.send(f"Failed to kick member: {e}")
    else:
        await ctx.send("Member not found.")


@bot.event
async def on_ready():
    scan_vc_members.start()


@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.id == VOICE_CHANNEL_ID:
        await validate_member(member)


@bot.event
async def on_member_update(before, after):
    if after.voice and after.voice.channel and after.voice.channel.id == VOICE_CHANNEL_ID:
        await validate_member(after)


@tasks.loop(minutes=5)
async def scan_vc_members():
    guild = bot.get_guild(GUILD_ID)
    vc = guild.get_channel(VOICE_CHANNEL_ID)

    if vc:
        for member in vc.members:
            await validate_member(member)


bot.add_command(commands.Command(kick_member_by_name, name="kick"))

bot.run(TOKEN)