# ============================================================
# DEREK AI BOT – WITH FULL TYPING SUPPORT (Option A)
# ============================================================

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
ASANA_TEMPLATE_GID = os.getenv("ASANA_TEMPLATE_GID")

OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID")

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
# REDIS KEYS
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
    return f"user:{user_id}:last_checkin"

def k_asana_project(user_id: int) -> str:
    return f"user:{user_id}:asana_project"

def today_str() -> str:
    return dt.date.today().isoformat()

# ============================================================
# STATS / MEMORY
# ============================================================

async def incr_stat(user_id: int, key: str, amount: int = 1):
    stats_key = k_user_stats(user_id)
    stats = await redis_client.hgetall(stats_key) or {}
    stats[key] = str(int(stats.get(key, 0)) + amount)
    await redis_client.hset(stats_key, mapping=stats)

async def get_stats(user_id: int):
    return await redis_client.hgetall(k_user_stats(user_id)) or {}

async def get_user_meta(user_id: int):
    raw = await redis_client.get(k_user_meta(user_id))
    return json.loads(raw) if raw else {}

async def set_user_meta(user_id: int, meta: Dict[str, Any]):
    await redis_client.set(k_user_meta(user_id), json.dumps(meta))

async def get_user_memory(user_id: int):
    mem = await redis_client.get(k_user_memory(user_id))
    return mem or ""

async def update_user_memory(user_id: int, summary: str):
    await redis_client.set(k_user_memory(user_id), summary)

# ============================================================
# THREAD-SAFE OPENAI WRAPPERS
# ============================================================

def _openai_call_assistant(messages):
    thread = client_openai.beta.threads.create()
    client_openai.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="\n\n".join([f"{m['role'].upper()}:\n{m['content']}" for m in messages])
    )
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=OPENAI_ASSISTANT_ID,
    )
    msgs = client_openai.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

    for msg in msgs.data:
        out = []
        for c in msg.content:
            if getattr(c, "type", None) == "text":
                out.append(c.text.value)
        if out:
            return "\n".join(out)
    return "I couldn't generate a response."

async def call_openai_assistant(messages):
    return await asyncio.to_thread(_openai_call_assistant, messages)

# ============================================================
# IMAGE GEN – THREAD SAFE
# ============================================================

def _generate_image_sync(prompt: str):
    resp = client_openai.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    return base64.b64decode(resp.data[0].b64_json)

async def generate_image(prompt: str, user_id: int) -> Optional[bytes]:
    today_key = f"images:{user_id}:{today_str()}"
    current = int((await redis_client.get(today_key)) or 0)
    if current >= 50:
        return None
    try:
        img = await asyncio.to_thread(_generate_image_sync, prompt)
        await redis_client.set(today_key, str(current + 1))
        await incr_stat(user_id, "images_generated", 1)
        return img
    except Exception:
        log.exception("Image generation failed")
        return None

# ============================================================
# TRANSCRIPTION – THREAD SAFE
# ============================================================

def _transcribe_sync(filename: str, raw: bytes):
    buf = io.BytesIO(raw)
    buf.name = filename
    result = client_openai.audio.transcriptions.create(
        file=buf,
        model="gpt-4o-mini-transcribe",
        response_format="text"
    )
    return result

async def transcribe_audio(attachment):
    raw = await attachment.read()
    if not raw:
        return None

    filename = attachment.filename or "audio.m4a"

    try:
        return await asyncio.to_thread(_transcribe_sync, filename, raw)
    except Exception:
        log.exception("Transcription error")
        return None

# ============================================================
# CALL ANALYSIS
# ============================================================

async def analyze_call_transcript(transcript: str) -> str:
    prompt = (
        "You are a ruthless but fair sales coach for Christian agency owners.\n"
        "Analyze the transcript:\n\n" + transcript
    )
    return await call_openai_assistant([{"role": "user", "content": prompt}])

