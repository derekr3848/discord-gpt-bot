import os
import asyncio
import logging
import textwrap
import base64
from io import BytesIO

import aiohttp
import discord
from discord.ext import commands

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # We'll fall back to an in-memory store if redis isn't available

from openai import OpenAI

# ------------------------
# Configuration / Globals
# ------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord-gpt-bot")

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID") or "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"
OPENAI_AUDIO_ASSISTANT_ID = os.getenv("OPENAI_AUDIO_ASSISTANT_ID") or OPENAI_ASSISTANT_ID
REDIS_URL = os.getenv("REDIS_URL")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

IMAGE_MODEL = "gpt-image-1"
TRANSCRIBE_MODEL = "whisper-1"

# Keys in redis / memory
def key_user_thread(user_id: int) -> str:
    return f"user_thread:{user_id}"

def key_user_openai_thread(user_id: int) -> str:
    return f"user_openai_thread:{user_id}"


# ------------------------
# Simple async key-value store
# ------------------------

class MemoryStore:
    """Generic async key/value interface. Uses Redis if available, else in-memory dict."""
    def __init__(self):
        self._use_redis = False
        self._redis = None
        self._dict = {}

        if REDIS_URL and redis is not None:
            try:
                self._redis = redis.from_url(REDIS_URL)
                self._use_redis = True
                logger.info("Using Redis for memory: %s", REDIS_URL)
            except Exception as e:
                logger.warning("Failed to connect to Redis (%s), falling back to in-memory store", e)
        else:
            logger.info("REDIS_URL not set or redis not installed – using in-memory store")

    async def get(self, key: str):
        if self._use_redis:
            val = await self._redis.get(key)
            if val is None:
                return None
            return val.decode("utf-8") if isinstance(val, (bytes, bytearray)) else val
        return self._dict.get(key)

    async def set(self, key: str, value: str):
        if self._use_redis:
            await self._redis.set(key, value)
        else:
            self._dict[key] = value

    async def close(self):
        if self._use_redis and self._redis is not None:
            await self._redis.close()


memory_store = MemoryStore()


# ------------------------
# Discord Bot Setup
# ------------------------

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ------------------------
# Utility helpers
# ------------------------

def split_message(text: str, limit: int = 1900):
    """Split a long string into chunks safe for Discord."""
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


def sync_openai_chat(thread_id: str | None, user_message: str, assistant_id: str):
    """
    Synchronous helper to talk to the OpenAI Assistants API.
    Returns (thread_id, reply_text).
    """
    # Ensure thread exists
    if thread_id is None:
        thread = client_openai.beta.threads.create()
        thread_id = thread.id

    # Add the user message
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message,
    )

    # Run the assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )

    if run.status != "completed":
        raise RuntimeError(f"Assistant run not completed (status={run.status})")

    # Get latest assistant message
    messages = client_openai.beta.threads.messages.list(
        thread_id=thread_id, order="desc", limit=1
    )

    reply_text = ""
    if messages.data:
        msg = messages.data[0]
        # Find first text part
        for part in msg.content:
            if part.type == "text":
                reply_text = part.text.value
                break

    return thread_id, reply_text or "I couldn't generate a response."


