import os
import io
import json
import base64
import logging
import datetime as dt
import asyncio
from typing import Optional, Dict, Any, List

import aiohttp
import discord
from discord.ext import commands, tasks
import redis.asyncio as redis
from openai import OpenAI

# ============================================================
# BASIC CONFIG
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("derek-ai-bot")

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

REDIS_URL = os.getenv("REDIS_URL")

ASANA_ACCESS_TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_TEMPLATE_GID = os.getenv("ASANA_TEMPLATE_GID")  # your onboarding project GID

OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID")  # Derek's user ID as string

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN env var is required")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY env var is required")
if not OPENAI_ASSISTANT_ID:
    raise RuntimeError("OPENAI_ASSISTANT_ID env var is required")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL env var is required")
if not OWNER_DISCORD_ID:
    raise RuntimeError("OWNER_DISCORD_ID env var is required")

OWNER_DISCORD_ID_INT = int(OWNER_DISCORD_ID)

client_openai = OpenAI(api_key=OPENAI_API_KEY)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
# REDIS KEY HELPERS
# ============================================================

def k_user_thread(user_id: int) -> str:
    return f"user:{user_id}:thread_id"

def k_user_memory(user_id: int) -> str:
    return f"user:{user_id}:memory"

def k_user_meta(user_id: int) -> str:
    return f"user:{user_id}:meta"

def k_user_stats(user_id: int) -> str:
    return f"user:{user_id}:stats"

def k_onboarding_stage(user_id: int) -> str:
    return f"user:{user_id}:onboarding_stage"

def k_last_checkin(user_id: int) -> str:
    return f"user:{user_id}:last_checkin_date"

def k_asana_project(user_id: int) -> str:
    return f"user:{user_id}:asana_project_gid"

def today_str() -> str:
    return dt.date.today().isoformat()

# ============================================================
# STATS / MEMORY
# ============================================================

async def incr_stat(user_id: int, key: str, amount: int = 1):
    stats_key = k_user_stats(user_id)
    stats = await redis_client.hgetall(stats_key) or {}
    current = int(stats.get(key, 0))
    stats[key] = str(current + amount)
    await redis_client.hset(stats_key, mapping=stats)

async def get_stats(user_id: int) -> Dict[str, Any]:
    return await redis_client.hgetall(k_user_stats(user_id)) or {}

async def get_user_meta(user_id: int) -> Dict[str, Any]:
    raw = await redis_client.get(k_user_meta(user_id))
    return json.loads(raw) if raw else {}

async def set_user_meta(user_id: int, meta: Dict[str, Any]):
    await redis_client.set(k_user_meta(user_id), json.dumps(meta))

async def get_user_memory(user_id: int) -> str:
    mem = await redis_client.get(k_user_memory(user_id))
    return mem or ""

async def update_user_memory(user_id: int, summary: str):
    await redis_client.set(k_user_memory(user_id), summary)

# ============================================================
# OPENAI – ASSISTANT (THREADS API)
# ============================================================

async def call_openai_assistant(messages: List[Dict[str, str]]) -> str:
    """
    Use your dashboard Assistant via Threads API.
    messages: [{"role": "system"/"user", "content": "..."}]
    """
    try:
        combined = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            combined.append(f"{role.upper()}:\n{content}")
        full_text = "\n\n".join(combined)

        thread = client_openai.beta.threads.create()
        client_openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=full_text,
        )
        run = client_openai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=OPENAI_ASSISTANT_ID,
        )
        msgs = client_openai.beta.threads.messages.list(
            thread_id=thread.id,
            order="desc",
            limit=1,
        )

        for msg in msgs.data:
            chunks = []
            for c in msg.content:
                if getattr(c, "type", None) == "text":
                    chunks.append(c.text.value)
            if chunks:
                return "\n".join(chunks)

        return "I couldn't generate a response — try again."
    except Exception as e:
        log.exception("Assistant error")
        return f"⚠️ AI error: `{e}`"

# ============================================================
# SUMMARY UPDATER
# ============================================================

