import os
import json
import logging
import textwrap
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any, List

import aiohttp
import discord
from discord.ext import commands, tasks
from openai import OpenAI
import redis.asyncio as redis

# --------------------------------------------------
# Logging setup
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("derek-ai-bot")

# --------------------------------------------------
# Environment & constants
# --------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

ASSISTANT_ID = os.getenv(
    "ASSISTANT_ID",
    "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"  # your assistant id
)

ASANA_ACCESS_TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_TEMPLATE_GID = os.getenv("ASANA_TEMPLATE_GID")

IMAGE_DAILY_LIMIT = int(os.getenv("IMAGE_DAILY_LIMIT", "50"))

# If empty, everyone is allowed (dev mode)
PROGRAM_USER_IDS = [
    int(x) for x in os.getenv("PROGRAM_USER_IDS", "").split(",") if x.strip()
]

PROGRAM_ADMIN_IDS = [
    int(x) for x in os.getenv("PROGRAM_ADMIN_IDS", "").split(",") if x.strip()
]

# CST for check-ins
CST_UTC_OFFSET_HOURS = -6
DAILY_CHECKIN_HOUR_CST = 8  # 8 AM CST

# --------------------------------------------------
# Redis key helpers
# --------------------------------------------------
def rk_user_thread(user_id: int) -> str:
    return f"user:{user_id}:openai_thread_id"


def rk_discord_thread(user_id: int) -> str:
    return f"user:{user_id}:discord_thread_id"


def rk_thread_owner(thread_id: int) -> str:
    return f"thread:{thread_id}:owner"


def rk_onboarding(user_id: int) -> str:
    return f"user:{user_id}:onboarding"


def rk_onboarding_done(user_id: int) -> str:
    return f"user:{user_id}:onboarding_done"


def rk_onboarding_answers(user_id: int) -> str:
    return f"user:{user_id}:onboarding_answers"


def rk_memory(user_id: int) -> str:
    return f"user:{user_id}:memory"


def rk_asana_project(user_id: int) -> str:
    return f"user:{user_id}:asana_project_gid"


def rk_asana_email(user_id: int) -> str:
    return f"user:{user_id}:asana_email"


def rk_metrics(user_id: int) -> str:
    return f"user:{user_id}:metrics"


def rk_daily_images(user_id: int, day: str) -> str:
    return f"user:{user_id}:images:{day}"


def rk_pending_audio(user_id: int) -> str:
    return f"user:{user_id}:pending_audio"


def rk_audio_mode(user_id: int) -> str:
    return f"user:{user_id}:audio_mode"


# --------------------------------------------------
# Clients
# --------------------------------------------------
openai_client = OpenAI(api_key=OPENAI_API_KEY)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Disable default help so we can define our own !help
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --------------------------------------------------
# Utility / metrics helpers
# --------------------------------------------------
def is_program_member(user_id: int) -> bool:
    if not PROGRAM_USER_IDS:
        # If list is empty, allow everyone (dev mode)
        return True
    return user_id in PROGRAM_USER_IDS


def is_program_admin(user_id: int) -> bool:
    if not PROGRAM_ADMIN_IDS:
        return False
    return user_id in PROGRAM_ADMIN_IDS


def chunk_for_discord(text: str, limit: int = 1900) -> List[str]:
    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:]
        if text.startswith("\n"):
            text = text[1:]
    return chunks


async def incr_metrics(user_id: int, **incs: float) -> None:
    key = rk_metrics(user_id)
    pipe = redis_client.pipeline(transaction=True)
    for field, val in incs.items():
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        pipe.hincrbyfloat(key, field, f)
    await pipe.execute()


async def get_metrics(user_id: int) -> Dict[str, Any]:
    key = rk_metrics(user_id)
    data = await redis_client.hgetall(key)
    return data or {}


async def record_response_time(user_id: int, seconds: float) -> None:
    await incr_metrics(
        user_id,
        response_time_total=seconds,
        response_count=1,
    )


