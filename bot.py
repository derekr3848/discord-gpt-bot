import os
import io
import base64
import textwrap
from typing import Dict, Optional

import discord
from discord.ext import commands
from openai import OpenAI

# ========= ENV VARS =========
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")  # asst_Fc3yRPdXjHUBlXNswxQ4q1TM

if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN env var is missing")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY env var is missing")
if not ASSISTANT_ID:
    raise RuntimeError("ASSISTANT_ID env var is missing")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# ========= DISCORD BOT SETUP =========
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# user_id -> discord_thread_id
user_to_discord_thread: Dict[int, int] = {}
# discord_thread_id -> openai_thread_id
discord_thread_to_openai: Dict[int, str] = {}


# ========= UTILS =========
def get_openai_message_text(msg) -> str:
    """Extract plain text from an OpenAI thread message object."""
    parts = []
    if hasattr(msg, "content"):
        for c in msg.content:
            if getattr(c, "type", None) == "text":
                parts.append(getattr(c.text, "value", ""))
    return "".join(parts).strip()


async def send_long_message(channel: discord.abc.Messageable, text: str):
    """
    Safely send long text to Discord by splitting into <= 2000-char chunks.
    Using ~1500 to be extra safe with formatting.
    """
    if not text:
        return
    chunks = textwrap.wrap(text, width=1500, break_long_words=False, replace_whitespace=False)
    for chunk in chunks:
        await channel.send(chunk)


def is_audio_attachment(att: discord.Attachment) -> bool:
    if att.content_type and att.content_type.startswith("audio"):
        return True
    # Fallback on file extension
    audio_exts = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".webm")
    return att.filename.lower().endswith(audio_exts)


# ========= STARTUP =========
@bot.event
async def on_ready():
    print(f"🤖 Bot ready — logged in as {bot.user} (id: {bot.user.id})")
    print("Loaded user memory threads:", len(user_to_discord_thread))


# ========= COMMANDS =========
@bot.command(name="start")
async def start(ctx: commands.Context):
    """
    Create or re-open a private thread for this user.
    All normal messages in that thread go to the OpenAI assistant automatically.
    """
    user_id = ctx.author.id

    # If user already has a thread, try to reuse it
    if user_id in user_to_discord_thread:
        existing_thread_id = user_to_discord_thread[user_id]
        existing_thread = ctx.guild.get_thread(existing_thread_id)
        if existing_thread is not None and not existing_thread.archived:
            await ctx.reply(
                f"✅ You already have an AI thread: {existing_thread.mention}\n"
                f"Chat with me there (no commands needed once inside)."
            )
            return

    # Create Discord private thread
    ai_thread = await ctx.channel.create_thread(
        name=f"{ctx.author.display_name}-ai",
        type=discord.ChannelType.private_thread,
        invitable=False,
        reason="Personal AI thread",
    )

    # Create OpenAI thread for this user
    oa_thread = client_openai.beta.threads.create()
    discord_thread_to_openai[ai_thread.id] = oa_thread.id
    user_to_discord_thread[user_id] = ai_thread.id

    await ai_thread.add_user(ctx.author)

    await ai_thread.send(
        f"👋 Hey {ctx.author.mention}! This is your **personal AI thread**.\n"
        "- Just talk to me normally here, no `!` commands needed.\n"
        "- Upload **audio calls** here for transcription & analysis.\n"
        "- Use `!image <prompt>` to generate images.\n"
        "- Use `!redflags <text>` to quickly scan scripts/DMs for red flags."
    )

    await ctx.reply(f"✅ Thread created: {ai_thread.mention}")


@bot.command(name="image")
async def image_command(ctx: commands.Context, *, prompt: str):
    """
    Generate an image from a prompt using OpenAI's image API.
    Works in normal channels or AI threads.
    """
    await ctx.reply("🎨 Generating image, one sec...")

    try:
        img_resp = client_openai.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        b64_data = img_resp.data[0].b64_json
        img_bytes = base64.b64decode(b64_data)

        file = discord.File(io.BytesIO(img_bytes), filename="ai-image.png")
        await ctx.send(file=file)
    except Exception as e:
        await ctx.send(f"❌ Image generation failed: `{e}`")


@bot.command(name="redflags")
async def redflags_command(ctx: commands.Context, *, text: str):
    """
    Quick red-flag detector for scripts / DMs / emails.
    Keeps response short and Discord-safe.
    """
    await ctx.reply("🚩 Scanning for red flags...")

    try:
        prompt = (
            "You are Derek's Christian marketing & sales coach AI.\n"
            "The user will give you text from a sales script, DM convo, email, or call.\n"
            "Your job: list **only red flags** that could hurt trust, conversions, or fit for "
            "Christian agency owners & coaches.\n"
            "Return:\n"
            "- Brief title line\n"
            "- Bulleted list where each bullet starts with '🚩'\n"
            "Be concise and under 1000 characters.\n\n"
            f"Text to analyze:\n{text}"
        )

        resp = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp.choices[0].message.content
        await send_long_message(ctx.channel, answer)
    except Exception as e:
        await ctx.send(f"❌ Red-flag analysis failed: `{e}`")