# ============================================================
# COACH ANSWER
# ============================================================

async def coach_answer(user_id: int, user_message: str) -> str:
    meta = await get_user_meta(user_id)
    memory = await get_user_memory(user_id)

    sys = (
        "You are Derek's AI coach for Christian agency owners.\n"
        "Be practical, strict, clear.\n\n"
        f"Memory:\n{memory}\n\nOnboarding:\n{json.dumps(meta, indent=2)}"
    )
    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": user_message},
    ]
    reply = await call_openai_assistant(messages)
    await summarize_and_update_memory(user_id, user_message, reply)
    await incr_stat(user_id, "messages_answered", 1)
    return reply

# ============================================================
# ASANA – THREAD SAFE WRAPPERS + TYPING SUPPORT
# ============================================================

async def _async_get(session, url, headers):
    async with session.get(url, headers=headers) as resp:
        return resp.status, await resp.json()

async def _async_put(session, url, headers, payload):
    async with session.put(url, headers=headers, json=payload) as resp:
        return resp.status, await resp.text()

async def _async_post(session, url, headers, payload):
    async with session.post(url, headers=headers, json=payload) as resp:
        return resp.status, await resp.json()

# (Part 2 contains Asana duplication + onboarding + message handlers)

# ============================================================
# ASANA DUPLICATION + RELATIVE DATES  (continues from Part 1)
# ============================================================

async def asana_apply_relative_due_dates(project_gid: str):
    if not ASANA_ACCESS_TOKEN:
        return

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    base = "https://app.asana.com/api/1.0"
    start = dt.date.today()

    async with aiohttp.ClientSession() as session:
        # Fetch sections
        sec_url = f"{base}/projects/{project_gid}/sections"
        code, data = await _async_get(session, sec_url, headers)
        if code >= 300:
            log.error("Asana sections error: %s %s", code, data)
            return

        offsets = {}
        for sec in data.get("data", []):
            name = sec["name"].lower()
            gid = sec["gid"]

            if "on project start date" in name:
                offsets[gid] = 0
            elif "days after" in name:
                try:
                    num = int(name.split("days after")[0].strip())
                    offsets[gid] = num
                except:
                    offsets[gid] = 0
            elif name.startswith("day "):
                try:
                    num = int(name.split("day")[1])
                    offsets[gid] = max(num - 1, 0)
                except:
                    offsets[gid] = 0
            else:
                offsets[gid] = 0

        # Fetch tasks
        task_url = f"{base}/tasks?project={project_gid}&limit=100&opt_fields=name,memberships.section"
        code, tdata = await _async_get(session, task_url, headers)
        if code >= 300:
            log.error("Asana tasks error: %s %s", code, tdata)
            return

        for task in tdata.get("data", []):
            t_gid = task["gid"]
            sect = task.get("memberships", [{}])[0].get("section", {})
            s_gid = sect.get("gid")
            if s_gid not in offsets:
                continue

            due = (start + dt.timedelta(days=offsets[s_gid])).isoformat()
            up_url = f"{base}/tasks/{t_gid}"
            payload = {"data": {"due_on": due}}

            code, body = await _async_put(session, up_url, headers, payload)
            if code >= 300:
                log.error("Asana due date update error %s: %s", code, body)
            else:
                log.info("Set task due date: %s -> %s", task["name"], due)


