import os
import io
import textwrap
import asyncio
import base64

import discord
from discord.ext import commands

from openai import OpenAI
import redis.asyncio as redis


# ========= ENV VARS =========
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = (
    os.getenv("OPENAI_ASSISTANT_ID")
    or os.getenv("ASSISTANT_ID")  # in case you named it this
)

REDIS_URL = os.getenv("REDIS_URL")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
if not ASSISTANT_ID:
    raise RuntimeError("OPENAI_ASSISTANT_ID (or ASSISTANT_ID) is not set")


# ========= CLIENTS =========
client_openai = OpenAI(api_key=OPENAI_API_KEY)

redis_client = None
if REDIS_URL:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# local cache so we don't hit Redis every time
# user_id -> {"openai_thread_id": str, "channel_id": str}
user_state_cache: dict[int, dict[str, str]] = {}


# ========= DISCORD SETUP =========
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ========= HELPERS =========
async def send_long_message(channel: discord.abc.Messageable, text: str):
    """Split long text into Discord-safe chunks."""
    max_len = 1900  # stay well under 2000 char limit
    for chunk in textwrap.wrap(text, max_len, replace_whitespace=False):
        await channel.send(chunk)


async def get_user_state(user: discord.User | discord.Member):
    """Load a user's state from cache or Redis."""
    state = user_state_cache.get(user.id)
    if state is not None:
        return state

    if redis_client is None:
        return None

    key = f"user:{user.id}"
    data = await redis_client.hgetall(key)
    if data:
        state = {
            "openai_thread_id": data.get("openai_thread_id"),
            "channel_id": data.get("channel_id"),
        }
        user_state_cache[user.id] = state
        return state

    return None


async def save_user_state(user: discord.User | discord.Member, state: dict):
    """Save a user's state to cache and Redis."""
    user_state_cache[user.id] = state
    if redis_client is not None:
        key = f"user:{user.id}"
        await redis_client.hset(
            key,
            mapping={
                "openai_thread_id": state.get("openai_thread_id") or "",
                "channel_id": state.get("channel_id") or "",
            },
        )


def add_message_to_thread(thread_id: str, content: str):
    """Send a user message into the OpenAI thread."""
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=content,
    )


def run_assistant(thread_id: str) -> str:
    """Run the assistant and return the assistant's latest reply."""
    # create_and_poll blocks until run is complete
    client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    msgs = client_openai.beta.threads.messages.list(
        thread_id=thread_id,
        order="desc",
        limit=1,
    )
    latest = msgs.data[0]
    parts = []

    for c in latest.content:
        if c.type == "text":
            parts.append(c.text.value)

    return "\n".join(parts).strip()


async def get_or_create_ai_thread(
    user: discord.User | discord.Member, parent_channel: discord.TextChannel
):
    """
    Ensure the user has:
      - an OpenAI thread
      - a dedicated Discord thread channel
    Returns (state, discord_thread)
    """
    state = await get_user_state(user)
    discord_thread = None

    # try to reuse existing thread/channel if they still exist
    if state and state.get("channel_id"):
        chan_id = int(state["channel_id"])
        chan = parent_channel.guild.get_channel(chan_id)
        if chan is not None:
            discord_thread = chan

    if state and state.get("openai_thread_id") and discord_thread is not None:
        return state, discord_thread

    # create new OpenAI thread
    ai_thread = client_openai.beta.threads.create()

    # create Discord thread off the parent channel
    discord_thread = await parent_channel.create_thread(
        name=f"{user.display_name}-ai-chat",
        type=discord.ChannelType.public_thread,
    )

    state = {
        "openai_thread_id": ai_thread.id,
        "channel_id": str(discord_thread.id),
    }
    await save_user_state(user, state)
    return state, discord_thread


async def handle_text_chat(message: discord.Message, openai_thread_id: str):
    """Handle a normal text message inside the user's AI thread."""
    user_prompt = message.content.strip()
    if not user_prompt:
        return

    # Add context about who this is for
    marketing_flavor = (
        "You are a Christian, ethical sales & marketing coach helping agency owners "
        "and coaches. You're friendly, direct, and practical. "
        "Give concise answers unless the user asks for more detail."
    )

    add_message_to_thread(
        openai_thread_id,
        f"[Discord user: {message.author.display_name}]\n"
        f"{marketing_flavor}\n\nUser message:\n{user_prompt}",
    )

    await message.channel.trigger_typing()
    reply = run_assistant(openai_thread_id)
    await send_long_message(message.channel, reply)


