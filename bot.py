import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import os
import base64

# --------------------------
# CONFIG
# --------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

client_openai = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

user_threads = {}  # {discord_user_id: { "thread_id": xxx, "ai_thread_id": yyy }}


# ----------------------------------------
# STARTUP
# ----------------------------------------
@bot.event
async def on_ready():
    print(f"Bot is ready — Logged in as {bot.user}")


# ================================================================
#  COMMAND: Create user thread
#  Creates:
#   • Discord thread
#   • OpenAI Assistant thread
#   • Saves mapping for auto conversation
# ================================================================
@bot.command()
async def start(ctx):
    user = ctx.author

    # Check if user already has thread
    if user.id in user_threads:
        thread_id = user_threads[user.id]["thread_id"]
        thread = ctx.guild.get_channel(thread_id)

        if thread:
            await ctx.reply(f"You already have a private chat thread here: {thread.mention}")
            return

    # Create Discord thread
    thread = await ctx.channel.create_thread(
        name=f"{user.display_name}'s AI Chat",
        type=discord.ChannelType.public_thread
    )

    # Create OpenAI thread
    ai_thread = client_openai.beta.threads.create()

    # Save mapping
    user_threads[user.id] = {
        "thread_id": thread.id,
        "ai_thread_id": ai_thread.id
    }

    await thread.send(f"👋 Hello {user.mention}! This is your private AI assistant thread.\n"
                      f"No commands needed — just talk normally and I will respond.")

    await ctx.reply(f"Your private AI chat is ready: {thread.mention}")


# ================================================================
#  MAIN LISTENER:
#    Auto Replies ONLY inside user thread
# ================================================================
@bot.event
async def on_message(message: discord.Message):
    # ignore bot messages
    if message.author == bot.user:
        return

    # Only reply inside a user's assigned thread
    for user_id, data in user_threads.items():
        if message.channel.id == data["thread_id"]:
            ai_thread_id = data["ai_thread_id"]

            # If message contains audio file → analyze call
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.filename.endswith((".mp3", ".wav", ".m4a", ".ogg")):
                        await process_audio(message, attachment, ai_thread_id)
                        return

                    if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        await process_image(message, attachment, ai_thread_id)
                        return

            # Normal text
            await process_text(message, ai_thread_id)
            return

    # Let commands still work
    await bot.process_commands(message)


# ================================================================
# PROCESS NORMAL TEXT
# ================================================================
async def process_text(message, ai_thread_id):
    user_msg = message.content

    # Add message to thread
    client_openai.beta.threads.messages.create(
        thread_id=ai_thread_id,
        role="user",
        content=user_msg
    )

    # Run assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=ai_thread_id,
        assistant_id=ASSISTANT_ID
    )

    # Fetch response
    msgs = client_openai.beta.threads.messages.list(thread_id=ai_thread_id)
    latest = msgs.data[0].content[0].text.value

    # Send back
    await message.channel.send(latest)


# ================================================================
# PROCESS IMAGE GENERATION
# ================================================================
async def process_image(message, attachment, ai_thread_id):
    await message.channel.send("🖼️ Image received. Analyzing...")

    # Download as base64
    img_bytes = await attachment.read()
    b64 = base64.b64encode(img_bytes).decode()

    # Upload to OpenAI
    result = client_openai.images.generate(
        model="gpt-image-1",
        prompt=f"Analyze and rewrite this image based on user request: {message.content}",
    )

    image_base64 = result.data[0].b64_json
    img_bytes = base64.b64decode(image_base64)

    # Send generated image
    await message.channel.send(file=discord.File(fp=img_bytes, filename="generated.png"))



# ================================================================
# PROCESS SALES CALL AUDIO
# ================================================================
async def process_audio(message, attachment, ai_thread_id):
    await message.channel.send("🎧 Received audio. Transcribing your call...")

    # Download audio
    audio_bytes = await attachment.read()

    # Send to Whisper
    transcription = client_openai.audio.transcriptions.create(
        model="gpt-4o-transcribe",
        file=("call.wav", audio_bytes)
    )

    transcript_text = transcription.text

    await message.channel.send("📝 Transcription complete. Analyzing now...")

    # SALES + RED FLAG prompt
    analysis_prompt = f"""
You are a Christian sales, setting, and marketing coach for agency owners.

Analyze the following call transcript.

=== REQUIRED OUTPUT ===
1. PERFORMANCE SCORE (0–100)
2. WHAT THEY DID WELL
3. MISTAKES
4. MISSED OPPORTUNITIES
5. TACTICAL IMPROVEMENTS
6. RED FLAG DETECTOR:
   - Sales Skill Red Flags
   - Prospect Red Flags
   - Framework Red Flags
   - Biblical Alignment Red Flags
7. ACTION PLAN
8. OBJECTION HANDLING SCORE
9. SCRIPT ACCURACY SCORE

CALL TRANSCRIPT:
{transcript_text}
"""

    # Add message to assistant thread
    client_openai.beta.threads.messages.create(
        thread_id=ai_thread_id,
        role="user",
        content=analysis_prompt
    )

    # Run assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=ai_thread_id,
        assistant_id=ASSISTANT_ID
    )

    # Get response
    msgs = client_openai.beta.threads.messages.list(thread_id=ai_thread_id)
    latest = msgs.data[0].content[0].text.value

    await message.channel.send(latest)


# ================================================================
# RUN BOT
# ================================================================
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
