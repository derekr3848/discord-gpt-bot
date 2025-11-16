import os
import json
import logging
import asyncio
import textwrap
import base64
from datetime import datetime, timedelta, time
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

PROGRAM_USER_IDS = [
    int(x) for x in os.getenv("PROGRAM_USER_IDS", "").split(",") if x.strip()
]

PROGRAM_ADMIN_IDS = [
    int(x) for x in os.getenv("PROGRAM_ADMIN_IDS", "").split(",") if x.strip()
]

# CST offset for simple daily schedule (no DST handling – good enough for v1)
CST_UTC_OFFSET_HOURS = -6
DAILY_CHECKIN_HOUR_CST = 8  # 8 AM CST

# Redis keys helpers
def redis_key_user_thread(user_id: int) -> str:
    return f"user:{user_id}:openai_thread_id"


def redis_key_user_memory(user_id: int) -> str:
    return f"user:{user_id}:memory"


def redis_key_user_metrics(user_id: int) -> str:
    return f"user:{user_id}:metrics"


def redis_key_user_onboarding(user_id: int) -> str:
    return f"user:{user_id}:onboarding"


def redis_key_user_asana_project(user_id: int) -> str:
    return f"user:{user_id}:asana_project_gid"


def redis_key_user_discord_thread(user_id: int) -> str:
    return f"user:{user_id}:discord_thread_id"


def redis_key_thread_owner(thread_id: int) -> str:
    return f"thread:{thread_id}:owner_user_id"


def redis_key_user_pending_audio(user_id: int) -> str:
    return f"user:{user_id}:pending_audio"


def redis_key_user_audio_mode(user_id: int) -> str:
    return f"user:{user_id}:audio_mode_pending"


def redis_key_user_daily_image(user_id: int, date_str: str) -> str:
    return f"user:{user_id}:images:{date_str}"


# --------------------------------------------------
# OpenAI & Redis clients
# --------------------------------------------------
openai_client = OpenAI(api_key=OPENAI_API_KEY)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# --------------------------------------------------
# Discord bot setup
# --------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --------------------------------------------------
# Utility functions
# --------------------------------------------------


def is_program_member(user_id: int) -> bool:
    if not PROGRAM_USER_IDS:
        # If list is empty, treat as open access (for dev)
        return True
    return user_id in PROGRAM_USER_IDS


def is_program_admin(user_id: int) -> bool:
    if not PROGRAM_ADMIN_IDS:
        return False
    return user_id in PROGRAM_ADMIN_IDS


def chunk_text_for_discord(text: str, limit: int = 1900) -> List[str]:
    """Split long responses into Discord-safe chunks."""
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
        if text.startswith("\n"):
            text = text[1:]
    return chunks


async def get_or_create_openai_thread(user_id: int) -> str:
    """Get or create OpenAI thread id stored in Redis per user."""
    key = redis_key_user_thread(user_id)
    thread_id = await redis_client.get(key)
    if thread_id:
        return thread_id

    logger.info(f"Creating new OpenAI thread for user {user_id}")
    thread = openai_client.beta.threads.create()
    thread_id = thread.id
    await redis_client.set(key, thread_id)
    return thread_id


async def update_user_metrics(user_id: int, **kwargs) -> None:
    """
    Update counters in a metrics hash in Redis.
    e.g. messages=1, audio_minutes=2.5, images=1, etc.
    """
    key = redis_key_user_metrics(user_id)
    pipe = redis_client.pipeline(transaction=True)
    for field, value in kwargs.items():
        if isinstance(value, (int, float)):
            pipe.hincrbyfloat(key, field, float(value))
        else:
            # ignore non-numeric for now
            pass
    pipe.execute()


async def get_user_metrics(user_id: int) -> Dict[str, Any]:
    key = redis_key_user_metrics(user_id)
    data = await redis_client.hgetall(key)
    return data or {}


async def record_response_time(user_id: int, elapsed_sec: float) -> None:
    key = redis_key_user_metrics(user_id)
    pipe = redis_client.pipeline(transaction=True)
    pipe.hincrbyfloat(key, "response_time_total_sec", float(elapsed_sec))
    pipe.hincrby(key, "response_count", 1)
    await pipe.execute()