async def handle_audio_message(
    message: discord.Message, openai_thread_id: str, attachment: discord.Attachment
):
    """Transcribe an audio attachment and analyze the call."""
    await message.channel.send(
        "🎧 Received audio. Transcribing your call and analyzing..."
    )

    # download audio file
    audio_bytes = await attachment.read()
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = attachment.filename or "call_audio.m4a"

    # TRANSCRIBE
    transcription = client_openai.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="text",
    )
    transcript_text = transcription.strip()

    # Build analysis prompt with red flag detection & coaching
    analysis_prompt = f"""
You are a Christian, ethical sales & marketing coach for agency owners and coaches.

You are analyzing a **sales or setter call** transcript from Discord.

TRANSCRIPT (verbatim):
\"\"\"{transcript_text}\"\"\"

Do ALL of the following in a concise, bullet-point style:

1) Quick Summary
   - 2–3 bullets summarizing what happened in the call.

2) Sales / Setting Breakdown
   - What the rep did well.
   - What needs improvement.
   - Specific suggestions for better questions, objection handling, and closing.

3) Red Flag Detector
   - List any red flags about:
     - prospect quality (no money, no decision power, not serious),
     - ethics (false promises, pressure tactics),
     - misalignment with a Christian, integrity-first approach.

4) Actionable To-Do List
   - 3–5 concrete action items the rep should do before their next call.

Keep the entire response under ~1000 words so it fits comfortably in Discord.
"""

    add_message_to_thread(openai_thread_id, analysis_prompt)

    await message.channel.trigger_typing()
    reply = run_assistant(openai_thread_id)
    await send_long_message(message.channel, reply)


# ========= COMMANDS =========
@bot.event
async def on_ready():
    print(f"✅ Bot ready — Logged in as {bot.user} ({bot.user.id})")
    if redis_client is None:
        print("⚠️ REDIS_URL not set; user memory will NOT persist across restarts.")
    else:
        print("✅ Redis connected; user memory will persist across restarts.")


@bot.command(name="start")
async def start_cmd(ctx: commands.Context):
    """
    Create (or reuse) the user's dedicated AI thread.
    Only ONE thread per user.
    """
    if ctx.guild is None:
        await ctx.reply("Please run `!start` inside a server channel, not in DMs.")
        return

    state = await get_user_state(ctx.author)
    if state and state.get("channel_id"):
        chan = ctx.guild.get_channel(int(state["channel_id"]))
        if chan:
            await ctx.reply(
                f"You already have a personal AI thread: {chan.mention}\n"
                "Talk to the bot inside that thread – no command needed."
            )
            return

    state, thread = await get_or_create_ai_thread(ctx.author, ctx.channel)

    await thread.send(
        f"Hey {ctx.author.mention}! 👋\n"
        "This is your personal AI thread.\n"
        "You can talk to me here about sales, setting, Meta ads, YouTube, "
        "organic, and Christian-aligned marketing.\n"
        "• Just type messages normally – **no command needed**.\n"
        "• Upload call recordings here for transcription & coaching.\n"
        "• Use `!image <prompt>` anywhere to generate creatives."
    )

    await ctx.reply(f"Your personal AI thread is ready: {thread.mention}")


@bot.command(name="image")
async def image_cmd(ctx, *, prompt: str):
    await ctx.send("🎨 Generating image, one sec...")

    try:
        result = client_openai.images.generate(
            model="gpt-image-1",
            prompt=prompt,
        )

        # Save image
        img_bytes = base64.b64decode(result.data[0].b64_json)
        filename = "image.png"
        with open(filename, "wb") as f:
            f.write(img_bytes)

        # Send ONLY the image – no empty text
        await ctx.send(file=discord.File(filename))

    except Exception as e:
        await ctx.send(f"❌ Image generation failed: `{e}`")



# ========= AUTO-REPLY LOGIC =========
@bot.event
async def on_message(message: discord.Message):
    # never reply to ourselves or other bots
    if message.author.bot:
        return

    # Let commands (`!start`, `!image`, etc.) run first
    await bot.process_commands(message)

    # Ignore messages that start with the prefix – they are commands
    if message.content.startswith(bot.command_prefix):
        return

    # Only care about messages inside the user's dedicated thread
    state = await get_user_state(message.author)
    if not state or not state.get("channel_id"):
        return

    try:
        user_thread_channel_id = int(state["channel_id"])
    except ValueError:
        return

    if message.channel.id != user_thread_channel_id:
        # message is not in their AI thread
        return

    # If there's an audio attachment -> transcribe & analyze
    audio_attachment = None
    for att in message.attachments:
        if any(
            att.filename.lower().endswith(ext)
            for ext in (".mp3", ".m4a", ".wav", ".ogg", ".flac")
        ):
            audio_attachment = att
            break

    openai_thread_id = state.get("openai_thread_id")
    if not openai_thread_id:
        # shouldn't normally happen; recreate thread
        new_state, _ = await get_or_create_ai_thread(
            message.author, message.channel.parent
        )
        openai_thread_id = new_state["openai_thread_id"]

    try:
        if audio_attachment is not None:
            await handle_audio_message(message, openai_thread_id, audio_attachment)
        else:
            await handle_text_chat(message, openai_thread_id)
    except Exception as e:
        # don't crash the bot on errors
        await message.channel.send(f"⚠️ Error talking to the AI: `{e}`")


# ========= RUN THE BOT =========
bot.run(DISCORD_TOKEN)