async def summarize_and_update_memory(user_id: int, user_message: str, ai_reply: str):
    old_summary = await get_user_memory(user_id)
    prompt = (
        "You maintain a concise, running summary of a coaching client.\n"
        "Include: niche, offer, stage, goals, recurring problems, personality signals.\n"
        "Keep under 200 words.\n\n"
        f"Old summary:\n{old_summary}\n\n"
        f"User message:\n{user_message}\n\n"
        f"Your reply:\n{ai_reply}\n\n"
        "Return ONLY the new summary."
    )
    summary = await call_openai_assistant(
        [
            {"role": "system", "content": "Update the client summary."},
            {"role": "user", "content": prompt},
        ]
    )
    await update_user_memory(user_id, summary)

# ============================================================
# IMAGE GENERATION – 50/DAY PER USER
# ============================================================

async def generate_image(prompt: str, user_id: int) -> Optional[bytes]:
    today_key = f"images:{user_id}:{today_str()}"
    current = int((await redis_client.get(today_key)) or 0)
    if current >= 50:
        return None

    try:
        resp = client_openai.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        b64 = resp.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        await redis_client.set(today_key, str(current + 1))
        await incr_stat(user_id, "images_generated", 1)
        return img_bytes
    except Exception:
        log.exception("Image generation failed")
        return None

# ============================================================
# AUDIO TRANSCRIPTION + CALL ANALYSIS
# ============================================================

async def transcribe_audio(attachment: discord.Attachment) -> Optional[str]:
    try:
        buf = io.BytesIO()
        await attachment.save(buf)
        buf.seek(0)
        transcript = client_openai.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=("audio.webm", buf, attachment.content_type or "audio/webm"),
        )
        return getattr(transcript, "text", None)
    except Exception:
        log.exception("Transcription error")
        return None

async def analyze_call_transcript(transcript: str) -> str:
    prompt = (
        "You are a ruthless but fair sales coach for Christian agency owners and coaches.\n"
        "You are given a full transcription of a sales or setter call.\n\n"
        "Do the following:\n"
        "1) Give a tight summary (3-7 bullet points).\n"
        "2) Score the caller 0-10 on:\n"
        "   - Discovery\n   - Qualification\n   - Objection handling\n"
        "   - Call control\n   - Closing\n"
        "3) List specific ACTION items.\n"
        "4) Tag red flags using ONLY these if present:\n"
        "   💸 Budget flags\n"
        "   🟧 Timeline objections\n"
        "   😕 Uncertainty indicators\n"
        "   🚫 Bad fit warnings\n"
        "   🧊 Lead coldness signals\n"
        "   💀 “Never buying” traits\n"
        "5) Give an overall verdict: 'Book them', 'Nurture', or 'Disqualify'.\n\n"
        f"Transcript:\n{transcript}"
    )
    return await call_openai_assistant(
        [{"role": "user", "content": prompt}]
    )

# ============================================================
# COACH ANSWER (AFTER ONBOARDING)
# ============================================================

