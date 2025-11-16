import os
import io
import json
import base64
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ext import tasks
import aiohttp
from datetime import time, datetime, timezone

from asana_integration import AsanaClient

from openai import OpenAI
import redis.asyncio as redis


# ========= CONFIG =========

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set")

OPENAI_ASSISTANT_ID = os.getenv(
    "OPENAI_ASSISTANT_ID",
    "asst_Fc3yRPdXjHUBlXNswxQ4q1TM",  # your assistant as default
)

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set (Redis add-on on Railway)")

# Max images per user per day
MAX_IMAGES_PER_DAY = 50

# Admins who can use !inspectmemory
ADMIN_IDS_ENV = os.getenv("ADMIN_USER_IDS", "")
ADMIN_IDS = {int(x.strip()) for x in ADMIN_IDS_ENV.split(",") if x.strip().isdigit()}


# ========= CLIENTS =========

client_openai = OpenAI()
redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

asana_client = None

@bot.event
async def on_ready():
    global asana_client
    if asana_client is None:
        try:
            asana_client = AsanaClient()
            print("AsanaClient initialized")
        except Exception as e:
            print(f"AsanaClient not initialized: {e}")

    if not daily_asana_checkin.is_running():
        daily_asana_checkin.start()

    print(f"Bot logged in as {bot.user}")


# ========= REDIS HELPERS =========

async def get_user_discord_thread(user_id: int) -> int | None:
    v = await redis_client.get(f"user:{user_id}:discord_thread_id")
    return int(v) if v else None


async def set_user_discord_thread(user_id: int, thread_id: int) -> None:
    await redis_client.set(f"user:{user_id}:discord_thread_id", str(thread_id))
    await redis_client.set(f"thread:{thread_id}:user_id", str(user_id))


async def get_user_openai_thread(user_id: int) -> str | None:
    return await redis_client.get(f"user:{user_id}:openai_thread_id")


async def set_user_openai_thread(user_id: int, thread_id: str) -> None:
    await redis_client.set(f"user:{user_id}:openai_thread_id", thread_id)


async def get_or_create_openai_thread(user_id: int) -> str:
    thread_id = await get_user_openai_thread(user_id)
    if thread_id:
        return thread_id
    thread = client_openai.beta.threads.create()
    await set_user_openai_thread(user_id, thread.id)
    # analytics
    await redis_client.incr("stats:openai_threads_created")
    return thread.id


async def increment_stat(key: str, amount: int = 1) -> None:
    await redis_client.incr(key, amount)


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def can_generate_image(user_id: int) -> bool:
    """Check 50 images/day limit per user."""
    key = f"user:{user_id}:images_generated:{today_str()}"
    current = int(await redis_client.get(key) or 0)
    return current < MAX_IMAGES_PER_DAY


async def record_generated_image(user_id: int) -> None:
    key = f"user:{user_id}:images_generated:{today_str()}"
    await redis_client.incr(key)
    # expire after 3 days so keys don't grow forever
    await redis_client.expire(key, 3 * 24 * 3600)
    await increment_stat("stats:images_generated")


# ========= MEMORY HELPERS =========

EMPTY_MEMORY = {
    "profile": "",
    "business": "",
    "goals": "",
    "pains": "",
    "roadblocks": "",
    "triggers": "",
    "budget": "",
    "timeline": "",
    "notes": "",
}


async def get_user_memory(user_id: int) -> dict:
    raw = await redis_client.get(f"user:{user_id}:memory")
    if not raw:
        return EMPTY_MEMORY.copy()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return EMPTY_MEMORY.copy()
    # ensure all keys exist
    mem = EMPTY_MEMORY.copy()
    mem.update({k: str(v) for k, v in data.items() if k in mem})
    return mem


async def save_user_memory(user_id: int, memory: dict) -> None:
    await redis_client.set(f"user:{user_id}:memory", json.dumps(memory))