async def asana_duplicate_project_for_user(user_id: int, email: str, name: str) -> Optional[str]:
    if not ASANA_ACCESS_TOKEN or not ASANA_TEMPLATE_GID:
        return None

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    base = "https://app.asana.com/api/1.0"

    payload = {
        "data": {
            "name": f"{name} – Program Board",
            "include": ["members", "notes", "task_subtasks", "task_notes"],
        }
    }

    async with aiohttp.ClientSession() as session:
        # Duplicate project
        dup_url = f"{base}/projects/{ASANA_TEMPLATE_GID}/duplicate"
        code, data = await _async_post(session, dup_url, headers, payload)
        if code >= 300:
            log.error("Asana duplicate error: %s %s", code, data)
            return None

        new = data.get("data", {}).get("new_project", {})
        new_gid = new.get("gid")
        if not new_gid:
            return None

        # Apply due dates
        await asana_apply_relative_due_dates(new_gid)

        # Add user as viewer/comment-only
        try:
            mem_url = f"{base}/project_memberships"
            mem_payload = {
                "data": {
                    "project": new_gid,
                    "user": email,
                    "role": "comment_only"
                }
            }
            code, data = await _async_post(session, mem_url, headers, mem_payload)
        except Exception:
            pass

        await redis_client.set(k_asana_project(user_id), new_gid)
        return f"https://app.asana.com/0/{new_gid}/list"

# ============================================================
# SUMMARIZER
# ============================================================

async def summarize_and_update_memory(user_id: int, user_message: str, ai_reply: str):
    old = await get_user_memory(user_id)
    prompt = (
        "Update the concise coaching-client summary (<200 words).\n"
        "Keep niche, offer, goals, pain points, patterns.\n\n"
        f"OLD:\n{old}\n\nMSG:\n{user_message}\n\nREPLY:\n{ai_reply}"
    )
    summary = await call_openai_assistant([
        {"role": "user", "content": prompt}
    ])
    await update_user_memory(user_id, summary)

# ============================================================
# ONBOARDING ENGINE  (FULL TYPING SUPPORT)
# ============================================================

ONBOARDING_QUESTIONS = [
    ("niche", "1️⃣ Who do you serve?"),
    ("offer", "2️⃣ What is your core offer?"),
    ("revenue", "3️⃣ What's your current monthly revenue + profit?"),
    ("goal", "4️⃣ Your 5–6 month target?"),
    ("bottleneck", "5️⃣ Your biggest bottleneck?"),
    ("email", "6️⃣ Best email for your Asana program board?"),
]

async def run_onboarding(thread: discord.Thread, user: discord.Member) -> Dict[str, Any]:
    meta = {
        "discord_id": user.id,
        "discord_name": str(user),
        "created_at_utc": dt.datetime.utcnow().isoformat(),
        "onboarding_complete": False,
    }

    async with thread.typing():
        await asyncio.sleep(1)
    await thread.send(
        f"Hey {user.mention}! 👋\n"
        "STRICT ONBOARDING MODE.\n"
        "I will ask 6 questions only. No coaching yet.\n"
    )

    def check(msg):
        return msg.author.id == user.id and msg.channel.id == thread.id

    stage = 1
    for key, question in ONBOARDING_QUESTIONS:
        await redis_client.set(k_onboarding_stage(user.id), str(stage))

        async with thread.typing():
            await asyncio.sleep(1.2)
        await thread.send(question)

        try:
            msg = await bot.wait_for("message", timeout=900, check=check)
        except asyncio.TimeoutError:
            await thread.send("⏳ Timeout. Use `!start` to resume later.")
            return meta

        meta[key] = msg.content.strip()
        stage += 1

    meta["onboarding_complete"] = True
    await set_user_meta(user.id, meta)
    await redis_client.delete(k_onboarding_stage(user.id))

    # Asana creation
    async with thread.typing():
        await asyncio.sleep(1.2)

    email = meta.get("email")
    if email:
        url = await asana_duplicate_project_for_user(user.id, email, user.display_name)
        if url:
            await thread.send(f"✅ Your Asana board is ready:\n{url}")
        else:
            await thread.send("⚠️ Failed to auto-create Asana board. Derek will handle it.")

    async with thread.typing():
        await asyncio.sleep(1)
    await thread.send("🎉 Onboarding complete! You may now talk to me normally.")

    return meta

# ============================================================
# PRIVATE THREAD HELPER
# ============================================================

