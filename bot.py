import os
import io
import base64
import discord
from discord.ext import commands
from openai import OpenAI

# ========= CONFIG =========

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# Your unified assistant (sales, setting, meta, YouTube, organic, marketing)
ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
client = OpenAI(api_key=OPENAI_KEY)

# Per-user mappings
# user_id -> OpenAI thread id
user_threads = {}
# user_id -> Discord thread channel id
discord_threads = {}


# ========= EVENTS =========

@bot.event
async def on_ready():
    print(f"✅ Bot ready — logged in as {bot.user}")


# ========= COMMAND: !start =========

@bot.command()
async def start(ctx: commands.Context):
    """Creates a personal AI thread for the user."""
    user = ctx.author

    # Don't allow in DMs
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("Use this command inside a server channel, not DMs.")
        return

    # If user already has a thread, reuse it
    if user.id in discord_threads:
        existing_thread_id = discord_threads[user.id]
        existing_thread = ctx.guild.get_channel(existing_thread_id)
        if existing_thread:
            await ctx.send(
                f"{user.mention} you already have an AI thread: {existing_thread.mention}"
            )
            return

    # 1) Create Discord private thread
    ai_thread = await ctx.channel.create_thread(
        name=f"{user.name}-ai-thread",
        type=discord.ChannelType.private_thread,
    )
    discord_threads[user.id] = ai_thread.id

    await ai_thread.send(
        f"👋 {user.mention}, this is your **personal AI assistant thread**.\n"
        "Just talk normally — no commands needed.\n\n"
        "**Tips:**\n"
        "• Ask about sales, setting, Meta ads, YouTube, organic, offers, etc.\n"
        "• Type `image: your prompt` to generate an image.\n"
        "• Upload a call recording (audio file) to get call analysis."
    )

    # 2) Create OpenAI thread for this user (memory)
    thread_obj = client.beta.threads.create()
    user_threads[user.id] = thread_obj.id

    await ctx.send(f"✅ Your personal AI thread is ready → {ai_thread.mention}")


# ========= HELPERS =========

async def send_ai_text_reply(message: discord.Message, user_id: int, text: str):
    """Send user text to their OpenAI assistant thread and reply back."""
    openai_thread_id = user_threads[user_id]

    # Add user message to assistant thread
    client.beta.threads.messages.create(
        thread_id=openai_thread_id,
        role="user",
        content=text,
    )

    # Run assistant
    run = client.beta.threads.runs.create_and_poll(
        thread_id=openai_thread_id,
        assistant_id=ASSISTANT_ID,
    )

    # Get assistant's reply
    ai_reply = ""
    messages = client.beta.threads.messages.list(thread_id=openai_thread_id)

    for msg in messages.data:
        if msg.role == "assistant":
            ai_reply = msg.content[0].text.value
            break

    if ai_reply:
        await message.channel.send(ai_reply)
    else:
        await message.channel.send("⚠️ I didn’t get a response from the AI.")


async def handle_image_prompt(message: discord.Message, user_id: int, prompt: str):
    """Generate an image from a prompt and send it to Discord."""
    try:
        await message.channel.send("🎨 Generating your image…")

        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
        )

        b64_data = response.data[0].b64_json
        image_bytes = base64.b64decode(b64_data)
        file = discord.File(io.BytesIO(image_bytes), filename="ai_image.png")

        await message.channel.send(
            f"🖼 **Image generated:** `{prompt}`", file=file
        )
    except Exception as e:
        await message.channel.send(f"⚠️ Error generating image: `{e}`")


async def handle_audio_file(message: discord.Message, user_id: int):
    """Transcribe an audio file and send the transcript to the assistant."""
    attachment = message.attachments[0]
    filename = attachment.filename.lower()

    # Only handle common audio formats
    if not filename.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
        return  # ignore non-audio files

    await message.channel.send("🎧 Received audio. Transcribing your call…")

    temp_path = f"/tmp/{attachment.filename}"
    await attachment.save(temp_path)

    try:
        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )

        transcript_text = transcription.text
        await message.channel.send("📝 Transcription complete. Analyzing now…")

        # Feed transcript into the same assistant + thread
        analysis_prompt = (
            "You are a Christian business/sales/marketing coach. "
            "Analyze this call transcript for sales, setting, offer, and marketing insights. "
            "Give a clear score (0-100), what they did well, mistakes, missed opportunities, "
            "and 5–10 specific tactical improvements. Here is the transcript:\n\n"
            f"{transcript_text}"
        )

        await send_ai_text_reply(message, user_id, analysis_prompt)

    except Exception as e:
        await message.channel.send(f"⚠️ Error processing audio: `{e}`")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ========= AUTO-REPLY LOGIC =========

@bot.event
async def on_message(message: discord.Message):
    # allow commands like !start
    await bot.process_commands(message)

    # ignore our own messages
    if message.author == bot.user:
        return

    user = message.author
    user_id = user.id

    # Only auto-reply in the user's dedicated thread
    if user_id not in discord_threads:
        return

    user_thread_channel_id = discord_threads[user_id]

    # If message is not in their AI thread, ignore
    if message.channel.id != user_thread_channel_id:
        return

    # If they sent an audio file -> handle sales/setting call analysis
    if message.attachments:
        await handle_audio_file(message, user_id)
        return

    # If they typed an image prompt
    content = (message.content or "").strip()
    if not content:
        return

    # image: prompt
    if content.lower().startswith("image:"):
        prompt = content[len("image:") :].strip()
        if not prompt:
            await message.channel.send("✏️ Please provide a prompt after `image:`.")
            return
        await handle_image_prompt(message, user_id, prompt)
        return

    # Otherwise, treat as normal chat to the assistant
    await send_ai_text_reply(message, user_id, content)


# ========= RUN =========

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