def today_str() -> str:
    return date.today().isoformat()


# --------------------------------------------------
# OpenAI helpers
# --------------------------------------------------
async def get_or_create_openai_thread(user_id: int) -> str:
    key = rk_user_thread(user_id)
    tid = await redis_client.get(key)
    if tid:
        return tid
    thread = openai_client.beta.threads.create()
    await redis_client.set(key, thread.id)
    return thread.id


async def call_assistant(
    user_id: int,
    thread_id: str,
    user_content: str,
    extra_system: Optional[str] = None,
) -> str:
    base_system = textwrap.dedent(
        """
        You are a focused growth coach for Christian agency owners and coaches.
        You help with:
        - sales & setting
        - Meta ads & creatives
        - YouTube & organic
        - offer, positioning, and systems
        - execution accountability over a 5–6 month program.

        Be punchy, specific, and practical. Use bullets and numbered steps.
        Avoid long walls of text; break things into sections.
        Tie advice back to the user's goals and constraints where possible.
        """
    )
    if extra_system:
        base_system += "\n\n" + extra_system

    start = datetime.now(timezone.utc)

    openai_client.beta.threads.messages.create(
        thread_id,
        role="user",
        content=user_content,
    )

    run = openai_client.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        instructions=base_system,
    )

    if run.status != "completed":
        logger.warning("Assistant run not completed for user %s: %s", user_id, run.status)
        return "I hit a snag generating that reply. Try again in a moment."

    messages = openai_client.beta.threads.messages.list(
        thread_id=thread_id,
        order="desc",
        limit=5,
    )

    reply_text = ""
    for m in messages.data:
        if m.role == "assistant":
            for part in m.content:
                if part.type == "text":
                    reply_text = part.text.value
                    break
            if reply_text:
                break

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    await record_response_time(user_id, elapsed)
    await incr_metrics(user_id, messages=1)
    if not reply_text:
        reply_text = "I couldn't pull a response from that run. Please try again."
    return reply_text


async def analyze_call(user_id: int, thread_id: str, transcript: str) -> str:
    extra = textwrap.dedent(
        """
        You are analyzing a SALES or SETTING call for a Christian agency/coach.

        Return a structured Markdown analysis with sections:

        1. **Call Summary**
        2. **What Went Well**
        3. **Biggest Opportunities**
        4. **Key Objections & Handling**
        5. **Better Lines They Could Have Used** (scripts)
        6. **Red Flag Buckets**

           - 💸 Budget flags
           - 🟧 Timeline objections
           - 😕 Uncertainty indicators
           - 🚫 Bad fit warnings
           - 🧊 Lead coldness signals
           - 💀 “Never buying” traits

        7. **Top 3 Actions for Their Next Call**

        Be blunt, specific, and actionable. No generic advice.
        """
    )
    prompt = f"Here is the call transcript:\n\n{transcript}"
    return await call_assistant(user_id, thread_id, prompt, extra)


# --------------------------------------------------
# Image generation
# --------------------------------------------------
async def can_generate_image(user_id: int) -> bool:
    key = rk_daily_images(user_id, today_str())
    val = await redis_client.get(key)
    if not val:
        return True
    return int(val) < IMAGE_DAILY_LIMIT


async def inc_image_usage(user_id: int) -> None:
    key = rk_daily_images(user_id, today_str())
    pipe = redis_client.pipeline(transaction=True)
    pipe.incr(key, 1)
    pipe.expire(key, 60 * 60 * 24 * 3)
    await pipe.execute()
    await incr_metrics(user_id, images=1)


async def generate_image_url(prompt: str) -> Optional[str]:
    try:
        resp = openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        if resp.data and resp.data[0].url:
            return resp.data[0].url
    except Exception as e:
        logger.exception("Image generation error: %s", e)
    return None