async def coach_answer(user_id: int, user_message: str) -> str:
    meta = await get_user_meta(user_id)
    memory = await get_user_memory(user_id)

    system = (
        "You are Derek's AI coach for Christian agency owners and coaches.\n"
        "You help with: sales, setting, Meta ads, YouTube, organic, systems, and scaling.\n"
        "You are strict but encouraging and very practical.\n\n"
        f"Client summary:\n{memory}\n\n"
        f"Onboarding data:\n{json.dumps(meta, indent=2)}"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    reply = await call_openai_assistant(messages)
    await summarize_and_update_memory(user_id, user_message, reply)
    await incr_stat(user_id, "messages_answered", 1)
    return reply

# ============================================================
# ASANA — DUPLICATE PROJECT + RELATIVE DUE DATES
# ============================================================

async def asana_apply_relative_due_dates(project_gid: str):
    """
    Reads sections in the duplicated project, infers day offsets from section names, and
    sets real calendar due dates for each task.

    Section naming rules (in Asana):
      - "On project start date" -> offset 0
      - "2 days after"          -> offset 2
      - "3 days after"          -> offset 3
      - "5 days after"          -> offset 5
      - "6 days after"          -> offset 6
      - "Day 1", "Day 2", etc.  -> offset = day - 1
    """

    if not ASANA_ACCESS_TOKEN:
        log.info("Asana token not set; skipping due date application.")
        return

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    base_url = "https://app.asana.com/api/1.0"
    start_date = dt.date.today()

    async with aiohttp.ClientSession() as session:
        # Fetch sections
        sections_url = f"{base_url}/projects/{project_gid}/sections"
        async with session.get(sections_url, headers=headers) as resp:
            sections_data = await resp.json()
            if resp.status >= 300:
                log.error("Asana sections error %s: %s", resp.status, sections_data)
                return
        sections = sections_data.get("data", [])

        section_offsets: Dict[str, int] = {}
        for sec in sections:
            name = sec.get("name", "").lower()
            gid = sec["gid"]
            offset = 0

            if "on project start date" in name:
                offset = 0
            elif "days after" in name:
                # e.g. "2 days after"
                try:
                    num = int(name.split("days after")[0].strip())
                    offset = num
                except Exception:
                    offset = 0
            elif name.startswith("day "):
                # e.g. "Day 3"
                try:
                    num = int(name.replace("day", "").strip())
                    offset = max(num - 1, 0)
                except Exception:
                    offset = 0

            section_offsets[gid] = offset

        # Fetch tasks in project
        tasks_url = f"{base_url}/tasks?project={project_gid}&limit=100&opt_fields=name,memberships.section"
        async with session.get(tasks_url, headers=headers) as resp:
            tasks_data = await resp.json()
            if resp.status >= 300:
                log.error("Asana tasks error %s: %s", resp.status, tasks_data)
                return
        tasks = tasks_data.get("data", [])

        # Apply due dates
        for task in tasks:
            task_gid = task["gid"]
            name = task.get("name", "")
            memberships = task.get("memberships", [])
            if not memberships:
                continue
            section = memberships[0].get("section")
            if not section:
                continue
            sec_gid = section.get("gid")
            if not sec_gid or sec_gid not in section_offsets:
                continue

            offset_days = section_offsets[sec_gid]
            due_date = start_date + dt.timedelta(days=offset_days)
            due_str = due_date.isoformat()

            update_url = f"{base_url}/tasks/{task_gid}"
            payload = {"data": {"due_on": due_str}}

            try:
                async with session.put(update_url, headers=headers, json=payload) as uresp:
                    if uresp.status >= 300:
                        body = await uresp.text()
                        log.error("Failed to set due date for task %s: %s %s", name, uresp.status, body)
                    else:
                        log.info("Set due date for '%s' -> %s", name, due_str)
            except Exception:
                log.exception("Error updating Asana task due date")

async def asana_duplicate_project_for_user(user_id: int, email: str, name: str) -> Optional[str]:
    """
    Duplicate ASANA_TEMPLATE_GID as a new project:
    - Uses your template project
    - Applies relative due dates
    - Adds client as comment-only guest
    - Stores project GID in Redis
    """
    if not ASANA_ACCESS_TOKEN or not ASANA_TEMPLATE_GID:
        log.info("Asana env vars not set, skipping Asana duplication.")
        return None

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    base_url = "https://app.asana.com/api/1.0"
    url = f"{base_url}/projects/{ASANA_TEMPLATE_GID}/duplicate"
    payload = {
        "data": {
            "name": f"{name} – Program Board",
            "include": [
                "members",
                "notes",
                "task_subtasks",
                "task_notes",
            ],
        }
    }

    new_project_gid: Optional[str] = None

    try:
        async with aiohttp.ClientSession() as session:
            # Duplicate project
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if resp.status >= 300:
                    log.error("Asana duplicate error %s: %s", resp.status, data)
                    return None

            new_project = data.get("data", {}).get("new_project")
            if new_project and "gid" in new_project:
                new_project_gid = new_project["gid"]
            else:
                log.error("Asana response missing new_project gid: %s", data)
                return None

            # Apply relative due dates based on sections
            await asana_apply_relative_due_dates(new_project_gid)

            # Add client as comment-only guest (best-effort)
            try:
                membership_url = f"{base_url}/project_memberships"
                membership_payload = {
                    "data": {
                        "project": new_project_gid,
                        "user": email,
                        "role": "comment_only"
                    }
                }
                async with session.post(membership_url, headers=headers, json=membership_payload) as mresp:
                    if mresp.status >= 300:
                        mbody = await mresp.text()
                        log.warning("Asana membership add failed %s: %s", mresp.status, mbody)
            except Exception:
                log.exception("Failed to add Asana comment-only membership")

    except Exception:
        log.exception("Asana duplication flow failed")
        return None

    if new_project_gid:
        await redis_client.set(k_asana_project(user_id), new_project_gid)
        return f"https://app.asana.com/0/{new_project_gid}/list"

    return None

# ============================================================
# STRICT ONBOARDING
# ============================================================

ONBOARDING_QUESTIONS = [
    ("niche", "1️⃣ Who do you serve? (niche / target market)"),
    ("offer", "2️⃣ What is your core offer? (deliverables + price range)"),
    ("revenue", "3️⃣ Where are you right now monthly? (revenue + profit)"),
    ("goal", "4️⃣ Where do you want to be 5–6 months from now?"),
    ("bottleneck", "5️⃣ What do YOU believe is the biggest bottleneck right now?"),
    ("email", "6️⃣ What email should I use to create your Asana program board?"),
]

async def run_onboarding(thread: discord.Thread, user: discord.Member) -> Dict[str, Any]:
    """
    STRICT MODE:
    - Bot ONLY asks onboarding questions.
    - No coaching or extra commentary.
    - After last answer: Asana board + unlock coaching.
    """
    meta: Dict[str, Any] = {
        "discord_id": user.id,
        "discord_name": str(user),
        "created_at_utc": dt.datetime.utcnow().isoformat(),
        "onboarding_complete": False,
    }

    await thread.send(
        f"Hey {user.mention} 👋\n"
        "Welcome to your private Derek AI thread.\n\n"
        "**STRICT ONBOARDING MODE** is active.\n"
        "I will ONLY ask onboarding questions.\n"
        "I will NOT coach or reply to anything else until we're finished.\n\n"
        "Let's start."
    )

    await redis_client.set(k_onboarding_stage(user.id), "1")

    def check(msg: discord.Message) -> bool:
        return msg.author.id == user.id and msg.channel.id == thread.id

    stage = 1
    for key, question in ONBOARDING_QUESTIONS:
        await redis_client.set(k_onboarding_stage(user.id), str(stage))
        await thread.send(question)

        try:
            msg = await bot.wait_for("message", timeout=900.0, check=check)
        except asyncio.TimeoutError:
            await thread.send(
                "⏳ You took too long.\n"
                "Type `!start` later to restart onboarding."
            )
            await redis_client.delete(k_onboarding_stage(user.id))
            return meta

        meta[key] = msg.content.strip()
        stage += 1

    await redis_client.delete(k_onboarding_stage(user.id))
    meta["onboarding_complete"] = True
    await set_user_meta(user.id, meta)

    email = meta.get("email")
    if email:
        asana_url = await asana_duplicate_project_for_user(user.id, email, user.display_name)
        if asana_url:
            await thread.send(
                f"✅ Your Asana program board is ready:\n{asana_url}\n\n"
                "You'll use this for execution & accountability."
            )
        else:
            await thread.send(
                "⚠️ I couldn't automatically create your Asana board.\n"
                "Derek will set it up manually."
            )

    await thread.send(
        "🎉 **Onboarding complete!**\n"
        "From now on, anything you say in this thread (text or voice) goes straight to the AI.\n"
        "No more commands needed."
    )

    owner = bot.get_user(OWNER_DISCORD_ID_INT)
    if owner:
        try:
            await owner.send(
                f"🆕 New client onboarded: {user} ({user.id})\n"
                f"Email: {meta.get('email','N/A')}\n"
                f"Goal: {meta.get('goal','N/A')}"
            )
        except Exception:
            log.exception("Failed to DM owner about onboarding")

    return meta

# ============================================================
# DISCORD HELPERS
# ============================================================

async def ensure_owner(ctx: commands.Context) -> bool:
    if ctx.author.id != OWNER_DISCORD_ID_INT:
        await ctx.send("⚠️ Only Derek can run this command.")
        return False
    return True

async def get_or_create_private_thread(ctx: commands.Context) -> discord.Thread:
    existing_id = await redis_client.get(k_user_thread(ctx.author.id))
    if existing_id:
        t = ctx.guild.get_thread(int(existing_id))
        if t:
            return t

    base_channel = ctx.channel
    thread_name = f"AI – {ctx.author.display_name}"
    thread = await base_channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.private_thread
        if isinstance(base_channel, discord.TextChannel)
        else discord.ChannelType.public_thread,
    )
    await thread.add_user(ctx.author)
    await redis_client.set(k_user_thread(ctx.author.id), str(thread.id))
    return thread

