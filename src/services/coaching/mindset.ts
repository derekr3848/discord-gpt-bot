import { memory } from "../../memory";
import { chatCompletion } from "../openaiClient";
import { mindsetPrompt } from "../prompts";
import { nowISO } from "../../utils/time";

export async function handleMindsetMessage(userId: string, message: string): Promise<string> {
  const profile = await memory.getProfile(userId);

  const ms =
    (await memory.getMindset(userId)) || {
      userId,
      themes: [],
      notes: "",
      lastUpdated: nowISO()
    };

  const faith = profile?.faithPreference ?? "off";

  const completion = await chatCompletion({
    system: "You are a business mindset coach (not a therapist).",
    messages: mindsetPrompt({
      message,
      profile,
      faithPreference: faith
    }),
    maxTokens: 900
  });

  // Log trend + notes
  ms.themes.push(message.slice(0, 100));
  ms.notes += `\n${nowISO()} - ${message.slice(0, 200)}`;
  ms.lastUpdated = nowISO();

  await memory.setMindset(userId, ms);

  return completion;
}

export async function generateMindsetResponse(userId: string, text: string) {
  return `🧠 Mindset Response:\n${text}`;
}