async def chat_with_assistant(thread_id: str | None, user_message: str, assistant_id: str):
    """Async wrapper around sync_openai_chat."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, sync_openai_chat, thread_id, user_message, assistant_id
    )


def sync_generate_image(prompt: str) -> bytes:
    """
    Generate an image via gpt-image-1 and return PNG bytes.
    """
    result = client_openai.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    img_b64 = result.data[0].b64_json
    return base64.b64decode(img_b64)


async def generate_image_bytes(prompt: str) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_generate_image, prompt)


def sync_transcribe_audio(data: bytes, filename: str) -> str:
    """
    Transcribe audio bytes via Whisper.
    """
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".mp3") as tmp:
        tmp.write(data)
        tmp.flush()
        audio_file = open(tmp.name, "rb")
        try:
            transcript = client_openai.audio.transcriptions.create(
                model=TRANSCRIBE_MODEL,
                file=audio_file,
            )
        finally:
            audio_file.close()
    return transcript.text


async def transcribe_audio(data: bytes, filename: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_transcribe_audio, data, filename)


async def download_attachment(attachment: discord.Attachment) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            resp.raise_for_status()
            return await resp.read()


# ------------------------
# Per-user AI thread helpers
# ------------------------

async def get_or_create_user_thread(ctx_channel: discord.TextChannel, user: discord.Member) -> discord.Thread:
    """
    Get the user's dedicated AI thread for this guild, or create it.
    The thread ID is stored in memory_store keyed by the user ID.
    """
    stored_thread_id = await memory_store.get(key_user_thread(user.id))
    if stored_thread_id:
        thread = ctx_channel.guild.get_thread(int(stored_thread_id))
        if thread and not thread.archived:
            return thread

    # Create a new thread in the current channel
    thread_name = f"{user.display_name} × Derek AI"
    thread = await ctx_channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.public_thread,
    )

    await memory_store.set(key_user_thread(user.id), str(thread.id))
    return thread


async def get_user_openai_thread_id(user: discord.abc.User) -> str | None:
    return await memory_store.get(key_user_openai_thread(user.id))


async def set_user_openai_thread_id(user: discord.abc.User, thread_id: str):
    await memory_store.set(key_user_openai_thread(user.id), thread_id)


def is_audio_attachment(att: discord.Attachment) -> bool:
    if att.content_type and att.content_type.startswith("audio/"):
        return True
    # Fallback by extension
    audio_exts = (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".webm", ".mka")
    return att.filename.lower().endswith(audio_exts)


# ------------------------
# Bot Events & Commands
# ------------------------

@bot.event
async def on_ready():
    logger.info("🤖 Bot ready – logged in as %s", bot.user)
    # No need to scan redis; memory is looked up lazily.


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    await ctx.reply("Pong!")


@bot.command(name="start")
async def start(ctx: commands.Context):
    """
    Create (or find) the user's personal AI thread.
    After this, they talk to the bot *only in that thread* with no commands.
    """
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.reply("Please run `!start` in a server text channel, not in a thread/DM.")
        return

    thread = await get_or_create_user_thread(ctx.channel, ctx.author)

    await ctx.reply(
        f"✅ Created / found your private AI thread: {thread.mention}\n"
        f"Chat with me there – no command needed."
    )

    # Greet in the thread
    greeting = (
        f"Hey {ctx.author.mention}! 👋\n"
        "This is your personal Derek AI thread.\n"
        "- Just type messages and I'll reply.\n"
        "- Send audio call recordings here and I'll transcribe + analyze them.\n"
        "- Use `!image <prompt>` (in any channel) for image generation."
    )
    await thread.send(greeting)


@bot.command(name="image")
async def image(ctx: commands.Context, *, prompt: str):
    """
    Generate an image using gpt-image-1 and send it.
    """
    try:
        await ctx.reply("🎨 Generating image, one sec...")
        async with ctx.channel.typing():
            img_bytes = await generate_image_bytes(prompt)

        file = discord.File(BytesIO(img_bytes), filename="image.png")
        await ctx.send(file=file)
    except Exception as e:
        logger.exception("Image generation failed")
        await ctx.send(f"❌ Image generation failed: `{e}`")


async def handle_text_message_in_ai_thread(message: discord.Message):
    """
    Handle normal text message inside a user's AI thread.
    """
    user = message.author
    channel = message.channel  # this is a Thread
    content = message.content.strip()
    if not content:
        return

    # Get (or create) OpenAI thread id for this user
    openai_thread_id = await get_user_openai_thread_id(user)

    async with channel.typing():
        try:
            # Sales / marketing focused assistant; your Assistant's instructions handle persona.
            openai_thread_id, reply = await chat_with_assistant(
                openai_thread_id,
                content,
                OPENAI_ASSISTANT_ID,
            )
            await set_user_openai_thread_id(user, openai_thread_id)
        except Exception as e:
            logger.exception("Error talking to OpenAI")
            await channel.send(f"⚠️ Error talking to the AI: `{e}`")
            return

    # Send reply in safe chunks
    for chunk in split_message(reply):
        await channel.send(chunk)


async def handle_audio_in_ai_thread(message: discord.Message, attachment: discord.Attachment):
    """
    When a user posts an audio file in their AI thread:
    - Download
    - Transcribe
    - Ask the assistant to analyze the sales/setting/marketing call
    - Include red-flag detection in the analysis
    """
    channel = message.channel
    user = message.author

    await channel.send("🎵 Received audio. Transcribing your call...")

    try:
        audio_bytes = await download_attachment(attachment)
    except Exception as e:
        logger.exception("Error downloading audio")
        await channel.send(f"⚠️ Could not download the audio file: `{e}`")
        return

    try:
        async with channel.typing():
            transcript = await transcribe_audio(audio_bytes, attachment.filename)
    except Exception as e:
        logger.exception("Error transcribing audio")
        await channel.send(f"⚠️ Error during transcription: `{e}`")
        return

    await channel.send("✏️ Transcription complete. Analyzing now...")

    # Build analysis prompt – sales + setter + meta ads + YouTube + organic + Christian coaches
    analysis_prompt = textwrap.dedent(
        f"""
        You are a Christian, high-performance business coach AI helping agency owners and coaches.

        TASK: Analyze the following call transcript (sales, setter, marketing, or coaching call).

        For the analysis, give:
        1. **Quick summary of the call**
        2. **What the rep/coach did well** (bullet points)
        3. **Opportunities to improve**, with specific lines they could have said instead
        4. **Lead quality assessment** (cold / warm / hot, affluence, decision-making power)
        5. **Red-flag detector** – list any red flags around:
           - misaligned values with Christian ethics
           - poor qualification (money, authority, need, timing)
           - compliance or policy risks (e.g., Meta ad policy, promises, claims)
           - bad sales behavior (pressure, manipulation, lying)
        6. **Concrete action items** for the next 3–5 calls.

        IMPORTANT CONTEXT:
        - The business is focused on Christian agency owners and coaches.
        - We care about sales, setting, Meta ads, YouTube, organic acquisition, and operations.

        TRANSCRIPT (verbatim):
        \"\"\"{transcript}\"\"\"
        """
    ).strip()

    # Use a *separate* OpenAI thread for audio analysis, but still keyed per user so memory can grow
    openai_thread_id = await get_user_openai_thread_id(user)

    try:
        async with channel.typing():
            openai_thread_id, reply = await chat_with_assistant(
                openai_thread_id,
                analysis_prompt,
                OPENAI_AUDIO_ASSISTANT_ID,
            )
            await set_user_openai_thread_id(user, openai_thread_id)
    except Exception as e:
        logger.exception("Error analyzing audio")
        await channel.send(f"⚠️ Error processing audio: `{e}`")
        return

    # Send summary back in safe chunks
    header = "✅ Call analysis complete. Here are your insights:\n"
    chunks = split_message(header + reply)
    for i, chunk in enumerate(chunks):
        await channel.send(chunk)


@bot.event
async def on_message(message: discord.Message):
    # Let commands (like !start, !image) run first
    await bot.process_commands(message)

    # Ignore bot's own messages
    if message.author.bot:
        return

    # 1) Only auto-respond inside a dedicated user AI thread
    if isinstance(message.channel, discord.Thread):
        # Check if this thread belongs to the author
        stored_thread_id = await memory_store.get(key_user_thread(message.author.id))
        if stored_thread_id and int(stored_thread_id) == message.channel.id:
            # If there is an audio attachment – prioritize audio analysis
            audio_attachments = [a for a in message.attachments if is_audio_attachment(a)]
            if audio_attachments:
                await handle_audio_in_ai_thread(message, audio_attachments[0])
            else:
                await handle_text_message_in_ai_thread(message)


# ------------------------
# Run the bot
# ------------------------

if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    finally:
        # Clean up redis connection on shutdown
        asyncio.run(memory_store.close())
