import os
import json
from pathlib import Path
from datetime import datetime

import discord
from discord.ext import commands
from openai import OpenAI

# ========== CONFIG ==========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Your personal OpenAI Assistant ID
ASSISTANT_ID = "asst_Fc3yRPdXjHUBlXNswxQ4q1TM"

client_openai = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== MEMORY FILE ==========
MEMORY_FILE = "memory.json"

# Load user → thread_id mapping
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as f:
        user_ai_threads = json.load(f)
else:
    user_ai_threads = {}

def save_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(user_ai_threads, f)

# ========== BOT READY ==========
@bot.event
async def on_ready():
    print(f"✅ Bot ready — logged in as {bot.user}")
    print(f"Loaded {len(user_ai_threads)} user memory threads")

# ========== !START COMMAND ==========
@bot.command()
async def start(ctx: commands.Context):
    """Creates a personal AI thread for the user."""
    user = ctx.author
    user_id = str(user.id)

    # Create Discord private thread
    discord_thread = await ctx.channel.create_thread(
        name=f"{user.name}'s AI Assistant",
        type=discord.ChannelType.private_thread,
    )

    # Create OpenAI memory thread for this user (if not exists)
    if user_id not in user_ai_threads:
        ai_thread = client_openai.beta.threads.create()
        user_ai_threads[user_id] = ai_thread.id
        save_memory()
        await discord_thread.send(
            "🧠 Your personal AI memory has been created!\n"
            "Just talk normally — I will reply automatically."
        )
    else:
        await discord_thread.send(
            "🔁 You already have an AI memory — continuing where we left off!"
        )

# ========== AI REPLY FUNCTION ==========
async def reply_with_ai(message: discord.Message, text: str, user_id: str):
    """Send user text to their AI memory and reply."""
    thread_id = user_ai_threads[user_id]

    # Add message to OpenAI thread
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=text,
    )

    # Run assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    # Get response
    messages_list = client_openai.beta.threads.messages.list(thread_id=thread_id)

    for msg in messages_list.data:
        if msg.role == "assistant":
            reply = msg.content[0].text.value
            await message.channel.send(reply)
            return

    await message.channel.send("⚠️ AI did not return a response.")

# ========== AUTOMATIC THREAD HANDLING ==========
@bot.event
async def on_message(message: discord.Message):
    # make commands still work (!start)
    await bot.process_commands(message)

    # ignore bot itself
    if message.author == bot.user:
        return

    # Only respond inside private threads
    if not isinstance(message.channel, discord.Thread):
        return

    user_id = str(message.author.id)

    # User must have used !start at least once
    if user_id not in user_ai_threads:
        return

    # Ignore empty messages
    if not message.content:
        return

    # Send message to AI
    await reply_with_ai(message, message.content, user_id)


# ========== RUN BOT ==========
if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