# ========= CORE AI HANDLING (THREAD MESSAGES) =========
async def handle_text_in_ai_thread(message: discord.Message, oa_thread_id: str):
    """
    Regular text message inside a user's AI thread.
    Send to assistant + reply.
    """
    async with message.channel.typing():
        # Add user message to OpenAI thread
        client_openai.beta.threads.messages.create(
            thread_id=oa_thread_id,
            role="user",
            content=message.content,
        )

        # Run the assistant
        run = client_openai.beta.threads.runs.create_and_poll(
            thread_id=oa_thread_id,
            assistant_id=ASSISTANT_ID,
        )

        if run.status != "completed":
            await message.channel.send(f"⚠️ Run did not complete (status: {run.status}).")
            return

        # Get latest assistant message
        msgs = client_openai.beta.threads.messages.list(
            thread_id=oa_thread_id,
            order="desc",
            limit=1,
        )
        if not msgs.data:
            await message.channel.send("⚠️ No response from the assistant.")
            return

        reply_text = get_openai_message_text(msgs.data[0])
        if not reply_text:
            reply_text = "⚠️ Assistant returned empty response."

    await send_long_message(message.channel, reply_text)


async def handle_audio_in_ai_thread(message: discord.Message, attachment: discord.Attachment, oa_thread_id: str):
    """
    Audio file dropped in AI thread:
    - Transcribe with Whisper
    - Analyze as sales/setting/marketing call for Christian agency owners & coaches
    - Include RED-FLAG detector in the analysis
    - Keep Discord response safely short
    """
    await message.channel.send("🎧 Received audio. Transcribing your call...")

    try:
        audio_bytes = await attachment.read()
        audio_file = ("call_audio.wav", audio_bytes)

        # 1) Transcription
        transcript_obj = client_openai.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        transcript_text = transcript_obj.text

        await message.channel.send("✏️ Transcription complete. Analyzing now...")

        # 2) Send transcript into the same assistant thread for analysis
        #    We keep the analysis **short** to avoid Discord length errors.
        instructions = (
            "You are Derek's AI assistant for Christian agency owners & coaches, "
            "specialized in sales, setting, Meta ads, YouTube, organic, and marketing.\n\n"
            "You are analyzing a **call transcript**. Your response MUST:\n"
            "1) Give a short title.\n"
            "2) Give 3–5 concise bullet points of what happened.\n"
            "3) Give 3–5 concise coaching bullets.\n"
            "4) RED-FLAG DETECTOR: list bullets that start with '🚩' for any big issues.\n"
            "Keep the **entire response under 1500 characters**. Be direct and practical."
        )

        # Add transcript as a message in the thread
        client_openai.beta.threads.messages.create(
            thread_id=oa_thread_id,
            role="user",
            content=f"Here is a call transcript to analyze:\n\n{transcript_text}",
        )

        run = client_openai.beta.threads.runs.create_and_poll(
            thread_id=oa_thread_id,
            assistant_id=ASSISTANT_ID,
            instructions=instructions,
        )

        if run.status != "completed":
            await message.channel.send(f"⚠️ Analysis run did not complete (status: {run.status}).")
            return

        msgs = client_openai.beta.threads.messages.list(
            thread_id=oa_thread_id,
            order="desc",
            limit=1,
        )
        if not msgs.data:
            await message.channel.send("⚠️ No analysis message from the assistant.")
            return

        analysis_text = get_openai_message_text(msgs.data[0])

        await message.channel.send("✅ Analysis ready:")
        await send_long_message(message.channel, analysis_text)

    except Exception as e:
        await message.channel.send(f"❌ Error processing audio: `{e}`")


@bot.event
async def on_message(message: discord.Message):
    """
    - Runs commands (like !start, !image, !redflags)
    - Then, if the message is inside an AI thread and NOT a command,
      forwards it to OpenAI (text or audio).
    """
    # Ignore bot messages
    if message.author.bot:
        return

    # Let the commands extension handle commands first
    await bot.process_commands(message)

    # Only care about messages in threads that are registered AI threads
    if not isinstance(message.channel, discord.Thread):
        return

    discord_thread_id = message.channel.id
    if discord_thread_id not in discord_thread_to_openai:
        return

    # Don't treat commands (starting with "!") as conversation
    if message.content.startswith("!"):
        return

    oa_thread_id = discord_thread_to_openai[discord_thread_id]

    # If there is an audio attachment, process as call analysis
    audio_attachment: Optional[discord.Attachment] = None
    for att in message.attachments:
        if is_audio_attachment(att):
            audio_attachment = att
            break

    if audio_attachment is not None:
        await handle_audio_in_ai_thread(message, audio_attachment, oa_thread_id)
        return

    # Otherwise treat as normal text chat with the assistant
    if message.content.strip():
        await handle_text_in_ai_thread(message, oa_thread_id)


# ========= RUN BOT =========
if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
