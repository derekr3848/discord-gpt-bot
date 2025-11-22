import { memory } from "../../memory";
import { chatCompletion } from "../openaiClient";
import { salesReviewPrompt } from "../prompts";
import { nowISO } from "../../utils/time";
import { redis } from "../../memory/redisClient";

export async function analyzeSalesCall(userId: string, transcript: string): Promise<string> {
  const [profile, offer] = await Promise.all([
    memory.getProfile(userId),
    memory.getOffer(userId)
  ]);

  const result = await chatCompletion({
    system: "You are an expert sales coach.",
    messages: salesReviewPrompt({
      transcript,
      profile,
      offer
    }),
    maxTokens: 1800
  });

  // Store summary in Redis list
  const key = `user:${userId}:sales_reviews`;
  const entry = {
    ts: nowISO(),
    transcriptSnippet: transcript.slice(0, 500),
    feedback: result
  };

  // ioredis commands are lowercase
  await redis.lpush(key, JSON.stringify(entry));
  await redis.ltrim(key, 0, 20);

  return result;
}