async def get_average_response_time(user_id: int) -> Optional[float]:
    metrics = await get_user_metrics(user_id)
    total = float(metrics.get("response_time_total_sec", 0.0))
    count = float(metrics.get("response_count", 0.0))
    if count == 0:
        return None
    return total / count


# --------------------------------------------------
# Image generation helpers
# --------------------------------------------------


async def can_generate_image(user_id: int) -> bool:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = redis_key_user_daily_image(user_id, today)
    count = await redis_client.get(key)
    if not count:
        return True
    return int(count) < IMAGE_DAILY_LIMIT


async def increment_image_usage(user_id: int) -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = redis_key_user_daily_image(user_id, today)
    pipe = redis_client.pipeline(transaction=True)
    pipe.incr(key, 1)
    pipe.expire(key, 60 * 60 * 24 * 2)  # 2 days TTL for safety
    await pipe.execute()


async def generate_image(prompt: str) -> Optional[str]:
    """
    Call OpenAI image model and return an image URL.
    (Using URL variant is easiest for Discord.)
    """
    try:
        result = openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        if result.data and result.data[0].url:
            return result.data[0].url
    except Exception as e:
        logger.exception("Error generating image: %s", e)
        return None
    return None


# --------------------------------------------------
# Audio handling helpers
# --------------------------------------------------


async def download_file(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


async def transcribe_audio_bytes(file_bytes: bytes, file_name: str) -> Dict[str, Any]:
    """
    Send raw audio bytes to OpenAI Whisper / transcription model.
    Return dict with { 'text': ..., 'duration_sec': float }
    """
    from io import BytesIO

    try:
        audio_file = BytesIO(file_bytes)
        audio_file.name = file_name

        # Using Whisper-style endpoint:
        transcript = openai_client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",  # or "whisper-1" depending on your account
            file=audio_file,
            response_format="json"
        )
        # Some models return text directly; adapt as needed
        text = transcript.text if hasattr(transcript, "text") else transcript.get("text", "")

        # We often don't get exact duration from API; approximate as 0 for now
        duration_sec = 0.0

        return {"text": text, "duration_sec": duration_sec}

    except Exception as e:
        logger.exception("Error transcribing audio: %s", e)
        raise


async def save_pending_audio(user_id: int, data: Dict[str, Any]) -> None:
    key = redis_key_user_pending_audio(user_id)
    await redis_client.set(key, json.dumps(data), ex=60 * 30)  # 30 min TTL


async def get_pending_audio(user_id: int) -> Optional[Dict[str, Any]]:
    key = redis_key_user_pending_audio(user_id)
    raw = await redis_client.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def clear_pending_audio(user_id: int) -> None:
    key = redis_key_user_pending_audio(user_id)
    await redis_client.delete(key)


async def set_audio_mode_pending(user_id: int, mode: str) -> None:
    key = redis_key_user_audio_mode(user_id)
    await redis_client.set(key, mode, ex=60 * 30)


async def get_audio_mode_pending(user_id: int) -> Optional[str]:
    key = redis_key_user_audio_mode(user_id)
    return await redis_client.get(key)


async def clear_audio_mode_pending(user_id: int) -> None:
    key = redis_key_user_audio_mode(user_id)
    await redis_client.delete(key)


# --------------------------------------------------
# Asana integration helpers
# --------------------------------------------------