async def update_user_memory(user_id: int, new_text: str) -> None:
    """Ask a small model to update classified memory JSON based on new text."""
    existing = await get_user_memory(user_id)

    prompt = f"""
You are a CRM memory engine for a Christian agency coaching assistant.

You store what you learn about each user in this JSON format:

{json.dumps(EMPTY_MEMORY, indent=2)}

Existing memory for this user (JSON):
{json.dumps(existing, indent=2)}

New message or transcript from the user:
\"\"\"{new_text.strip()[:6000]}\"\"\"

Update the JSON, improving and filling in fields where appropriate.
Return ONLY valid JSON with the same top-level keys.
"""

    try:
        resp = client_openai.responses.create(
            model="gpt-4.1-mini",
            input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        )
        content = resp.output[0].content[0].text
        updated = json.loads(content)
        # merge with default schema
        new_mem = EMPTY_MEMORY.copy()
        new_mem.update({k: str(v) for k, v in updated.items() if k in new_mem})
        await save_user_memory(user_id, new_mem)
    except Exception as e:
        print(f"[MEMORY] Failed to update memory for {user_id}: {e}")


def format_memory_for_discord(memory: dict) -> str:
    parts = []
    for k, label in [
        ("profile", "Profile"),
        ("business", "Business"),
        ("goals", "Goals"),
        ("pains", "Pains"),
        ("roadblocks", "Roadblocks"),
        ("triggers", "Buying Triggers"),
        ("budget", "Budget"),
        ("timeline", "Timeline"),
        ("notes", "Notes"),
    ]:
        v = memory.get(k, "").strip()
        if not v:
            v = "_(nothing yet)_"
        parts.append(f"**{label}:** {v}")
    msg = "\n".join(parts)
    if len(msg) > 1900:
        msg = msg[:1900] + "\n\n_(truncated)_"
    return msg


# ========= OPENAI HELPERS =========

async def run_assistant(thread_id: str, user_message: str) -> str:
    """Send a message to your Assistant thread and return the latest reply text."""
    # add user message to thread
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message,
    )

    # run assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=OPENAI_ASSISTANT_ID,
    )

    # collect latest assistant message
    messages = client_openai.beta.threads.messages.list(thread_id=thread_id, limit=5)
    for msg in messages.data:
        if msg.role == "assistant":
            # messages can have multiple parts
            parts = []
            for c in msg.content:
                if c.type == "text":
                    parts.append(c.text.value)
            text = "\n".join(parts).strip()
            if text:
                return text
    return "I couldn't generate a response, please try again."


async def analyze_audio_transcript(transcript: str) -> str:
    """
    Use the Responses API to analyze a sales / setter / marketing call.
    Includes red-flag detection and coaching.
    """
    prompt = f"""
You are a Christian sales and marketing call coach.
Analyze the following call transcript for a Christian agency owner or coach.

Transcript:
\"\"\"{transcript.strip()[:8000]}\"\"\"

Do ALL of the following clearly and concisely:

1) Give a short summary of the call.
2) Break down what the rep did WELL and what they did POORLY.
3) Coach them on exactly how to improve.

4) VERY IMPORTANT: Detect and list red flags in these categories:
   💸 Budget flags
   🟧 Timeline objections
   😕 Uncertainty indicators
   🚫 Bad fit warnings
   🧊 Lead coldness signals
   💀 "Never buying" traits

For each category, output EITHER:
- "None detected", OR
- A bullet list with specific quotes/behaviors.

Return a response formatted for Discord with clear headings and bullet points.
Keep under 1500 characters if possible.
"""

    resp = client_openai.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    )
    return resp.output[0].content[0].text[:1900]


async def generate_image(prompt: str) -> bytes:
    """Generate an image and return PNG bytes."""
    img_resp = client_openai.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        n=1,
        response_format="b64_json",
    )
    b64 = img_resp.data[0].b64_json
    return base64.b64decode(b64)


