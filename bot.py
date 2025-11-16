import os
import io
import json
import base64
import logging
import datetime as dt
from typing import Optional, Dict, Any, Tuple

import aiohttp
import discord
from discord.ext import commands, tasks
import redis.asyncio as redis
from openai import OpenAI

# ----------------- Basic config -----------------

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("derek-ai-bot")

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

ASANA_ACCESS_TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_TEMPLATE_GID = os.getenv("ASANA_TEMPLATE_GID")  # your template project GID

OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID")  # Derek's user ID as string

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN env var is required")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY env var is required")
if not OPENAI_ASSISTANT_ID:
    raise RuntimeError("OPENAI_ASSISTANT_ID env var is required")
if not OWNER_DISCORD_ID:
    raise RuntimeError("OWNER_DISCORD_ID env var is required (your Discord user ID)")

client_openai = OpenAI(api_key=OPENAI_API_KEY)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

bot = commands.Bot(command_prefix="!", intents=INTENTS)

# Per-day limits
MAX_IMAGES_PER_DAY = 50

# Redis key helpers
def k_user_thread(user_id: int) -> str:
    return f"user:{user_id}:thread_id"

def k_user_memory(user_id: int) -> str:
    return f"user:{user_id}:memory"

def k_user_meta(user_id: int) -> str:
    return f"user:{user_id}:meta"

def k_user_metrics(user_id: int) -> str:
    return f"user:{user_id}:metrics"

def k_user_asana(user_id: int) -> str:
    return f"user:{user_id}:asana"

def k_daily_image_count(date_str: str) -> str:
    return f"images:{date_str}:count"

def k_daily_image_user(date_str: str, user_id: int) -> str:
    return f"images:{date_str}:user:{user_id}"

def k_daily_checkin_date(user_id: int) -> str:
    return f"user:{user_id}:last_checkin_date"

def today_str_cst() -> str:
    # Just used for limits, not precision-critical
    return dt.datetime.utcnow().date().isoformat()

# -------------- OpenAI helpers -----------------


async def call_openai_assistant(messages: list[dict]) -> str:
    """
    Use the Responses API with your existing Assistant (knowledge bank, tools, etc).
    We also pass a short "memory" string from Redis as extra system context.
    """
    try:
        # Combine memory into system message if present
        # messages is already [{role, content}, ...] with user/system msgs
        response = client_openai.responses.create(
            model="gpt-4.1-mini",
            assistant_id=OPENAI_ASSISTANT_ID,
            input=messages,
        )
        # Responses API: first output_text item
        for out in response.output:
            if out.type == "message":
                for c in out.message.content:
                    if c.type == "output_text":
                        return c.output_text
        return "I had trouble generating a response, please try again."
    except Exception as e:
        log.exception("Error calling OpenAI Responses API")
        return f"⚠️ Error talking to the AI: `{e}`"


async def summarize_and_update_memory(user_id: int, new_message: str, ai_reply: str) -> None:
    """Keep a short 'memory' summary per user in Redis."""
    key = k_user_memory(user_id)
    old = await redis_client.get(key) or ""
    prompt = (
        "You are maintaining a short, running summary of a coaching client.\n"
        "Update the summary with any NEW, long-term relevant info "
        "(business model, offer, audience, goals, personality, etc).\n"
        "Keep it under 200 words.\n\n"
        f"Current summary:\n{old}\n\n"
        f"Latest user message:\n{new_message}\n\n"
        f"Your last reply:\n{ai_reply}\n\n"
        "Return ONLY the updated summary."
    )
    summary = await call_openai_assistant(
        [{"role": "system", "content": "Update the client summary based on the conversation."},
         {"role": "user", "content": prompt}]
    )
    await redis_client.set(key, summary)


