async def handle_audio_file(message: discord.Message, user_id: int):
    """Transcribe an audio file and send it to the assistant for analysis."""
    attachment = message.attachments[0]
    filename = attachment.filename.lower()

    if not filename.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
        return

    await message.channel.send("🎧 Received audio. Transcribing your call…")

    temp_path = f"/tmp/{attachment.filename}"
    await attachment.save(temp_path)

    try:
        # ---- TRANSCRIBE ----
        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )

        transcript_text = transcription.text

        # DO NOT send transcript to Discord (too long)
        await message.channel.send("📝 Transcription complete. Analyzing now…")

        # ---- ANALYSIS PROMPT ----
        analysis_prompt = (
            "You are a Christian sales, setting, and marketing coach.\n"
            "Analyze the following call transcript and provide:\n"
            "• A performance score (0–100)\n"
            "• What they did well\n"
            "• Mistakes\n"
            "• Missed opportunities\n"
            "• 5–10 tactical improvements\n\n"
            f"CALL TRANSCRIPT:\n{transcript_text}"
        )

        # ---- SEND TO AI ----
        openai_thread_id = user_threads[user_id]

        client.beta.threads.messages.create(
            thread_id=openai_thread_id,
            role="user",
            content=analysis_prompt,
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=openai_thread_id,
            assistant_id=ASSISTANT_ID,
        )

        messages = client.beta.threads.messages.list(thread_id=openai_thread_id)

        # Find latest assistant message
        ai_reply = next(
            (msg.content[0].text.value for msg in messages.data if msg.role == "assistant"),
            "⚠️ No response from AI."
        )

        # ---- DISCORD LIMIT PROTECTION ----
        for chunk in [ai_reply[i:i+1900] for i in range(0, len(ai_reply), 1900)]:
            await message.channel.send(chunk)

    except Exception as e:
        await message.channel.send(f"⚠️ Error processing audio: `{e}`")

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