async def analyze_image_with_gpt(image_url: str, extra_prompt: str | None = None) -> str:
    prompt = (
        "You are a creative director for Christian agency owners and coaches. "
        "Analyze this image like it's an ad / creative / piece of content. "
        "Give feedback on hook, clarity, scroll-stopping power, and what to change."
    )
    if extra_prompt:
        prompt += f"\n\nUser request: {extra_prompt}"

    resp = client_openai.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": {"url": image_url}},
                ],
            }
        ],
    )
    return resp.output[0].content[0].text[:1900]


async def analyze_pdf_bytes(pdf_bytes: bytes, filename: str) -> str:
    """
    Upload a PDF to OpenAI and ask for a marketing / sales focused analysis.
    """
    file_obj = io.BytesIO(pdf_bytes)
    file_obj.name = filename

    uploaded = client_openai.files.create(
        file=file_obj,
        purpose="assistants",
    )

    prompt = """
You are a strategic marketing and sales consultant for Christian agency owners and coaches.
Analyze this PDF document. Summarize the key ideas, identify strengths and weaknesses, and
give 3–7 concrete recommendations to improve the offer, messaging, and clarity.
Return a response formatted for Discord, under ~1500 characters.
"""

    resp = client_openai.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_file", "file_id": uploaded.id},
                ],
            }
        ],
    )
    return resp.output[0].content[0].text[:1900]


# ========= DISCORD EVENTS =========

@bot.event
async def on_ready():
    print(f"🤖 Bot ready — logged in as {bot.user} (id={bot.user.id})")


# ========= COMMANDS =========

@bot.command(name="start")
async def start(ctx: commands.Context):
    """
    Create (or recall) the user's private AI thread in this channel.
    All chat in that thread goes straight to your Assistant.
    """
    await increment_stat("stats:commands_start")

    # Only allow in text channels (not DMs)
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.reply("Please use `!start` inside a server text channel, not in DMs.")
        return

    existing_thread_id = await get_user_discord_thread(ctx.author.id)
    if existing_thread_id:
        thread = ctx.channel.guild.get_thread(existing_thread_id)
        if thread:
            await ctx.reply(f"You already have a thread: {thread.mention}")
            return

    # Create new private thread
    thread_name = f"{ctx.author.display_name}-ai"
    thread = await ctx.channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.private_thread,
        reason="Personal AI coaching thread",
    )
    await thread.add_user(ctx.author)

    await set_user_discord_thread(ctx.author.id, thread.id)
    await get_or_create_openai_thread(ctx.author.id)
    await increment_stat("stats:threads_created")

    await thread.send(
        f"Hey {ctx.author.mention}! 👋\n"
        "This is your private AI thread.\n"
        "Just talk to me here — no command needed.\n\n"
        "Things I can do:\n"
        "• Chat coaching on sales, setters, Meta ads, YouTube, organic, and marketing\n"
        "• Analyze *audio* (drop mobile voice messages or call recordings here)\n"
        "• `!image <prompt>` – generate ads / creatives (50 images/day)\n"
        "• `!analyzeimage` (with an image attached) – feedback on your creative\n"
        "• `!analyzepdf` (with a PDF attached) – review your docs/decks\n"
        "• `!myinfo` – see what I remember about you\n"
        "• `!resetmemory` – wipe my memory of you\n"
    )

    await ctx.reply(f"Your AI thread is ready: {thread.mention}")

@bot.command(name="start")
async def start_command(ctx: commands.Context):
    user = ctx.author

    # 1) create their private AI thread (you already do this)
    # thread = await ensure_user_thread(ctx, user)

    # 2) create their Asana project from your template
    if asana_client:
        async with aiohttp.ClientSession() as session:
            try:
                project_gid = await asana_client.create_project_for_user(
                    session=session,
                    discord_user_id=user.id,
                    client_name=user.display_name,
                )
                await ctx.send(
                    f"✅ Your 6-month Asana roadmap is ready.\n"
                    f"I’ll use it to keep you accountable every day at 8 AM CST.\n"
                    f"(Project ID: `{project_gid}`)"
                )
            except Exception as e:
                await ctx.send(
                    f"⚠️ I couldn't create your Asana project automatically. "
                    f"Let Derek know. (Error: `{e}`)"
                )
    else:
        await ctx.send(
            "⚠️ Asana integration is not configured yet. Ask Derek to set ASANA_ACCESS_TOKEN / ASANA_TEMPLATE_GID."
        )

    # 3) continue with any onboarding questions you already have...