async def transcribe_audio(discord_attachment: discord.Attachment) -> Optional[str]:
    """Download audio from Discord and send to OpenAI for transcription."""
    try:
        buf = io.BytesIO()
        await discord_attachment.save(buf)
        buf.seek(0)
        # Use new audio transcription endpoint
        transcript = client_openai.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=("audio.webm", buf, discord_attachment.content_type or "audio/webm"),
        )
        # transcript.text for new API
        return getattr(transcript, "text", None)
    except Exception as e:
        log.exception("Error transcribing audio")
        return None


async def analyze_call_transcript(transcript: str) -> str:
    """Sales/setting call analysis with red-flag buckets."""
    prompt = (
        "You're a ruthless sales coach for Christian agency owners and coaches.\n"
        "You are given a full transcript of a sales or setter call.\n\n"
        "1) Give a tight summary (3-7 bullet points).\n"
        "2) Score the caller on a 0-10 scale for:\n"
        "   - Discovery\n   - Qualification\n   - Objection handling\n   - Call control\n   - Closing\n"
        "3) List specific ACTION items they should do differently next time.\n"
        "4) Tag red-flags using ONLY these labels, if present:\n"
        "   💸 Budget flags\n"
        "   🟧 Timeline objections\n"
        "   😕 Uncertainty indicators\n"
        "   🚫 Bad fit warnings\n"
        "   🧊 Lead coldness signals\n"
        "   💀 “Never buying” traits\n"
        "5) At the end, give an overall verdict like 'Book them', 'Nurture', or 'Disqualify'.\n\n"
        "Return everything in clean Discord-friendly markdown.\n\n"
        f"Transcript:\n{transcript}"
    )
    result = await call_openai_assistant(
        [{"role": "user", "content": prompt}]
    )
    return result


async def coach_answer(user_id: int, user_message: str) -> str:
    """Normal Q&A coaching answer using your Assistant + stored memory."""
    memory = await redis_client.get(k_user_memory(user_id)) or ""
    meta_raw = await redis_client.get(k_user_meta(user_id))
    meta = json.loads(meta_raw) if meta_raw else {}

    system = (
        "You are Derek's AI coach for Christian agency owners and coaches.\n"
        "You:\n"
        "- Help with sales, setting, Meta ads, YouTube, organic, and business strategy.\n"
        "- Are strict but encouraging.\n"
        "- Keep answers practical and tailored to THIS user.\n\n"
        f"Client summary (from previous conversations and onboarding):\n{memory}\n\n"
        f"Onboarding data:\n{json.dumps(meta, indent=2)}"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    reply = await call_openai_assistant(messages)
    await summarize_and_update_memory(user_id, user_message, reply)
    return reply


# -------------- Asana integration (safe) ---------------

ASYNC_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def asana_duplicate_project_for_user(user_id: int, email: str, user_name: str) -> Optional[str]:
    """
    Try to duplicate your template project in Asana for this user.
    If anything fails, we log & return None (bot won't crash).
    We deliberately avoid 'schedule_dates' (that's what caused the 400 schedule_dates error).
    """
    if not ASANA_ACCESS_TOKEN or not ASANA_TEMPLATE_GID:
        log.info("Asana env vars not set, skipping Asana duplication.")
        return None

    url = f"https://app.asana.com/api/1.0/projects/{ASANA_TEMPLATE_GID}/duplicate"
    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    project_name = f"{user_name} – Coach AI Program"

    # Only allowed values from the error message list
    payload = {
        "data": {
            "name": project_name,
            "include": [
                "members",
                "notes",
                "task_assignee",
                "task_dates",
                "task_subtasks",
                "task_notes",
            ],
            # IMPORTANT: no 'schedule_dates' field here to avoid
            # "schedule_dates: Value is not an object" 400 error.
        }
    }

    try:
        async with aiohttp.ClientSession(timeout=ASYNC_HTTP_TIMEOUT) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status >= 300:
                    log.error("Asana duplicate error %s: %s", resp.status, text)
                    return None
                data = json.loads(text)
    except Exception as e:
        log.exception("Error talking to Asana")
        return None

    # Asana's duplicate endpoint returns a job; eventually a new project is created.
    # For simplicity we try to pull 'new_project' if present, else bail out
    try:
        new_project = data.get("data", {}).get("new_project")
        if new_project and "gid" in new_project:
            project_gid = new_project["gid"]
            asana_url = f"https://app.asana.com/0/{project_gid}/board"
            await redis_client.set(
                k_user_asana(user_id),
                json.dumps(
                    {
                        "email": email,
                        "project_gid": project_gid,
                        "project_url": asana_url,
                    }
                ),
            )
            return asana_url
    except Exception:
        log.exception("Failed to parse Asana duplicate response")

    return None


# -------------- Memory / metrics utilities --------------


async def get_user_meta(user_id: int) -> Dict[str, Any]:
    raw = await redis_client.get(k_user_meta(user_id))
    return json.loads(raw) if raw else {}


async def set_user_meta(user_id: int, meta: Dict[str, Any]) -> None:
    await redis_client.set(k_user_meta(user_id), json.dumps(meta))


async def inc_metric(user_id: int, field: str, amount: float = 1.0) -> None:
    key = k_user_metrics(user_id)
    metrics_raw = await redis_client.get(key)
    metrics = json.loads(metrics_raw) if metrics_raw else {}
    metrics[field] = metrics.get(field, 0) + amount
    await redis_client.set(key, json.dumps(metrics))


async def get_metrics(user_id: int) -> Dict[str, Any]:
    raw = await redis_client.get(k_user_metrics(user_id))
    return json.loads(raw) if raw else {}


# -------------- Discord helpers -----------------


async def get_or_create_private_thread(ctx: commands.Context) -> discord.Thread:
    """
    Each user gets exactly one private 'Derek AI – <name>' thread inside the channel where they used !start.
    We'll remember thread_id in Redis so we don't recreate.
    """
    key = k_user_thread(ctx.author.id)
    thread_id = await redis_client.get(key)
    if thread_id:
        thread = ctx.guild.get_thread(int(thread_id))
        if thread:
            return thread

    # Create new thread
    base_channel = ctx.channel
    thread_name = f"AI – {ctx.author.display_name}"
    thread = await base_channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.private_thread
        if isinstance(base_channel, discord.TextChannel)
        else discord.ChannelType.public_thread,
    )
    await thread.add_user(ctx.author)
    await redis_client.set(key, str(thread.id))
    return thread