# ============================================================
# COMMANDS
# ============================================================

@bot.event
async def on_ready():
    log.info("Bot ready as %s", bot.user)
    daily_checkins.start()

@bot.command(name="start")
async def start_command(ctx: commands.Context):
    """Create/find the private AI thread and run onboarding if needed."""
    thread = await get_or_create_private_thread(ctx)
    meta = await get_user_meta(ctx.author.id)

    if not meta.get("onboarding_complete"):
        await thread.send("Starting onboarding now…")
        await run_onboarding(thread, ctx.author)
    else:
        await thread.send(
            f"Welcome back, {ctx.author.mention}!\n"
            "You’re already onboarded. Just talk to me here."
        )

    await ctx.reply(f"Your private AI thread: {thread.mention}", mention_author=True)

@bot.command(name="image")
async def image_command(ctx: commands.Context, *, prompt: str):
    img_bytes = await generate_image(prompt, ctx.author.id)
    if img_bytes is None:
        await ctx.send("⚠️ You hit your 50 images for today. Try again tomorrow.")
        return
    file = discord.File(io.BytesIO(img_bytes), filename="image.png")
    await ctx.send(file=file)

@bot.command(name="myinfo")
async def myinfo_command(ctx: commands.Context):
    meta = await get_user_meta(ctx.author.id)
    mem = await get_user_memory(ctx.author.id) or "(no summary yet)"
    stats = await get_stats(ctx.author.id)

    embed = discord.Embed(
        title="🧠 What I know about you",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Summary", value=mem[:1024], inline=False)
    embed.add_field(
        name="Onboarding data",
        value="```json\n" + json.dumps(meta, indent=2)[:1000] + "\n```",
        inline=False,
    )
    embed.add_field(
        name="Stats",
        value="```json\n" + json.dumps(stats, indent=2)[:1000] + "\n```",
        inline=False,
    )
    await ctx.send(embed=embed)

@bot.command(name="resetmemory")
async def resetmemory_command(ctx: commands.Context):
    await redis_client.delete(k_user_memory(ctx.author.id))
    await redis_client.delete(k_user_stats(ctx.author.id))
    await ctx.send("🧼 Cleared your AI memory & stats. Onboarding data stays.")

@bot.command(name="inspectmemory")
async def inspectmemory_command(ctx: commands.Context, member: discord.Member):
    if not await ensure_owner(ctx):
        return

    meta = await get_user_meta(member.id)
    mem = await get_user_memory(member.id)
    stats = await get_stats(member.id)

    content = (
        f"Inspecting {member} ({member.id})\n\n"
        f"Summary:\n{mem}\n\n"
        f"Meta:\n```json\n{json.dumps(meta, indent=2)}\n```\n"
        f"Stats:\n```json\n{json.dumps(stats, indent=2)}\n```"
    )
    await ctx.send(content[:2000])

@bot.command(name="fullreset")
async def fullreset_command(ctx: commands.Context):
    if not await ensure_owner(ctx):
        return

    await ctx.send("🧨 Who do you want to full-reset? Mention them, or type `cancel`.")

    def check(msg: discord.Message) -> bool:
        return msg.author.id == ctx.author.id and msg.channel.id == ctx.channel.id

    try:
        msg = await bot.wait_for("message", timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Timed out.")
        return

    if msg.content.lower() == "cancel":
        await ctx.send("Cancelled.")
        return

    if not msg.mentions:
        await ctx.send("You must @mention a user.")
        return

    target = msg.mentions[0]

    await ctx.send(
        f"⚠️ This will erase ALL stored data for {target.mention}.\n"
        "Type `CONFIRM` to continue, or anything else to cancel."
    )

    try:
        confirm = await bot.wait_for("message", timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("Timed out.")
        return

    if confirm.content.strip().upper() != "CONFIRM":
        await ctx.send("Cancelled.")
        return

    uid = target.id
    meta = await get_user_meta(uid)
    mem = await get_user_memory(uid)
    stats = await get_stats(uid)

    await redis_client.delete(k_user_meta(uid))
    await redis_client.delete(k_user_memory(uid))
    await redis_client.delete(k_user_stats(uid))
    await redis_client.delete(k_user_thread(uid))
    await redis_client.delete(k_onboarding_stage(uid))
    await redis_client.delete(k_last_checkin(uid))
    await redis_client.delete(k_asana_project(uid))

    await ctx.send(f"🧨 Full reset done for {target.mention}.")

    owner = bot.get_user(OWNER_DISCORD_ID_INT)
    if owner:
        try:
            await owner.send(
                f"FULL RESET for {target} ({uid})\n"
                f"Meta:\n```json\n{json.dumps(meta, indent=2)}\n```\n"
                f"Memory:\n{mem}\n\n"
                f"Stats:\n```json\n{json.dumps(stats, indent=2)}\n```"
            )
        except Exception:
            log.exception("Failed to DM owner about reset")

@bot.command(name="analyzecall")
async def analyzecall_command(ctx: commands.Context):
    if not ctx.message.attachments:
        await ctx.send("Attach an audio file to the same message as `!analyzecall`.")
        return

    attachment = ctx.message.attachments[0]
    await ctx.send("🎧 Transcribing your call…")

    text = await transcribe_audio(attachment)
    if not text:
        await ctx.send("❌ Could not transcribe that audio.")
        return

    await ctx.send("✏️ Analyzing…")

    analysis = await analyze_call_transcript(text)
    if len(analysis) <= 2000:
        await ctx.send(analysis)
    else:
        buf = io.StringIO(analysis)
        file = discord.File(buf, filename="call-analysis.txt")
        await ctx.send("The analysis is long, so I put it in a file:", file=file)

    await incr_stat(ctx.author.id, "audio_minutes_analyzed", 5)

# ============================================================
# DAILY CHECK-INS (~8AM CST)
# ============================================================

@tasks.loop(minutes=10)
async def daily_checkins():
    now_utc = dt.datetime.utcnow()
    hour_cst = (now_utc.hour - 6) % 24
    if hour_cst != 8:
        return

    today = now_utc.date().isoformat()

    keys = await redis_client.keys("user:*:meta")
    for key in keys:
        try:
            uid = int(key.split(":")[1])
        except Exception:
            continue

        last = await redis_client.get(k_last_checkin(uid))
        if last == today:
            continue

        thread_id = await redis_client.get(k_user_thread(uid))
        if not thread_id:
            continue

        channel = bot.get_channel(int(thread_id))
        if not isinstance(channel, discord.Thread):
            continue

        meta = await get_user_meta(uid)
        goal = meta.get("goal", "Hit your next target")

        msg = (
            "📆 **Daily Check-In**\n"
            f"Main 5–6 month goal: **{goal}**\n\n"
            "Reply with:\n"
            "1) What you did yesterday\n"
            "2) Top 1–3 actions for today\n"
            "3) Anything blocking you"
        )

        try:
            await channel.send(msg)
            await redis_client.set(k_last_checkin(uid), today)
        except Exception:
            log.exception("Check-in send failed")

# ============================================================
# AUTO-AI REPLIES IN PRIVATE THREAD (STRICT ONBOARDING AWARE)
# ============================================================

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    # If onboarding is in progress, ignore free messages (only run_onboarding consumes them)
    stage = await redis_client.get(k_onboarding_stage(message.author.id))
    if stage:
        return

    # Only auto-respond in user's private thread
    thread_id = await redis_client.get(k_user_thread(message.author.id))
    if not thread_id:
        return
    if str(message.channel.id) != str(thread_id):
        return

    # Ignore commands here
    if message.content.startswith("!"):
        return

    meta = await get_user_meta(message.author.id)
    if not meta.get("onboarding_complete"):
        # safety guard (shouldn't normally happen)
        return

    # Voice note?
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.content_type and attachment.content_type.startswith("audio"):
            await message.channel.send("🎧 Got your voice note. Transcribing + replying…")
            text = await transcribe_audio(attachment)
            if not text:
                await message.channel.send("❌ Couldn't transcribe that. Try again.")
                return
            reply = await coach_answer(message.author.id, text)
            if len(reply) <= 2000:
                await message.channel.send(reply)
            else:
                for i in range(0, len(reply), 1900):
                    await message.channel.send(reply[i:i+1900])
            await incr_stat(message.author.id, "audio_minutes_qna", 2)
            return

    # Normal text coaching
    reply = await coach_answer(message.author.id, message.content)
    if len(reply) <= 2000:
        await message.channel.send(reply)
    else:
        for i in range(0, len(reply), 1900):
            await message.channel.send(reply[i:i+1900])

# ============================================================
# RUN BOT
# ============================================================

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