@bot.command(name="myinfo")
async def myinfo(ctx: commands.Context):
    mem = await get_user_memory(ctx.author.id)
    msg = format_memory_for_discord(mem)
    await ctx.reply(f"🧠 **Here's what I remember about you:**\n\n{msg}")


@bot.command(name="resetmemory")
async def resetmemory(ctx: commands.Context):
    await redis_client.delete(f"user:{ctx.author.id}:memory")
    await ctx.reply("🧹 Memory wiped. I no longer remember your profile. Start talking and I’ll relearn.")


@bot.command(name="inspectmemory")
async def inspectmemory(ctx: commands.Context, user: discord.User | None = None):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.reply("❌ You don't have permission to use this command.")
        return

    if not user:
        await ctx.reply("Usage: `!inspectmemory @user`")
        return

    mem = await get_user_memory(user.id)
    msg = format_memory_for_discord(mem)
    await ctx.reply(f"🧠 **Memory for {user.mention}:**\n\n{msg}")


@bot.command(name="image")
async def image_command(ctx: commands.Context, *, prompt: str):
    """
    Generate an image. Respects per-user daily limit.
    """
    if not await can_generate_image(ctx.author.id):
        await ctx.reply(
            f"🚫 You've hit your daily image limit ({MAX_IMAGES_PER_DAY} per day). "
            "Try again tomorrow."
        )
        return

    await ctx.reply("🎨 Generating image, one sec...")

    try:
        png_bytes = await generate_image(prompt)
        file = discord.File(io.BytesIO(png_bytes), filename="image.png")
        await ctx.reply(file=file)
        await record_generated_image(ctx.author.id)
    except Exception as e:
        await ctx.reply(f"❌ Image generation failed: `{e}`")


@bot.command(name="analyzeimage")
async def analyze_image_command(ctx: commands.Context, *, extra_prompt: str = ""):
    """
    Analyze an attached image (ad, thumbnail, etc.)
    """
    if not ctx.message.attachments:
        await ctx.reply("Attach an image and run `!analyzeimage`.")
        return

    img = None
    for att in ctx.message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            img = att
            break
        if att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            img = att
            break

    if not img:
        await ctx.reply("I don't see an image attachment. Try again with a PNG/JPG/etc.")
        return

    await ctx.reply("🧐 Analyzing your image...")

    try:
        analysis = await analyze_image_with_gpt(img.url, extra_prompt)
        await ctx.reply(analysis)
        await increment_stat("stats:images_analyzed")
    except Exception as e:
        await ctx.reply(f"❌ Image analysis failed: `{e}`")


@bot.command(name="analyzepdf")
async def analyze_pdf_command(ctx: commands.Context):
    """
    Analyze an attached PDF (offer doc, deck, script, etc.)
    """
    if not ctx.message.attachments:
        await ctx.reply("Attach a PDF and run `!analyzepdf`.")
        return

    pdf = None
    for att in ctx.message.attachments:
        if att.filename.lower().endswith(".pdf"):
            pdf = att
            break
        if att.content_type == "application/pdf":
            pdf = att
            break

    if not pdf:
        await ctx.reply("I don't see a PDF attachment. Try again with a .pdf file.")
        return

    await ctx.reply("📄 Reading and analyzing your PDF...")

    try:
        data = await pdf.read()
        analysis = await analyze_pdf_bytes(data, pdf.filename)
        await ctx.reply(analysis)
        await increment_stat("stats:pdfs_analyzed")
    except Exception as e:
        await ctx.reply(f"❌ PDF analysis failed: `{e}`")



# ========= List Commands Command =====