async def ensure_owner(ctx: commands.Context) -> bool:
    """Check if the command runner is Derek."""
    if str(ctx.author.id) != str(OWNER_DISCORD_ID):
        await ctx.send("⚠️ Only Derek can run this command.")
        return False
    return True


# -------------- Onboarding flow -----------------


ONBOARDING_QUESTIONS = [
    ("niche", "Who are you serving? (niche / target market)"),
    ("offer", "What is your core offer? (what you sell & price range)"),
    ("revenue", "Where are you at right now monthly (rev & profit)?"),
    ("goal", "Where do you want to be 5–6 months from now?"),
    ("bottleneck", "What do YOU think is the biggest bottleneck right now?"),
    ("email", "What email should we use for your program & Asana?"),
]


async def run_onboarding(thread: discord.Thread, user: discord.Member) -> Dict[str, Any]:
    """
    Ask onboarding questions INSIDE the private AI thread.
    Returns meta dict saved for the user.
    """
    meta: Dict[str, Any] = {
        "discord_id": user.id,
        "discord_name": str(user),
        "created_at_utc": dt.datetime.utcnow().isoformat(),
    }

    await thread.send(
        f"Hey {user.mention} 👋\n"
        "Welcome to your private Derek AI thread.\n\n"
        "Before we dive in, I need a few quick questions so I can customize everything for you."
    )

    def check(m: discord.Message) -> bool:
        return m.author.id == user.id and m.channel.id == thread.id

    for key, question in ONBOARDING_QUESTIONS:
        await thread.send(question)
        try:
            msg = await bot.wait_for("message", timeout=600.0, check=check)
        except asyncio.TimeoutError:
            await thread.send("Timed out waiting for your answer. You can type `!start` again later.")
            return meta

        meta[key] = msg.content.strip()

    await set_user_meta(user.id, meta)

    # Attempt Asana project creation (safe)
    email = meta.get("email")
    if email:
        asana_url = await asana_duplicate_project_for_user(user.id, email, user.display_name)
        if asana_url:
            await thread.send(
                f"✅ I created an Asana board for you here (comment-level):\n{asana_url}\n\n"
                "Use this as your execution hub. I’ll keep you accountable to it."
            )
        else:
            await thread.send(
                "⚠️ I couldn’t auto-create your Asana board.\n"
                "Derek will set it up manually using your email and drop the link here. "
                "You can still start using this thread in the meantime."
            )

    await thread.send(
        "All set. From now on, anything you say **in this thread** (text or voice note) will go straight to the AI.\n"
        "You no longer need a command to talk to me here."
    )

    # Let Derek know a new client started
    owner = bot.get_user(int(OWNER_DISCORD_ID))
    if owner:
        try:
            await owner.send(
                f"🆕 New client onboarded: {user} ({user.id})\n"
                f"Email: {meta.get('email','N/A')}\n"
                f"Niche: {meta.get('niche','N/A')}\n"
                f"Goal: {meta.get('goal','N/A')}"
            )
        except Exception:
            log.exception("Failed to DM owner about new onboarding")

    return meta


