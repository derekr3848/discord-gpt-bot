import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

client_openai = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

user_threads = {}
active_channels = {}


# ----------------------------
# MESSAGE CHUNKING FIX
# ----------------------------
async def send_long_message(channel, text):
    limit = 1900
    chunks = [text[i:i+limit] for i in range(0, len(text), limit)]
    for c in chunks:
        await channel.send(c)


# ----------------------------
# OPENAI HELPERS
# ----------------------------
def create_user_thread():
    thread = client_openai.beta.threads.create()
    return thread.id


def run_assistant(thread_id, user_input=None, file_id=None):
    messages = []

    if user_input:
        messages.append({"role": "user", "content": user_input})

    if file_id:
        messages.append({
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze this call."},
                {"type": "input_audio", "audio_id": file_id}
            ]
        })

    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=messages
    )

    client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID
    )

    msgs = client_openai.beta.threads.messages.list(thread_id=thread_id)
    return msgs.data[0].content[0].text.value


# ----------------------------
# AUDIO HANDLING
# ----------------------------
async def transcribe_audio(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()

    transcript = client_openai.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=("audio.ogg", data)
    )

    return transcript.text


# ----------------------------
# START COMMAND → MAKES PRIVATE THREAD
# ----------------------------
@bot.command()
async def start(ctx):
    user = ctx.author

    if user.id not in user_threads:
        user_threads[user.id] = create_user_thread()

    thread = await ctx.channel.create_thread(
        name=f"{user.name}-ai-chat",
        type=discord.ChannelType.private_thread
    )

    active_channels[thread.id] = user.id

    welcome_message = (
        f"👋 **Welcome {user.name}!**\n\n"
        f"This is your **private AI chat thread**.\n"
        f"Just talk normally — no commands needed.\n\n"
        f"### 🤖 I can help you with:\n"
        f"- Sales call breakdowns\n"
        f"- Setter call analysis\n"
        f"- Meta ads strategy & audits\n"
        f"- YouTube content planning\n"
        f"- Organic content strategy\n"
        f"- Full marketing support for Christian agency owners/coaches\n"
        f"- Image analysis\n"
        f"- Audio/call feedback\n\n"
        f"How can I help you today?"
    )

    await thread.send(welcome_message)


# ----------------------------
# MESSAGE HANDLING
# ----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_id = message.channel.id

    if channel_id not in active_channels:
        await bot.process_commands(message)
        return

    user_id = active_channels[channel_id]
    thread_id = user_threads[user_id]

    # AUDIO messages
    if message.attachments:
        att = message.attachments[0]
        if att.content_type and "audio" in att.content_type:
            await message.channel.send("🎧 Transcribing audio...")
            transcript = await transcribe_audio(att.url)

            await message.channel.send("📄 Analyzing call...")

            reply = run_assistant(thread_id, user_input=transcript)
            await send_long_message(message.channel, reply)
            return

    # TEXT messages
    if message.content.strip():
        reply = run_assistant(thread_id, user_input=message.content.strip())
        await send_long_message(message.channel, reply)


# ----------------------------
# BOT READY
# ----------------------------
@bot.event
async def on_ready():
    print(f"🤖 Bot ready — logged in as {bot.user}")


bot.run(DISCORD_TOKEN)