@bot.command(name="commands")
async def commands_list(ctx: commands.Context):
    cmds = """
🧾 **Available Commands**

**General**
• `!start` — Creates your private AI thread  
• `!myinfo` — Shows what I remember about you  
• `!resetmemory` — Wipes your memory  

**AI Tools**
• `!image <prompt>` — Generate an image (50/day)  
• `!analyzeimage` — Analyze attached image  
• `!analyzepdf` — Analyze attached PDF  

**Audio (no command needed)**
• Drop a voice message or audio file in your AI thread → Transcription + correct analysis  
    - Detects: sales call, setter call, general question, faith question, marketing brainstorming  
    - Includes red-flag detection  

**Admin Only**
• `!inspectmemory @user` — View a user's memory

"""
    await ctx.reply(cmds)


# ========= AUDIO PROCESSING =========

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg", ".oga", ".webm", ".mp4")


def is_audio_attachment(att: discord.Attachment) -> bool:
    if att.content_type and att.content_type.startswith("audio/"):
        return True
    fname = att.filename.lower()
    return fname.endswith(AUDIO_EXTENSIONS)


async def classify_audio_intent(transcript: str) -> str:
    """
    Classifies the audio into one of these categories:
    - general_question
    - sales_call
    - setter_call
    - discovery_call
    - marketing_ideation
    - faith_question
    - personal_msg
    - other
    """

    prompt = f"""
You are an intent classification engine.

Classify this audio transcript into EXACTLY ONE of these categories:

- general_question   (user asking something, no call happening)
- sales_call         (rep speaking to a prospect)
- setter_call        (appointment setter calling a lead)
- discovery_call     (initial qualification call)
- marketing_ideation (user brainstorming content, ads, creative ideas)
- faith_question     (user asking biblical/spiritual questions)
- personal_msg       (casual personal message, stories, diary-style)
- other

Transcript:
\"\"\"{transcript[:6000]}\"\"\"

Respond with ONLY the category name, nothing else.
"""

    resp = client_openai.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt}
                ]
            }
        ]
    )

    label = resp.output[0].content[0].text.strip().lower()
    return label


async def process_audio_message(message: discord.Message, user_id: int):
    """
    Full upgraded audio pipeline:
    - Transcription
    - Intent classification
    - Route to correct handler
    """

    # 1. Grab the first audio attachment
    attachment = None
    for att in message.attachments:
        if is_audio_attachment(att):
            attachment = att
            break

    if not attachment:
        return

    await message.channel.send("🎧 Received your voice message. Transcribing...")

    try:
        audio_bytes = await attachment.read()
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = attachment.filename

        transcription = client_openai.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file,
        )
        text = transcription.text

        await message.channel.send("📝 Transcription done. Understanding your message...")
    except Exception as e:
        await message.channel.send(f"⚠️ Error transcribing audio: `{e}`")
        return

    # 2. Intent Classification
    try:
        intent = await classify_audio_intent(text)
    except Exception as e:
        await message.channel.send(f"⚠️ Error classifying audio: `{e}`")
        intent = "general_question"

    # 3. Route Based on Intent
    if intent in {"sales_call", "setter_call", "discovery_call"}:
        await message.channel.send("📞 Detected a call. Running call analysis...")

        analysis = await analyze_audio_transcript(text)

        await message.channel.send(analysis)
        await increment_stat("stats:audio_items_analyzed")
        await update_user_memory(user_id, text)
        return

    elif intent == "marketing_ideation":
        await message.channel.send("🎨 Detected marketing brainstorming. Analyzing...")

        marketing_prompt = f"""
User is brainstorming marketing/ads/creative ideas.

Transcript:
\"\"\"{text}\"\"\"

Give:
- creative directions
- hooks
- angles
- improvements
- examples and variations
"""
        resp = client_openai.responses.create(
            model="gpt-4.1-mini",
            input=[{
                "role": "user",
                "content": [{"type": "input_text", "text": marketing_prompt}]
            }]
        )
        reply = resp.output[0].content[0].text[:1900]

        await message.channel.send(reply)
        await update_user_memory(user_id, text)
        return

    elif intent == "faith_question":
        await message.channel.send("✝️ Detected faith-based question. Answering...")

        faith_prompt = f"""
User is asking a faith/biblical/spiritual question.

Transcript:
\"\"\"{text}\"\"\"

Respond as a Christian mentor, with scripture support.
"""
        resp = client_openai.responses.create(
            model="gpt-4.1-mini",
            input=[{
                "role": "user",
                "content": [{"type": "input_text", "text": faith_prompt}]
            }]
        )
        reply = resp.output[0].content[0].text[:1900]

        await message.channel.send(reply)
        return

    else:
        # Default: general question → treat it like a normal assistant chat
        await message.channel.send("🎤 Detected a general voice question. Answering your question...")

        openai_thread = await get_or_create_openai_thread(user_id)

        try:
            reply = await run_assistant(openai_thread, text)
            await message.channel.send(reply[:1900])
            await update_user_memory(user_id, text)
            await increment_stat("stats:audio_items_analyzed")
        except Exception as e:
            await message.channel.send(f"⚠️ Error answering your voice message: `{e}`")