# -------------- Commands -----------------


@bot.event
async def on_ready():
    log.info("Bot is ready — Logged in as %s", bot.user)
    daily_checkins.start()


@bot.command(name="start")
async def start_command(ctx: commands.Context):
    """Create/find the private AI thread and run onboarding if needed."""
    thread = await get_or_create_private_thread(ctx)

    # Check if we already have onboarding meta
    meta = await get_user_meta(ctx.author.id)
    if not meta.get("email"):
        await thread.send("Starting onboarding questions…")
        await run_onboarding(thread, ctx.author)
    else:
        await thread.send(
            f"Welcome back, {ctx.author.mention}! You’re already onboarded.\n"
            "You can just talk to me here—no command needed."
        )

    await ctx.reply(f"Your private AI thread is ready: {thread.mention}", mention_author=True)


@bot.command(name="image")
async def image_command(ctx: commands.Context, *, prompt: str):
    """Generate an image (counts toward 50/day global cap)."""
    today = today_str_cst()
    global_key = k_daily_image_count(today)
    user_key = k_daily_image_user(today, ctx.author.id)

    current_global = int(await redis_client.get(global_key) or 0)
    if current_global >= MAX_IMAGES_PER_DAY:
        await ctx.send("⚠️ Daily image limit reached. Try again tomorrow.")
        return

    await ctx.send("🎨 Generating image, one sec…")

    try:
        img_resp = client_openai.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            n=1,
            quality="high",
        )
        b64 = img_resp.data[0].b64_json
        binary = base64.b64decode(b64)
        file = discord.File(io.BytesIO(binary), filename="image.png")
        await ctx.send(file=file)
        await inc_metric(ctx.author.id, "images_generated", 1)
        await redis_client.incr(global_key)
        await redis_client.incr(user_key)
    except Exception as e:
        log.exception("Image generation failed")
        await ctx.send(f"❌ Image generation failed: `{e}`")


