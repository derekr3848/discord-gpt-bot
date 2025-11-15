import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import io

# ----------------------------
# CONFIG
# ----------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

client_openai = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

user_threads = {}       # maps discord user_id → OpenAI thread_id
active_channels = {}    # maps channel_id → user_id


# ----------------------------
# MESSAGE CHUNKING FIX (IMPORTANT)
# ----------------------------
async def send_long_message(channel, text):
    """Splits long messages so Discord doesn't reject them."""
    limit = 1900
    chunks = [text[i:i + limit] for i in range(0, len(text), limit)]

    for chunk in chunks:
        await channel.send(chunk)


# ----------------------------
# OPENAI HELPERS
# ----------------------------
def create_user_thread():
    """Creates a new OpenAI thread for a user."""
    thread = client_openai.beta.threads.create()
    return thread.id


def run_assistant(thread_id, user_input=None, file_id=None):
    """Runs our assistant on a thread with text or audio."""
    messages = []

    if user_input:
        messages.append({"role": "user", "content": user_input})

    if file_id:
        messages.append({
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze this sales or setting call."},
                {"type": "input_audio", "audio_id": file_id}
            ]
        })

    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=messages
    )

    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    msgs = client_openai.beta.threads.messages.list(thread_id=thread_id)
    return msgs.data[0].content[0].text.value


# ----------------------------
# AUDIO HANDLING
# ----------------------------
async def transcribe_audio(url):
    """Downloads and transcribes Discord audio → returns transcript."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()

    transcript = client_openai.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=("audio.ogg", data)
    )

    return transcript.text


# ----------------------------
# START COMMAND — CREATES USER'S PRIVATE THREAD
# ----------------------------
@bot.command()
async def start(ctx):
    user = ctx.author

    # Create OpenAI thread if new user
    if user.id not in user_threads:
        user_threads[user.id] = create_user_thread()

    # Create a private thread for this user
    thread = await ctx.channel.create_thread(
        name=f"{user.name}-ai-chat",
        type=discord.ChannelType.private_thread
    )

    active_channels[thread.id] = user.id

    await thread.send(
        f"👋 Welcome **{user.name}**!\n\n"
        f"This is your private AI channel.\n"
        f"Just type normally — no commands required.\n\n"
        f"🎯 I specialize in:\n"
        f"- Sales call analysis\n"
        f- Setter performance feedback\n"
        f"- Meta ads + YouTube strategy\n"
        f"- Organic + content marketing\n"
        f"- Christian agency & coaching business scaling\n"
        f"- Image analysis\n"
        f"- Audio / call analysis\n\n"
        f"How can I help you today?"
    )


# ----------------------------
# ON MESSAGE — Handles text, images, audio
# ----------------------------
@bot.event
async def on_message(message):
    # ignore bot messages
    if message.author.bot:
        return

    channel_id = message.channel.id

    # Not an AI thread → allow commands
    if channel_id not in active_channels:
        await bot.process_commands(message)
        return

    user_id = active_channels[channel_id]
    thread_id = user_threads[user_id]

    # ----------------------------
    # AUDIO FILES
    # ----------------------------
    if message.attachments:
        attachment = message.attachments[0]

        if attachment.content_type and "audio" in attachment.content_type:
            await message.channel.send("🎧 Received audio. Transcribing...")

            transcript = await transcribe_audio(attachment.url)

            await message.channel.send("📄 Transcription complete. Analyzing...")

            result = run_assistant(thread_id, user_input=transcript)

            await send_long_message(message.channel, result)
            return

    # ----------------------------
    # TEXT MESSAGE
    # ----------------------------
    user_text = message.content.strip()
    if user_text:
        reply = run_assistant(thread_id, user_input=user_text)
        await send_long_message(message.channel, reply)


# ----------------------------
# BOT READY
# ----------------------------
@bot.event
async def on_ready():
    print(f"🤖 Bot ready — Logged in as {bot.user}")


bot.run(DISCORD_TOKEN)
