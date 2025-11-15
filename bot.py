import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# Set up OpenAI client
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# Discord intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Store conversation threads per user
user_threads = {}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

def get_or_create_thread(user_id: int):
    if user_id in user_threads:
        return user_threads[user_id]

    thread = client_openai.beta.threads.create()
    user_threads[user_id] = thread.id
    return thread.id

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    user_id = message.author.id
    content = message.content.strip()

    # Reset context
    if content.lower() == "!reset":
        if user_id in user_threads:
            del user_threads[user_id]
        await message.channel.send("🧠 Context reset. Let's start fresh!")
        return

    # Create/get the thread for the user
    thread_id = get_or_create_thread(user_id)

    # Add user message to thread
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=content
    )

    # Run your assistant
    run = client_openai.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID
    )

    # Get assistant reply
    reply_text = ""
    messages = client_openai.beta.threads.messages.list(thread_id=thread_id)
    for m in reversed(messages.data):
        if m.role == "assistant":
            for part in m.content:
                if part.type == "text":
                    reply_text = part.text.value
            break

    if not reply_text:
        reply_text = "Hmm, I couldn’t generate a response right now. Try again?"

    # Discord character limit check
    if len(reply_text) > 2000:
        reply_text = reply_text[:1990] + "... (truncated)"

    await message.channel.send(reply_text)

    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