@bot.command(name="myinfo")
async def myinfo_command(ctx: commands.Context):
    """Show what the bot remembers & your usage stats."""
    memory = await redis_client.get(k_user_memory(ctx.author.id)) or "(no long-term summary yet)"
    meta = await get_user_meta(ctx.author.id)
    metrics = await get_metrics(ctx.author.id)
    asana_raw = await redis_client.get(k_user_asana(ctx.author.id))
    asana = json.loads(asana_raw) if asana_raw else None

    embed = discord.Embed(
        title="🧠 What I know about you",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Summary", value=memory[:1024], inline=False)
    embed.add_field(
        name="Onboarding data",
        value="```json\n" + json.dumps(meta, indent=2)[:1000] + "\n```",
        inline=False,
    )
    embed.add_field(
        name="Usage metrics",
        value="```json\n" + json.dumps(metrics, indent=2)[:1000] + "\n```",
        inline=False,
    )
    if asana and asana.get("project_url"):
        embed.add_field(
            name="Asana board",
            value=asana["project_url"],
            inline=False,
        )

    await ctx.send(embed=embed)


@bot.command(name="resetmemory")
async def resetmemory_command(ctx: commands.Context):
    """Soft reset: clear your AI memory & metrics but keep Asana link."""
    await redis_client.delete(k_user_memory(ctx.author.id))
    await redis_client.delete(k_user_metrics(ctx.author.id))
    # keep meta + Asana
    await ctx.send("🧼 Cleared your AI memory & metrics. We kept your onboarding + Asana.")


@bot.command(name="inspectmemory")
async def inspectmemory_command(ctx: commands.Context, member: discord.Member):
    """Admin: inspect another user's memory/meta/metrics."""
    if not await ensure_owner(ctx):
        return

    memory = await redis_client.get(k_user_memory(member.id)) or "(no summary)"
    meta = await get_user_meta(member.id)
    metrics = await get_metrics(member.id)
    asana_raw = await redis_client.get(k_user_asana(member.id))
    asana = json.loads(asana_raw) if asana_raw else None

    content = (
        f"Inspecting {member} ({member.id})\n\n"
        f"Summary:\n{memory}\n\n"
        f"Meta:\n```json\n{json.dumps(meta, indent=2)}\n```\n"
        f"Metrics:\n```json\n{json.dumps(metrics, indent=2)}\n```"
    )
    if asana:
        content += f"\nAsana:\n```json\n{json.dumps(asana, indent=2)}\n```"

    await ctx.send(content[:2000])


@bot.command(name="fullreset")
async def fullreset_command(ctx: commands.Context, member: discord.Member):
    """
    **Dangerous**: delete ALL stored data for a user (including Asana mapping),
    but DO NOT touch their Asana project itself.
    Only Derek can run this.
    """
    if not await ensure_owner(ctx):
        return

    uid = member.id

    # Fetch some info first for logging
    meta = await get_user_meta(uid)
    asana_raw = await redis_client.get(k_user_asana(uid))
    asana = json.loads(asana_raw) if asana_raw else None

    # Delete everything we store
    await redis_client.delete(k_user_thread(uid))
    await redis_client.delete(k_user_memory(uid))
    await redis_client.delete(k_user_meta(uid))
    await redis_client.delete(k_user_metrics(uid))
    await redis_client.delete(k_user_asana(uid))
    await redis_client.delete(k_daily_checkin_date(uid))

    await ctx.send(f"🧨 Completely reset stored data for {member.mention}. They’ll need to run `!start` again.")

    # DM Derek with audit info
    owner = bot.get_user(int(OWNER_DISCORD_ID))
    if owner:
        try:
            await owner.send(
                f"⚠️ FULL RESET EXECUTED\n"
                f"User: {member} ({uid})\n"
                f"Meta before reset:\n```json\n{json.dumps(meta, indent=2)}\n```\n"
                f"Asana mapping before reset:\n```json\n{json.dumps(asana, indent=2) if asana else 'None'}\n```"
            )
        except Exception:
            log.exception("Failed to DM owner about fullreset")


@bot.command(name="analyzecall")
async def analyzecall_command(ctx: commands.Context):
    """
    Analyze a sales/setting call recording attached to this command.
    """
    if not ctx.message.attachments:
        await ctx.send("Attach an audio file (or voice message) **to the same message** as `!analyzecall`.")
        return

    audio = ctx.message.attachments[0]
    await ctx.send("🎧 Received audio. Transcribing your call…")

    transcript = await transcribe_audio(audio)
    if not transcript:
        await ctx.send("❌ I couldn't transcribe that audio. Try again with a clearer file.")
        return

    await ctx.send("✏️ Transcription complete. Analyzing now…")

    analysis = await analyze_call_transcript(transcript)

    # Discord has a 2000 char limit
    if len(analysis) <= 2000:
        await ctx.send(analysis)
    else:
        # send as file
        buf = io.StringIO(analysis)
        file = discord.File(buf, filename="call-analysis.txt")
        await ctx.send("The analysis was long, so I put it in a file:", file=file)

    await inc_metric(ctx.author.id, "audio_minutes_analyzed", 5)  # rough guess


# -------------- Daily check-ins -----------------


@tasks.loop(minutes=10)
async def daily_checkins():
    """
    Every 10 minutes, check if it's ~8am CST and send a check-in to each onboarded user,
    once per day. (We just use date string tracking so it's simple.)
    """
    now_utc = dt.datetime.utcnow()
    # CST = UTC-6 (approx; we don't handle DST precisely here)
    hour_cst = (now_utc.hour - 6) % 24

    if hour_cst != 8:
        return

    today = now_utc.date().isoformat()

    # We don't have an easy way to list all users from Redis, so we rely on a
    # set of "known users" stored under a special key.
    known_key = "known_users"
    user_ids = await redis_client.smembers(known_key)
    if not user_ids:
        return

    for uid_str in user_ids:
        uid = int(uid_str)
        last = await redis_client.get(k_daily_checkin_date(uid))
        if last == today:
            continue  # already sent

        thread_id = await redis_client.get(k_user_thread(uid))
        if not thread_id:
            continue
        thread = bot.get_channel(int(thread_id))
        if not isinstance(thread, discord.Thread):
            continue

        meta = await get_user_meta(uid)
        goal = meta.get("goal", "Hit your next revenue level")
        msg = (
            f"📆 Daily check-in time.\n"
            f"Main goal (5–6 months): **{goal}**\n\n"
            "Reply here with:\n"
            "1) What you did yesterday\n"
            "2) The 1–3 most important actions you’ll do today\n"
            "3) Anything blocking you"
        )
        try:
            await thread.send(msg)
            await redis_client.set(k_daily_checkin_date(uid), today)
        except Exception:
            log.exception("Failed to send daily check-in to %s", uid)


# -------------- on_message: auto-AI in private threads --------------


@bot.event
async def on_message(message: discord.Message):
    # Let commands process first
    await bot.process_commands(message)

    if message.author.bot:
        return

    # Only auto-respond inside the user's private AI thread
    thread_key = k_user_thread(message.author.id)
    thread_id = await redis_client.get(thread_key)
    if not thread_id:
        return
    if str(message.channel.id) != str(thread_id):
        return

    # Ignore messages that are pure commands
    if message.content.startswith("!"):
        return

    await redis_client.sadd("known_users", str(message.author.id))

    # Check if this is an audio message (normal Q&A, not call review)
    if message.attachments:
        audio = message.attachments[0]
        if audio.content_type and audio.content_type.startswith("audio"):
            await message.channel.send("🎧 Got your voice note. Transcribing and replying…")
            transcript = await transcribe_audio(audio)
            if not transcript:
                await message.channel.send("❌ I couldn't transcribe that. Try again with a clearer recording.")
                return
            reply = await coach_answer(message.author.id, transcript)
            # Split if too long
            if len(reply) <= 2000:
                await message.channel.send(reply)
            else:
                for chunk_start in range(0, len(reply), 1900):
                    await message.channel.send(reply[chunk_start:chunk_start+1900])
            await inc_metric(message.author.id, "audio_minutes_qna", 2)
            return

    # Normal text question
    reply = await coach_answer(message.author.id, message.content)
    if len(reply) <= 2000:
        await message.channel.send(reply)
    else:
        for chunk_start in range(0, len(reply), 1900):
            await message.channel.send(reply[chunk_start:chunk_start+1900])

    await inc_metric(message.author.id, "messages_sent", 1)


# -------------- Run bot -----------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