async def get_or_create_private_thread(ctx):
    existing = await redis_client.get(k_user_thread(ctx.author.id))
    if existing:
        t = ctx.guild.get_thread(int(existing))
        if t:
            return t

    base = ctx.channel
    t = await base.create_thread(
        name=f"AI – {ctx.author.display_name}",
        type=discord.ChannelType.private_thread
    )
    await t.add_user(ctx.author)
    await redis_client.set(k_user_thread(ctx.author.id), t.id)
    return t

# ============================================================
# COMMANDS
# ============================================================

@bot.event
async def on_ready():
    log.info("Bot ready as %s", bot.user)
    daily_checkins.start()

@bot.command(name="start")
async def start_command(ctx):
    thread = await get_or_create_private_thread(ctx)
    meta = await get_user_meta(ctx.author.id)

    if not meta.get("onboarding_complete"):
        async with thread.typing():
            await asyncio.sleep(1)
        await thread.send("Starting onboarding…")
        await run_onboarding(thread, ctx.author)
    else:
        async with thread.typing():
            await asyncio.sleep(1)
        await thread.send("Welcome back — you're already onboarded.")

    await ctx.reply(f"Your private AI thread: {thread.mention}")

@bot.command(name="image")
async def image_command(ctx, *, prompt):
    async with ctx.typing():
        img = await generate_image(prompt, ctx.author.id)
    if not img:
        return await ctx.send("⚠️ You've hit your 50 images for today.")

    file = discord.File(io.BytesIO(img), filename="image.png")
    await ctx.send(file=file)

# ============================================================
# AUTO AI HANDLER  (FULL TYPING SUPPORT)
# ============================================================

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)
    if message.author.bot:
        return

    # Only respond inside user's private thread
    t_id = await redis_client.get(k_user_thread(message.author.id))
    if not t_id or str(message.channel.id) != t_id:
        return

    # Onboarding messages are ignored here
    if await redis_client.get(k_onboarding_stage(message.author.id)):
        return

    # Commands bypass
    if message.content.startswith("!"):
        return

    # Voice notes
    if message.attachments:
        att = message.attachments[0]
        if att.content_type and att.content_type.startswith("audio"):
            async with message.channel.typing():
                text = await transcribe_audio(att)
            if not text:
                return await message.channel.send("❌ Couldn't transcribe.")
            async with message.channel.typing():
                reply = await coach_answer(message.author.id, text)
            return await message.channel.send(reply)

    # Normal text coaching
    async with message.channel.typing():
        reply = await coach_answer(message.author.id, message.content)

    if len(reply) <= 2000:
        await message.channel.send(reply)
    else:
        for i in range(0, len(reply), 1900):
            await message.channel.send(reply[i:i+1900])

# ============================================================
# DAILY CHECKINS
# ============================================================

@tasks.loop(minutes=10)
async def daily_checkins():
    now = dt.datetime.utcnow()
    hour_cst = (now.hour - 6) % 24
    if hour_cst != 8:
        return

    today = now.date().isoformat()
    keys = await redis_client.keys("user:*:meta")

    for key in keys:
        try:
            uid = int(key.split(":")[1])
        except:
            continue

        last = await redis_client.get(k_last_checkin(uid))
        if last == today:
            continue

        t_id = await redis_client.get(k_user_thread(uid))
        if not t_id:
            continue

        ch = bot.get_channel(int(t_id))
        if not isinstance(ch, discord.Thread):
            continue

        meta = await get_user_meta(uid)
        goal = meta.get("goal", "Grow")

        async with ch.typing():
            await asyncio.sleep(1)
        await ch.send(
            "📆 **Daily Check-In**\n"
            f"Goal: **{goal}**\n\n"
            "1) What you did yesterday\n"
            "2) Top 1–3 actions today\n"
            "3) Any blockers?"
        )

        await redis_client.set(k_last_checkin(uid), today)

# ============================================================
# RUN BOT
# ============================================================

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