# --------------------------------------------------
# Audio helpers
# --------------------------------------------------
async def transcribe_audio(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    from io import BytesIO

    f = BytesIO(file_bytes)
    f.name = filename
    try:
        result = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="json",
        )
        # Depending on SDK version, this may be dict-like or object-like
        if isinstance(result, dict):
            text = result.get("text", "")
        else:
            text = getattr(result, "text", "")
        return {"text": text or "", "duration_sec": 0.0}
    except Exception as e:
        logger.exception("Transcription error: %s", e)
        raise


async def save_pending_audio(user_id: int, data: Dict[str, Any]) -> None:
    await redis_client.set(rk_pending_audio(user_id), json.dumps(data), ex=60 * 30)


async def get_pending_audio(user_id: int) -> Optional[Dict[str, Any]]:
    raw = await redis_client.get(rk_pending_audio(user_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def clear_pending_audio(user_id: int) -> None:
    await redis_client.delete(rk_pending_audio(user_id))


async def set_audio_mode(user_id: int, mode: Optional[str]) -> None:
    key = rk_audio_mode(user_id)
    if mode is None:
        await redis_client.delete(key)
    else:
        await redis_client.set(key, mode, ex=60 * 30)


async def get_audio_mode(user_id: int) -> Optional[str]:
    return await redis_client.get(rk_audio_mode(user_id))


# --------------------------------------------------
# Asana integration (comment-only sharing)
# --------------------------------------------------
ASANA_API_BASE = "https://app.asana.com/api/1.0"


async def duplicate_asana_project_for_user(
    user: discord.User,
    email: str,
    onboarding_summary: str,
) -> Optional[str]:
    """
    Duplicate the template project for this user, then attempt to share it with
    their email as comment-only (guest / free route). Returns project GID or None.
    """
    if not ASANA_ACCESS_TOKEN or not ASANA_TEMPLATE_GID:
        logger.warning("Asana not configured; skipping project duplication.")
        return None

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    project_name = f"{user.display_name} – Scaling Program"

    # 1) Duplicate the template
    dup_url = f"{ASANA_API_BASE}/projects/{ASANA_TEMPLATE_GID}/duplicate"
    dup_payload = {
        "data": {
            "name": project_name,
            "include": [
                "notes",
                "task_notes",
                "task_subtasks",
                "task_dependencies",
                "task_dates",
                "task_projects",
                "task_tags",
                "task_followers",
                "task_attachments",
            ],
            "schedule_dates": True,
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(dup_url, headers=headers, json=dup_payload) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.error("Asana duplicate error %s: %s", resp.status, body)
                    return None
                dup_data = await resp.json()
    except Exception as e:
        logger.exception("Asana duplicate request failed: %s", e)
        return None

    new_project = dup_data.get("data", {}).get("new_project") or dup_data.get("data")
    project_gid = new_project.get("gid") if new_project else None
    if not project_gid:
        logger.error("Asana duplicate response missing project gid: %s", dup_data)
        return None

    # 2) Try to share project as comment-only with the client's email.
    # NOTE: Actual billing (guest vs member) depends on Asana's rules,
    # but this follows the "comment-only project share" pattern.
    share_url = f"{ASANA_API_BASE}/projects/{project_gid}/addMembers"
    share_payload = {
        "data": {
            "members": [email],
            "role": "commenter",
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(share_url, headers=headers, json=share_payload) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(
                        "Asana share error %s for email %s: %s",
                        resp.status,
                        email,
                        body,
                    )
                else:
                    logger.info("Shared Asana project %s with %s as commenter", project_gid, email)
    except Exception as e:
        logger.exception("Asana share request failed: %s", e)

    # 3) Remember mapping
    await redis_client.set(rk_asana_project(user.id), project_gid)
    await redis_client.set(rk_asana_email(user.id), email)

    return project_gid


async def summarize_asana_project(project_gid: str) -> str:
    """
    Simple daily summary of tasks: overdue, due today, upcoming.
    """
    if not ASANA_ACCESS_TOKEN:
        return "Asana is not configured yet."

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
    }
    tasks_url = f"{ASANA_API_BASE}/tasks"

    today = date.today().isoformat()
    params = {
        "project": project_gid,
        "opt_fields": "gid,name,completed,due_on",
        "limit": 100,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(tasks_url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Asana tasks fetch error %s: %s", resp.status, body)
                    return "I couldn't fetch your Asana tasks yet."
                data = await resp.json()
    except Exception as e:
        logger.exception("Asana tasks fetch failed: %s", e)
        return "I couldn't fetch your Asana tasks yet."

    tasks = data.get("data", [])
    overdue = 0
    due_today = 0
    upcoming = 0

    for t in tasks:
        if t.get("completed"):
            continue
        due_on = t.get("due_on")
        if not due_on:
            continue
        if due_on < today:
            overdue += 1
        elif due_on == today:
            due_today += 1
        else:
            upcoming += 1

    parts = []
    if overdue:
        parts.append(f"{overdue} overdue")
    if due_today:
        parts.append(f"{due_today} due today")
    if upcoming:
        parts.append(f"{upcoming} upcoming")

    if not parts:
        return "You're fully caught up on your Asana tasks."

    return "You have " + ", ".join(parts) + "."


# --------------------------------------------------
# Onboarding
# --------------------------------------------------
ONBOARDING_QUESTIONS = [
    ("program_focus", "What is your current primary offer or niche (e.g. 'Christian fitness coaching for dads')?"),
    ("current_mrr", "What is your current consistent monthly revenue?"),
    ("revenue_goal", "What is your target monthly revenue in the next 5–6 months?"),
    ("constraints", "What are your top 2–3 constraints right now (lead flow, offer, sales, delivery, mindset, etc.)?"),
    ("time_per_week", "How many **focused hours per week** can you realistically commit?"),
    ("asana_email", "What email should I use to give you comment-only access to your Asana program workspace?"),
]

ONBOARDING_STATE_INDEX = "index"


async def is_onboarded(user_id: int) -> bool:
    val = await redis_client.get(rk_onboarding_done(user_id))
    return val == "1"


async def get_onboarding_state(user_id: int) -> Optional[int]:
    raw = await redis_client.hget(rk_onboarding(user_id), ONBOARDING_STATE_INDEX)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def set_onboarding_state(user_id: int, index: Optional[int]) -> None:
    key = rk_onboarding(user_id)
    if index is None:
        await redis_client.hdel(key, ONBOARDING_STATE_INDEX)
    else:
        await redis_client.hset(key, ONBOARDING_STATE_INDEX, str(index))


async def get_onboarding_answers(user_id: int) -> Dict[str, Any]:
    raw = await redis_client.get(rk_onboarding_answers(user_id))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


async def save_onboarding_answers(user_id: int, answers: Dict[str, Any]) -> None:
    await redis_client.set(rk_onboarding_answers(user_id), json.dumps(answers))


async def start_onboarding(user: discord.User, thread: discord.Thread) -> None:
    await set_onboarding_state(user.id, 0)
    await save_onboarding_answers(user.id, {})
    await thread.send(
        f"👋 Hey {user.mention}! Before I coach you, I need a quick snapshot of your business.\n\n"
        f"I'll ask you a few short questions. Answer here in this thread.\n\n"
        f"**Q1:** {ONBOARDING_QUESTIONS[0][1]}"
    )


async def handle_onboarding_message(
    user: discord.User,
    thread: discord.Thread,
    message: discord.Message,
) -> bool:
    idx = await get_onboarding_state(user.id)
    if idx is None:
        return False

    answers = await get_onboarding_answers(user.id)

    # Save answer for current index
    if 0 <= idx < len(ONBOARDING_QUESTIONS):
        field, question = ONBOARDING_QUESTIONS[idx]
        answers[field] = message.content.strip()
        await save_onboarding_answers(user.id, answers)
        idx += 1
        await set_onboarding_state(user.id, idx)

    # Ask next question or finish
    if idx < len(ONBOARDING_QUESTIONS):
        field, question = ONBOARDING_QUESTIONS[idx]
        await thread.send(f"**Q{idx+1}:** {question}")
        return True

    # Done
    await redis_client.set(rk_onboarding_done(user.id), "1")
    await set_onboarding_state(user.id, None)

    summary_lines = [
        "✅ **Onboarding complete. Here's what I captured:**",
    ]
    for field, question in ONBOARDING_QUESTIONS:
        summary_lines.append(f"- **{question}**\n  → {answers.get(field, '(not answered)')}")

    onboarding_summary = "\n".join(summary_lines)
    await thread.send(onboarding_summary)

    # Store high-level memory for AI
    await redis_client.set(rk_memory(user.id), onboarding_summary)

    # Create Asana project & share comment-only link
    email = answers.get("asana_email")
    if email:
        await thread.send(
            "📋 Creating your Asana program workspace and giving you **comment-only** access…"
        )
        project_gid = await duplicate_asana_project_for_user(user, email, onboarding_summary)
        if project_gid:
            await thread.send(
                "✅ Your Asana program workspace is created.\n"
                "You should receive an email invite from Asana with comment-only access.\n"
                "I'll use this workspace as your 'source of truth' for tasks and accountability."
            )
        else:
            await thread.send(
                "⚠️ I tried to create/share your Asana workspace but hit an issue.\n"
                "Derek may need to manually set it up for you."
            )
    else:
        await thread.send(
            "⚠️ You didn't provide an Asana email, so I skipped auto-creating your Asana workspace."
        )

    await thread.send(
        "From here on, just use this thread to:\n"
        "- Ask strategy questions (sales, ads, content, systems)\n"
        "- Drop call recordings for deep breakdowns\n"
        "- Get clarity on what to do next\n\n"
        "Whenever you want to see what I remember about you, type `!myinfo`."
    )

    return True


# --------------------------------------------------
# Discord thread helpers
# --------------------------------------------------
async def get_or_create_discord_thread(ctx: commands.Context) -> discord.Thread:
    """
    Create or get a simple thread (compatible with your discord.py version).
    """
    user = ctx.author
    key = rk_discord_thread(user.id)
    existing = await redis_client.get(key)

    # If thread exists already, return it
    if existing:
        thread = ctx.guild.get_thread(int(existing))
        if isinstance(thread, discord.Thread):
            return thread

    # Create thread using ONLY supported arguments
    base_msg = await ctx.send(f"{user.mention} setting up your coaching thread…")

    thread = await base_msg.create_thread(
        name=f"{user.display_name} – Coaching",
        auto_archive_duration=10080  # 7 days
    )

    # Try to add the user to the thread
    try:
        await thread.add_user(user)
    except Exception:
        pass

    await redis_client.set(key, str(thread.id))
    await redis_client.set(rk_thread_owner(thread.id), str(user.id))

    return thread



async def get_thread_owner(thread: discord.Thread) -> Optional[int]:
    val = await redis_client.get(rk_thread_owner(thread.id))
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


# --------------------------------------------------
# Daily check-ins (8 AM CST in their coaching thread)
# --------------------------------------------------
def current_cst_hour() -> int:
    now_utc = datetime.now(timezone.utc)
    cst = now_utc + timedelta(hours=CST_UTC_OFFSET_HOURS)
    return cst.hour


@tasks.loop(minutes=10.0)
async def daily_checkins():
    """
    Every ~10 minutes, check if it's around 8 AM CST and send a simple check-in
    to each program member who has a Discord thread + Asana project.
    """
    try:
        if current_cst_hour() != DAILY_CHECKIN_HOUR_CST:
            return

        logger.info("Running daily check-ins at 8 AM CST window.")

        for user_id in PROGRAM_USER_IDS:
            thread_id_str = await redis_client.get(rk_discord_thread(user_id))
            if not thread_id_str:
                continue
            channel = bot.get_channel(int(thread_id_str))
            if not channel or not isinstance(channel, discord.Thread):
                continue

            project_gid = await redis_client.get(rk_asana_project(user_id))
            if project_gid:
                summary = await summarize_asana_project(project_gid)
            else:
                summary = "We haven't connected your Asana program workspace yet."

            msg = (
                "⏰ **Daily Check-in**\n\n"
                f"{summary}\n\n"
                "Reply with:\n"
                "- What you completed yesterday\n"
                "- What you're committed to today\n"
                "- Any blockers or confusion\n"
            )
            try:
                await channel.send(msg)
            except Exception as e:
                logger.exception("Error sending check-in to %s: %s", user_id, e)

    except Exception as e:
        logger.exception("Error in daily_checkins loop: %s", e)


@daily_checkins.before_loop
async def before_daily_checkins():
    await bot.wait_until_ready()
    logger.info("Daily check-ins loop ready.")


# --------------------------------------------------
# Commands
# --------------------------------------------------
@bot.event
async def on_ready():
    logger.info("Bot logged in as %s", bot.user)
    if not daily_checkins.is_running():
        daily_checkins.start()


@bot.command(name="start")
async def cmd_start(ctx: commands.Context):
    """
    Entry: create/join private AI thread, then onboarding if needed.
    """
    user = ctx.author
    if not is_program_member(user.id):
        await ctx.reply(
            "You’re not in my program list yet. DM Derek if you think this is a mistake."
        )
        return

    thread = await get_or_create_discord_thread(ctx)
    await ctx.reply(
        f"✅ Your private coaching thread is ready: {thread.mention}\n"
        f"I'll work with you in there so we don't spam this channel."
    )

    if not await is_onboarded(user.id):
        await start_onboarding(user, thread)
    else:
        await thread.send(
            f"Welcome back, {user.mention}! You’re already onboarded — ask me anything or drop a call recording."
        )


@bot.command(name="image")
async def cmd_image(ctx: commands.Context, *, prompt: str):
    """
    Generate a creative or visual asset with the image model.
    """
    user = ctx.author
    if not is_program_member(user.id):
        await ctx.reply("This command is only available to program members.")
        return

    if not await can_generate_image(user.id):
        await ctx.reply(
            f"🚫 You've hit your daily limit of {IMAGE_DAILY_LIMIT} images for today."
        )
        return

    await ctx.reply("🎨 Generating image…")

    url = await generate_image_url(prompt)
    if not url:
        await ctx.send(
            "❌ I couldn't generate the image. Check your OpenAI billing/org settings."
        )
        return

    await inc_image_usage(user.id)

    embed = discord.Embed(
        title="Generated Image",
        description=prompt,
    )
    embed.set_image(url=url)
    await ctx.send(embed=embed)


@bot.command(name="myinfo")
async def cmd_myinfo(ctx: commands.Context):
    """
    Show what the bot remembers about the user (onboarding + summary).
    """
    user = ctx.author
    if not is_program_member(user.id):
        await ctx.reply("This is only for program members.")
        return

    onboarding = await get_onboarding_answers(user.id)
    summary = await redis_client.get(rk_memory(user.id))
    metrics = await get_metrics(user.id)

    lines = ["🧠 **What I know about you:**"]
    if onboarding:
        for field, question in ONBOARDING_QUESTIONS:
            if field in onboarding:
                lines.append(f"- **{question}**\n  → {onboarding[field]}")
    else:
        lines.append("_No onboarding data yet._")

    if summary:
        lines.append("\n📝 **Summary memory:**")
        lines.append(summary)

    if metrics:
        lines.append("\n📊 **Usage metrics:**")
        for k, v in metrics.items():
            try:
                num = float(v)
                lines.append(f"- `{k}` → **{num:.2f}**")
            except ValueError:
                lines.append(f"- `{k}` → {v}")

    text = "\n".join(lines)
    for chunk in chunk_for_discord(text):
        await ctx.reply(chunk)


@bot.command(name="resetmemory")
async def cmd_resetmemory(ctx: commands.Context):
    """
    Reset onboarding + memory (but keep Asana project mapping).
    """
    user = ctx.author
    if not is_program_member(user.id):
        await ctx.reply("This is only for program members.")
        return

    await redis_client.delete(rk_onboarding_done(user.id))
    await redis_client.delete(rk_onboarding_answers(user.id))
    await redis_client.delete(rk_onboarding(user.id))
    await redis_client.delete(rk_memory(user.id))
    await ctx.reply(
        "🧹 I wiped your onboarding + memory. Use `!start` to go through onboarding again if you want."
    )


@bot.command(name="inspectmemory")
async def cmd_inspectmemory(ctx: commands.Context, user: discord.User):
    """
    Admin-only: inspect another user's memory.
    """
    if not is_program_admin(ctx.author.id):
        await ctx.reply("You don't have permission to use this command.")
        return

    onboarding = await get_onboarding_answers(user.id)
    summary = await redis_client.get(rk_memory(user.id))
    metrics = await get_metrics(user.id)
    asana_project = await redis_client.get(rk_asana_project(user.id))
    asana_email = await redis_client.get(rk_asana_email(user.id))

    lines = [f"📂 **Memory for {user} ({user.id})**"]
    if onboarding:
        lines.append("\n🧠 **Onboarding:**")
        for field, question in ONBOARDING_QUESTIONS:
            if field in onboarding:
                lines.append(f"- {field}: {onboarding[field]}")
    else:
        lines.append("\n_No onboarding data._")

    if summary:
        lines.append("\n📝 **Summary memory:**")
        lines.append(summary)

    if metrics:
        lines.append("\n📊 **Metrics:**")
        for k, v in metrics.items():
            lines.append(f"- {k}: {v}")

    if asana_project:
        lines.append(f"\n📋 **Asana project GID:** `{asana_project}`")
    if asana_email:
        lines.append(f"📧 **Asana email:** `{asana_email}`")

    text = "\n".join(lines)
    for chunk in chunk_for_discord(text):
        await ctx.reply(chunk)


@bot.command(name="stats")
async def cmd_stats(ctx: commands.Context):
    """
    Short usage stats for the current user.
    """
    user = ctx.author
    if not is_program_member(user.id):
        await ctx.reply("This is only for program members.")
        return

    metrics = await get_metrics(user.id)
    msgs = float(metrics.get("messages", 0))
    imgs = float(metrics.get("images", 0))
    audio_min = float(metrics.get("audio_minutes", 0))
    resp_total = float(metrics.get("response_time_total", 0))
    resp_count = float(metrics.get("response_count", 0))
    avg_rt = resp_total / resp_count if resp_count > 0 else 0.0

    text = (
        "📊 **Your stats:**\n"
        f"- Messages processed: **{int(msgs)}**\n"
        f"- Images generated: **{int(imgs)}**\n"
        f"- Audio minutes analyzed: **{audio_min:.1f}**\n"
        f"- AI responses: **{int(resp_count)}**\n"
        f"- Avg response time: **{avg_rt:.1f}s**"
    )
    await ctx.reply(text)


@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    """
    Show commands and capabilities.
    """
    text = textwrap.dedent(
        """
        🤖 **Derek AI – Commands**

        `!start` – Open your private thread and go through onboarding if needed.
        `!image <prompt>` – Generate a creative/image (limited per day).
        `!myinfo` – See what I remember about you + your stats.
        `!resetmemory` – Wipe your onboarding + memory (keeps Asana mapping).
        `!stats` – Quick usage stats.
        `!inspectmemory @user` – (Admin) Inspect someone’s onboarding + metrics.
        `!help` – Show this help message.

        In your private thread, just talk normally:
        - Text → I’ll answer as your growth coach.
        - Drop audio files → I’ll transcribe & ask if it’s a **call** or **question**.
        - Long calls → I’ll grade them with red flags & coaching.
        """
    )
    await ctx.reply(text)


# --------------------------------------------------
# Message handler: threads, onboarding, audio, AI
# --------------------------------------------------
@bot.event
async def on_message(message: discord.Message):
    # ignore bot messages
    if message.author.bot:
        return

    # let commands run
    await bot.process_commands(message)

    # we only care about user messages in threads we own
    if not isinstance(message.channel, discord.Thread):
        return

    thread = message.channel
    user = message.author

    owner_id = await get_thread_owner(thread)
    if owner_id is None or owner_id != user.id:
        return

    if not is_program_member(user.id):
        return

    # ignore command-style messages here
    if message.content.startswith("!"):
        return

    # 1) If onboarding is in progress, handle that
    if await get_onboarding_state(user.id) is not None and not await is_onboarded(user.id):
        consumed = await handle_onboarding_message(user, thread, message)
        if consumed:
            return

    # 2) If we have a pending audio mode ("call" vs "question")
    mode = await get_audio_mode(user.id)
    if mode:
        pending = await get_pending_audio(user.id)
        if not pending:
            await set_audio_mode(user.id, None)
        else:
            lower = message.content.lower().strip()
            transcript = pending.get("text") or pending.get("transcript") or ""
            duration_sec = float(pending.get("duration_sec", 0.0))
            openai_thread_id = await get_or_create_openai_thread(user.id)

            if "call" in lower:
                await thread.send("📞 Got it – treating that as a **call**. Analyzing now…")
                analysis = await analyze_call(user.id, openai_thread_id, transcript)
                for chunk in chunk_for_discord(analysis):
                    await thread.send(chunk)
                await incr_metrics(user.id, audio_minutes=duration_sec / 60.0, calls_analyzed=1)
                await clear_pending_audio(user.id)
                await set_audio_mode(user.id, None)
                return
            elif "question" in lower or "qa" in lower or "q&a" in lower:
                await thread.send("🎧 Treating that as a **question**. Answering now…")
                reply = await call_assistant(
                    user.id,
                    openai_thread_id,
                    f"User sent a voice note. Transcript:\n\n{transcript}",
                )
                for chunk in chunk_for_discord(reply):
                    await thread.send(chunk)
                await incr_metrics(user.id, audio_minutes=duration_sec / 60.0)
                await clear_pending_audio(user.id)
                await set_audio_mode(user.id, None)
                return
            # if they say something else, fall through to normal text handling but keep mode set

    # 3) If message has audio attachment, process transcription
    if message.attachments:
        audio_att = None
        for a in message.attachments:
            if a.content_type and (a.content_type.startswith("audio") or a.content_type.startswith("video")):
                audio_att = a
                break
        if audio_att:
            await thread.send("🎧 Received audio. Transcribing…")
            try:
                file_bytes = await audio_att.read()
                result = await transcribe_audio(file_bytes, audio_att.filename)
            except Exception:
                await thread.send("❌ I couldn't transcribe that audio. Try again with a clearer file.")
                return

            transcript = result.get("text", "")
            duration_sec = float(result.get("duration_sec", 0.0))

            await save_pending_audio(user.id, {"text": transcript, "duration_sec": duration_sec})
            await set_audio_mode(user.id, "pending")
            await thread.send(
                "I’ve transcribed your audio.\n\n"
                "Should I treat this as:\n"
                "- a **sales/setting call** to grade (`call`), or\n"
                "- a **quick question** you want answered (`question`)?\n\n"
                "Reply with `call` or `question`."
            )
            return

    # 4) Otherwise this is normal text for the AI
    content = message.content.strip()
    if not content:
        return

    openai_thread_id = await get_or_create_openai_thread(user.id)
    reply = await call_assistant(user.id, openai_thread_id, content)
    for chunk in chunk_for_discord(reply):
        await thread.send(chunk)


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN is not set.")
    bot.run(DISCORD_TOKEN)