@tasks.loop(time=time(hour=14, minute=0))  # ~8am CST = 14:00 UTC
async def daily_asana_checkin():
    """
    Runs once a day. For every user that has an Asana project + a thread,
    post their daily agenda.
    """
    if asana_client is None:
        return

    # You already have *some* way to know which users have threads / are in the program.
    # If you store user IDs in Redis or in a file, iterate over them here.
    # For now, we’ll assume a simple list `PROGRAM_USER_IDS` you maintain.
    from bot_config import PROGRAM_USER_IDS  # or replace with your own mechanism

    async with aiohttp.ClientSession() as session:
        for user_id in PROGRAM_USER_IDS:
            project_gid = asana_client.get_project_for_user(user_id)
            if not project_gid:
                continue

            # Get their thread/channel
            user = bot.get_user(user_id)
            if user is None:
                continue

            # You should replace this with however you fetch their private AI thread:
            # e.g. thread = await get_or_create_user_thread(user)
            # For now, just DM them:
            channel = user.dm_channel or await user.create_dm()

            agenda_text = await asana_client.build_daily_agenda(
                session=session,
                discord_user_id=user_id,
            )

            if agenda_text:
                try:
                    await channel.send(agenda_text)
                except Exception as e:
                    print(f"Failed to send daily Asana agenda to {user_id}: {e}")


# ========= AUTO-REPLY IN USER THREAD =========

@bot.event
async def on_message(message: discord.Message):
    # Let commands run first
    await bot.process_commands(message)

    if message.author.bot:
        return

    # Check if this channel is a mapped AI thread for this user
    user_thread_id = await get_user_discord_thread(message.author.id)
    if not user_thread_id or message.channel.id != user_thread_id:
        return

    # Ignore explicit commands inside the thread
    if message.content.startswith("!"):
        return

    # If there is audio attached, treat as call analysis
    if message.attachments and any(is_audio_attachment(att) for att in message.attachments):
        await process_audio_message(message, message.author.id)
        return

    # Otherwise, treat as normal chat to the Assistant
    text = message.content.strip()
    if not text and not message.attachments:
        return  # nothing to send

    await message.channel.typing()

    openai_thread_id = await get_or_create_openai_thread(message.author.id)

    # If user attached non-audio files without using specific commands,
    # just mention the available tools.
    if message.attachments and not text:
        await message.channel.send(
            "📎 I see a file. For images use `!analyzeimage` with the image attached, "
            "and for PDFs use `!analyzepdf` with the PDF attached.\n"
            "For now I'll ignore the file and just wait for your next message."
        )
        return

    try:
        reply = await run_assistant(openai_thread_id, text)
        # Shorten if needed
        if len(reply) > 1900:
            reply = reply[:1900] + "\n\n_(truncated)_"
        await message.channel.send(reply)

        # Update memory & analytics
        await update_user_memory(message.author.id, text)
        await increment_stat("stats:messages_handled")
    except Exception as e:
        await message.channel.send(f"⚠️ Error talking to the AI: `{e}`")


# ========= RUN =========

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