async def create_asana_project_for_user(user: discord.User, onboarding: Dict[str, Any]) -> Optional[str]:
    """
    Duplicate the Asana template into a new project for this user.
    Store project GID in Redis on success.
    """
    if not ASANA_ACCESS_TOKEN or not ASANA_TEMPLATE_GID:
        logger.warning("Asana not configured, skipping project creation for user %s", user.id)
        return None

    url = f"https://app.asana.com/api/1.0/projects/{ASANA_TEMPLATE_GID}/duplicate"
    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    project_name = f"{user.display_name} – Coaching Program"

    payload = {
        "data": {
            "name": project_name,
            "include": ["tasks", "notes", "assignee", "due_dates"],
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    logger.error("Asana duplicate error (%s): %s", resp.status, text)
                    return None

                data = await resp.json()
                new_project_gid = data["data"]["new_project"]["gid"]
                logger.info("Created Asana project %s for user %s", new_project_gid, user.id)

                # Save in Redis
                key = redis_key_user_asana_project(user.id)
                await redis_client.set(key, new_project_gid)
                return new_project_gid

    except Exception as e:
        logger.exception("Error creating Asana project: %s", e)
        return None


async def get_asana_project_gid(user_id: int) -> Optional[str]:
    key = redis_key_user_asana_project(user_id)
    return await redis_client.get(key)


async def fetch_asana_task_summary(project_gid: str) -> str:
    """
    Very high-level Asana project summary for check-ins.
    (For v1 we keep it simple – just number of incomplete tasks due today / overdue.)
    """
    if not ASANA_ACCESS_TOKEN:
        return "Asana not configured."

    headers = {
        "Authorization": f"Bearer {ASANA_ACCESS_TOKEN}",
    }

    today = datetime.utcnow().date().isoformat()

    tasks_url = "https://app.asana.com/api/1.0/tasks"
    params = {
        "project": project_gid,
        "completed_since": "now",
        "opt_fields": "gid,name,completed,due_on",
        "limit": 100
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(tasks_url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.error("Asana tasks fetch error %s: %s", resp.status, await resp.text())
                    return "I couldn't fetch your Asana tasks yet."

                data = await resp.json()
                tasks = data.get("data", [])

        overdue = 0
        due_today = 0

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

        parts = []
        if overdue:
            parts.append(f"{overdue} overdue task(s)")
        if due_today:
            parts.append(f"{due_today} due today")
        if not parts:
            return "You're fully caught up on your Asana tasks for now."

        return "You currently have " + " and ".join(parts) + "."

    except Exception as e:
        logger.exception("Error summarizing Asana tasks: %s", e)
        return "I couldn't fetch your Asana tasks yet."


# --------------------------------------------------
# Onboarding flow
# --------------------------------------------------

ONBOARDING_QUESTIONS = [
    ("program_focus", "What is your current business focus? (e.g. agency niche, coaching offer, etc.)"),
    ("revenue_goal", "What is your target monthly revenue in the next 5–6 months?"),
    ("current_mrr", "What is your current consistent monthly revenue?"),
    ("biggest_constraints", "What do you feel are your 2–3 biggest constraints right now (lead flow, offers, sales, delivery, leadership, etc.)?"),
    ("time_commitment", "How many focused hours per week can you realistically dedicate to working the plan?"),
    ("team_context", "Who else is on your team (setters, closers, ops, media buyers, etc.)? Be brief."),
]

ONBOARDING_DONE_FLAG = "done"


async def is_user_onboarded(user_id: int) -> bool:
    data = await redis_client.hget(redis_key_user_onboarding(user_id), ONBOARDING_DONE_FLAG)
    return data == "1"


async def get_user_onboarding(user_id: int) -> Dict[str, Any]:
    key = redis_key_user_onboarding(user_id)
    data = await redis_client.hgetall(key)
    return data or {}


async def save_onboarding_answer(user_id: int, field: str, answer: str) -> None:
    key = redis_key_user_onboarding(user_id)
    await redis_client.hset(key, field, answer)


async def mark_onboarding_done(user_id: int) -> None:
    key = redis_key_user_onboarding(user_id)
    await redis_client.hset(key, ONBOARDING_DONE_FLAG, "1")


async def start_onboarding_conversation(user: discord.User, thread: discord.Thread) -> None:
    """
    Start the onboarding Q&A sequence in the AI thread.
    We'll store a little state in Redis: which question index the user is on.
    """
    key = redis_key_user_onboarding(user.id)
    await redis_client.hset(key, "current_index", 0)
    await thread.send(
        f"👋 Hey {user.mention}! Before we dive in, I want to get a quick picture of your business so I can coach you properly.\n\n"
        f"I'll ask you a few short questions – just answer in this thread.\n\n"
        f"**Q1:** {ONBOARDING_QUESTIONS[0][1]}"
    )


async def handle_onboarding_answer(
    user: discord.User,
    thread: discord.Thread,
    message: discord.Message
) -> bool:
    """
    Process a message as part of onboarding if the user is mid-flow.
    Returns True if the message was consumed by onboarding handler.
    """
    key = redis_key_user_onboarding(user.id)
    data = await redis_client.hgetall(key)
    if not data:
        return False

    if data.get(ONBOARDING_DONE_FLAG) == "1":
        return False

    current_index_raw = data.get("current_index")
    if current_index_raw is None:
        return False

    try:
        current_index = int(current_index_raw)
    except ValueError:
        current_index = 0

    # Save answer for current question
    if 0 <= current_index < len(ONBOARDING_QUESTIONS):
        field, question_text = ONBOARDING_QUESTIONS[current_index]
        await save_onboarding_answer(user.id, field, message.content.strip())

        current_index += 1
        await redis_client.hset(key, "current_index", current_index)

    # If there are more questions, ask next
    if current_index < len(ONBOARDING_QUESTIONS):
        field, question_text = ONBOARDING_QUESTIONS[current_index]
        await thread.send(f"**Q{current_index + 1}:** {question_text}")
        return True

    # We are done
    await mark_onboarding_done(user.id)
    onboarding = await get_user_onboarding(user.id)
    await thread.send(
        "🔥 Awesome, I’ve got what I need.\n"
        "I'm now going to generate a structured game plan and set up your Asana project using our program template.\n"
        "This might take a moment."
    )

    # Trigger Asana project creation (fire & forget)
    asyncio.create_task(create_asana_project_for_user(user, onboarding))

    # Also store a brief memory summarizing onboarding so AI has context
    summary_text = (
        "Onboarding summary:\n"
        f"- Program focus: {onboarding.get('program_focus', 'n/a')}\n"
        f"- Revenue goal: {onboarding.get('revenue_goal', 'n/a')}\n"
        f"- Current MRR: {onboarding.get('current_mrr', 'n/a')}\n"
        f"- Biggest constraints: {onboarding.get('biggest_constraints', 'n/a')}\n"
        f"- Time commitment: {onboarding.get('time_commitment', 'n/a')}\n"
        f"- Team context: {onboarding.get('team_context', 'n/a')}\n"
    )
    await redis_client.set(redis_key_user_memory(user.id), summary_text)

    await thread.send(
        "✅ You’re onboarded.\n\n"
        "From here on, you can:\n"
        "- Ask me anything about sales, setting, Meta ads, YouTube, organic, and scaling your program.\n"
        "- Drop call recordings for deep breakdowns.\n"
        "- Use `!myinfo` to see what I remember about you.\n"
        "- Use `!stats` to see your usage.\n"
        "- Use `!image` to generate creatives (within daily limits).\n\n"
        "Let’s get to work. What do you want to work on right now?"
    )
    return True


# --------------------------------------------------
# OpenAI assistant call helpers
# --------------------------------------------------


async def call_assistant_for_user(
    user_id: int,
    thread_id: str,
    prompt: str,
    extra_system_instructions: Optional[str] = None
) -> str:
    """
    Send a message into the user's OpenAI thread and get assistant response.
    """
    system_instructions = textwrap.dedent(
        """
        You are Derek's AI coach for Christian agency owners and coaches.
        You help with:
        - sales calls & objection handling
        - setting / outbound frameworks
        - Meta ads and creative strategy
        - YouTube & organic content
        - offer & positioning
        - scheduling & accountability to a 5–6 month scaling plan.

        Always be direct, clear, and practical. Use bullets and structure where it helps.
        Avoid super long walls of text; break big ideas into steps.
        If user mentions faith, respect it and integrate it without being cheesy.

        You have access to some onboarding info and memory stored outside of this call. If the user asks about their plan, respond based on what you know + what they say now.
        """
    )

    if extra_system_instructions:
        system_instructions += "\n\n" + extra_system_instructions

    start_time = datetime.utcnow()

    # Add user message
    openai_client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt
    )

    # Run
    run = openai_client.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        instructions=system_instructions,
    )

    if run.status != "completed":
        logger.warning("Run not completed for user %s: %s", user_id, run.status)
        return "I had an issue completing that request. Try again in a moment."

    # Get last assistant message
    messages = openai_client.beta.threads.messages.list(
        thread_id=thread_id,
        order="desc",
        limit=1
    )
    for msg in messages.data:
        if msg.role == "assistant":
            content_parts = msg.content
            for part in content_parts:
                if part.type == "text":
                    text_value = part.text.value
                    elapsed = (datetime.utcnow() - start_time).total_seconds()
                    await record_response_time(user_id, elapsed)
                    await update_user_metrics(user_id, messages=1)
                    return text_value

    elapsed = (datetime.utcnow() - start_time).total_seconds()
    await record_response_time(user_id, elapsed)
    return "I wasn't able to generate a response message. Try again."


async def call_assistant_for_call_analysis(
    user_id: int,
    thread_id: str,
    transcript: str
) -> str:
    """
    Ask the assistant to act as a call grader and output a structured analysis.
    """
    extra_instructions = textwrap.dedent(
        """
        The user has provided a transcript of a SALES or SETTING call.
        Your job is to analyze and coach.

        1. Give a concise summary of the call.
        2. Identify what the rep did well.
        3. Identify the biggest improvement opportunities.
        4. Extract key objections and how they were handled.
        5. Give specific lines they could have said instead (scripts).
        6. Classify red flags into these buckets and label them clearly:

           - 💸 Budget flags
           - 🟧 Timeline objections
           - 😕 Uncertainty indicators
           - 🚫 Bad fit warnings
           - 🧊 Lead coldness signals
           - 💀 “Never buying” traits

        7. End with the top 3 actions they should take on the very next call.

        Keep it punchy and practical. No generic fluff.
        """
    )

    prompt = f"Here is the call transcript:\n\n{transcript}"
    return await call_assistant_for_user(user_id, thread_id, prompt, extra_instructions)


# --------------------------------------------------
# Discord thread + mapping helpers
# --------------------------------------------------


async def get_or_create_discord_thread(ctx: commands.Context) -> discord.Thread:
    """
    Get or create the user's private AI thread in the current channel.
    """
    user_id = ctx.author.id
    key = redis_key_user_discord_thread(user_id)
    existing_id = await redis_client.get(key)
    if existing_id:
        channel = ctx.guild.get_thread(int(existing_id))
        if channel and isinstance(channel, discord.Thread):
            return channel

    # Create new private thread
    thread_name = f"{ctx.author.display_name}-ai"
    parent = ctx.channel
    thread = await parent.create_thread(
        name=thread_name,
        type=discord.ChannelType.private_thread,
        invitable=False
    )

    await thread.add_user(ctx.author)

    await redis_client.set(key, str(thread.id))
    await redis_client.set(redis_key_thread_owner(thread.id), str(user_id))

    return thread


async def get_thread_owner_user_id(thread: discord.Thread) -> Optional[int]:
    key = redis_key_thread_owner(thread.id)
    val = await redis_client.get(key)
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


# --------------------------------------------------
# Daily check-in background task
# --------------------------------------------------


def utc_now_cst_hour() -> int:
    """
    Returns the current hour in CST (naive).
    """
    now_utc = datetime.utcnow()
    cst_time = now_utc + timedelta(hours=CST_UTC_OFFSET_HOURS)
    return cst_time.hour


@tasks.loop(minutes=10.0)
async def daily_checkins_loop():
    """
    Every 10 minutes, check if it's around 8 AM CST, and if so,
    run check-ins for all program members (simple v1).
    """
    try:
        hour_cst = utc_now_cst_hour()
        if hour_cst != DAILY_CHECKIN_HOUR_CST:
            return

        logger.info("Running daily check-ins loop at CST hour %s", hour_cst)

        # For now, just iterate program members
        for user_id in PROGRAM_USER_IDS:
            user = bot.get_user(user_id)
            if not user:
                # Try fetching
                try:
                    user = await bot.fetch_user(user_id)
                except Exception:
                    continue

            # Get their Discord thread
            thread_id_str = await redis_client.get(redis_key_user_discord_thread(user_id))
            if not thread_id_str:
                continue

            thread = bot.get_channel(int(thread_id_str))
            if not thread or not isinstance(thread, discord.Thread):
                continue

            # Get Asana summary if exists
            project_gid = await get_asana_project_gid(user_id)
            if project_gid:
                summary = await fetch_asana_task_summary(project_gid)
            else:
                summary = "We haven't linked your Asana project yet."

            msg = (
                f"⏰ **Daily Check-in**\n\n"
                f"{summary}\n\n"
                f"Reply here with:\n"
                f"- What you completed yesterday\n"
                f"- What you will complete today\n"
                f"- Anything that could block you\n"
            )
            try:
                await thread.send(msg)
            except Exception as e:
                logger.exception("Error sending daily checkin to user %s: %s", user_id, e)

    except Exception as e:
        logger.exception("Error in daily_checkins_loop: %s", e)


@daily_checkins_loop.before_loop
async def before_daily_checkins_loop():
    await bot.wait_until_ready()
    logger.info("Daily check-ins loop started.")


# --------------------------------------------------
# Commands
# --------------------------------------------------


@bot.event
async def on_ready():
    logger.info("Bot is ready — Logged in as %s", bot.user)
    if not daily_checkins_loop.is_running():
        daily_checkins_loop.start()


@bot.command(name="start")
async def cmd_start(ctx: commands.Context):
    """
    Entry point: creates user's AI thread & kicks off onboarding if needed.
    """
    user_id = ctx.author.id

    if not is_program_member(user_id):
        await ctx.reply(
            "Hey! You’re not in the program list I have. "
            "DM Derek if you think this is a mistake and he’ll add you."
        )
        return

    thread = await get_or_create_discord_thread(ctx)
    await ctx.reply(
        f"✅ Your private AI thread is ready: {thread.mention}\n"
        f"I'll handle everything inside that thread so we don't spam the main channel."
    )

    # Ensure OpenAI thread exists as well
    await get_or_create_openai_thread(user_id)

    onboarded = await is_user_onboarded(user_id)
    if not onboarded:
        await start_onboarding_conversation(ctx.author, thread)
    else:
        await thread.send(
            f"Welcome back, {ctx.author.mention}. You’re already onboarded.\n"
            "Ask me anything or drop a call recording, and I’ll jump in."
        )


@bot.command(name="image")
async def cmd_image(ctx: commands.Context, *, prompt: str):
    """
    Generate a marketing / creative image.
    """
    user_id = ctx.author.id

    if not is_program_member(user_id):
        await ctx.reply("This command is only available to program members.")
        return

    if not await can_generate_image(user_id):
        await ctx.reply(
            f"🚫 You’ve hit your image limit for today. "
            f"Daily cap: {IMAGE_DAILY_LIMIT} images."
        )
        return

    await ctx.reply("🎨 Generating image, one sec...")

    img_url = await generate_image(prompt)
    if not img_url:
        await ctx.send(
            "❌ Image generation failed. Check that your OpenAI org is verified "
            "and that `gpt-image-1` is enabled."
        )
        return

    await increment_image_usage(user_id)
    await update_user_metrics(user_id, images=1)

    embed = discord.Embed(title="Generated Image", description=prompt)
    embed.set_image(url=img_url)
    await ctx.send(embed=embed)


@bot.command(name="myinfo")
async def cmd_myinfo(ctx: commands.Context):
    """
    Show what the bot remembers about the user.
    """
    user_id = ctx.author.id

    if not is_program_member(user_id):
        await ctx.reply("This is only for program members.")
        return

    memory = await redis_client.get(redis_key_user_memory(user_id))
    onboarding = await get_user_onboarding(user_id)

    if not memory and not onboarding:
        await ctx.reply("I don't have any saved memory for you yet.")
        return

    parts = []
    if onboarding:
        parts.append("**Onboarding data:**")
        for k, v in onboarding.items():
            if k == ONBOARDING_DONE_FLAG:
                continue
            parts.append(f"- **{k}**: {v}")

    if memory:
        parts.append("\n**Summary memory:**")
        parts.append(memory)

    text = "\n".join(parts)
    for chunk in chunk_text_for_discord(text):
        await ctx.reply(chunk)


@bot.command(name="resetmemory")
async def cmd_resetmemory(ctx: commands.Context):
    """
    Wipe AI memory for this user.
    """
    user_id = ctx.author.id

    if not is_program_member(user_id):
        await ctx.reply("This is only for program members.")
        return

    await redis_client.delete(redis_key_user_memory(user_id))
    await redis_client.delete(redis_key_user_onboarding(user_id))
    await ctx.reply("🧹 Your memory and onboarding data have been reset. Use `!start` to re-onboard if needed.")


@bot.command(name="inspectmemory")
async def cmd_inspectmemory(ctx: commands.Context, user: discord.User):
    """
    Admin-only: inspect another user's memory.
    """
    invoker_id = ctx.author.id
    if not is_program_admin(invoker_id):
        await ctx.reply("You don't have permission to use this command.")
        return

    memory = await redis_client.get(redis_key_user_memory(user.id))
    onboarding = await get_user_onboarding(user.id)

    if not memory and not onboarding:
        await ctx.reply(f"No memory/onboarding saved for {user.mention}.")
        return

    parts = [f"📂 **Memory for {user} ({user.id})**"]
    if onboarding:
        parts.append("\n**Onboarding:**")
        for k, v in onboarding.items():
            if k == ONBOARDING_DONE_FLAG:
                continue
            parts.append(f"- {k}: {v}")

    if memory:
        parts.append("\n**Summary memory:**")
        parts.append(memory)

    text = "\n".join(parts)
    for chunk in chunk_text_for_discord(text):
        await ctx.reply(chunk)


@bot.command(name="stats")
async def cmd_stats(ctx: commands.Context):
    """
    Show user-level usage stats.
    """
    user_id = ctx.author.id

    if not is_program_member(user_id):
        await ctx.reply("This is only for program members.")
        return

    metrics = await get_user_metrics(user_id)
    avg_rt = await get_average_response_time(user_id)

    msg_count = float(metrics.get("messages", 0))
    audio_minutes = float(metrics.get("audio_minutes", 0))
    images = int(float(metrics.get("images", 0)))
    response_count = float(metrics.get("response_count", 0))

    lines = [
        "📊 **Your usage stats**",
        f"- Messages processed: **{int(msg_count)}**",
        f"- Audio minutes analyzed: **{audio_minutes:.1f}**",
        f"- Images generated: **{images}**",
        f"- AI responses: **{int(response_count)}**",
    ]
    if avg_rt is not None:
        lines.append(f"- Average response time: **{avg_rt:.1f} sec**")

    await ctx.reply("\n".join(lines))


@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    """
    List all commands and capabilities.
    """
    text = textwrap.dedent(
        """
        🤖 **Derek AI – Commands**

        `!start` – Create / open your private AI thread and (if needed) run onboarding.
        `!image <prompt>` – Generate a creative (up to your daily limit).
        `!myinfo` – Show what I remember about you and your onboarding.
        `!resetmemory` – Wipe your memory & onboarding (soft reset).
        `!stats` – See your usage stats (messages, audio minutes, images, etc.).
        `!inspectmemory <user>` – (Admin) Inspect another user's memory.
        `!help` – Show this message.

        Inside your private AI thread:
        - Just type questions like normal – I’ll reply.
        - Drop audio files – I’ll ask if it’s a **call** to grade or just a **question**.
        - I’ll also do daily check-ins and Asana accountability for program members.
        """
    )
    await ctx.reply(text)


# --------------------------------------------------
# on_message – routing messages to AI + audio flow + onboarding
# --------------------------------------------------


@bot.event
async def on_message(message: discord.Message):
    # Ignore ourselves and other bots
    if message.author.bot:
        return

    # Always let command processing happen
    await bot.process_commands(message)

    # Only care about messages in threads that we manage
    if isinstance(message.channel, discord.Thread):
        thread = message.channel
        user = message.author

        # Check if this thread belongs to a specific user
        owner_id = await get_thread_owner_user_id(thread)
        if owner_id is None or owner_id != user.id:
            # Not the owner's personal AI thread – ignore
            return

        # Only handle messages from program members
        if not is_program_member(user.id):
            return

        # If message starts with command prefix, don't treat as free-form AI
        if message.content.startswith("!"):
            return

        # 1) Check if user is mid-onboarding
        consumed_by_onboarding = await handle_onboarding_answer(user, thread, message)
        if consumed_by_onboarding:
            return

        # 2) Check if there is an audio mode pending (call vs question)
        audio_mode_pending = await get_audio_mode_pending(user.id)
        if audio_mode_pending:
            lower = message.content.lower().strip()
            pending = await get_pending_audio(user.id)
            if not pending:
                await clear_audio_mode_pending(user.id)
                return

            transcript = pending.get("transcript", "")
            duration_sec = float(pending.get("duration_sec", 0.0))

            if "call" in lower:
                await thread.send("📞 Got it – treating that as a **call**. Grading now...")
                analysis = await call_assistant_for_call_analysis(
                    user.id,
                    await get_or_create_openai_thread(user.id),
                    transcript,
                )
                for chunk in chunk_text_for_discord(analysis):
                    await thread.send(chunk)
                await update_user_metrics(user.id, audio_minutes=duration_sec / 60.0)
                await clear_audio_mode_pending(user.id)
                await clear_pending_audio(user.id)
                return

            if "question" in lower or "qa" in lower or "q&a" in lower:
                await thread.send("🎧 Cool – treating it as a **question**. Answering now...")
                openai_thread_id = await get_or_create_openai_thread(user.id)
                answer = await call_assistant_for_user(
                    user.id,
                    openai_thread_id,
                    f"User sent a voice note. Here is the transcript:\n\n{transcript}",
                )
                for chunk in chunk_text_for_discord(answer):
                    await thread.send(chunk)
                await update_user_metrics(user.id, audio_minutes=duration_sec / 60.0)
                await clear_audio_mode_pending(user.id)
                await clear_pending_audio(user.id)
                return

            # If they replied something else while mode pending, we still treat as normal text question
            # but keep pending state to give them another shot.
            # Fall through to AI text response below.

        # 3) If message has an audio attachment, handle transcription + ask mode
        if message.attachments:
            # We only handle first audio for now
            audio_attachment = None
            for att in message.attachments:
                if att.content_type and att.content_type.startswith(("audio", "video")):
                    audio_attachment = att
                    break

            if audio_attachment:
                await thread.send("🎧 Received audio. Transcribing now...")
                try:
                    file_bytes = await audio_attachment.read()
                    transcription = await transcribe_audio_bytes(file_bytes, audio_attachment.filename)
                except Exception:
                    await thread.send("❌ I couldn't transcribe that audio. Try again with a clearer file.")
                    return

                transcript = transcription["text"]
                duration = float(transcription.get("duration_sec", 0.0))

                # Save pending audio & ask how to treat it
                await save_pending_audio(
                    user.id,
                    {"transcript": transcript, "duration_sec": duration}
                )
                await set_audio_mode_pending(user.id, "awaiting_mode")

                await thread.send(
                    "I’ve transcribed your audio.\n\n"
                    "Should I treat this as:\n"
                    "- a **sales/setting call** to grade (`call`), or\n"
                    "- a **quick question** you want answered (`question`)?\n\n"
                    "Reply with `call` or `question`."
                )
                return

        # 4) Otherwise, treat as normal text question to AI
        content = message.content.strip()
        if not content:
            return

        openai_thread_id = await get_or_create_openai_thread(user.id)
        reply_text = await call_assistant_for_user(user.id, openai_thread_id, content)

        for chunk in chunk_text_for_discord(reply_text):
            await thread.send(chunk)

    # If not in a managed thread, do nothing extra


# --------------------------------------------------
# Run bot
# --------------------------------------------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not set. Exiting.")
    else:
        bot.run(DISCORD_TOKEN)
