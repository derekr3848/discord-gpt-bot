import OpenAI from 'openai';
import { env } from '../config/env';

export const openai = new OpenAI({
  apiKey: env.OPENAI_API_KEY
});

export async function chatCompletion(
  systemPrompt: string,
  userPrompt: string,
  options?: { maxTokens?: number }
): Promise<string> {
  const res = await openai.chat.completions.create({
    model: env.OPENAI_MODEL,
    max_completion_tokens: options?.maxTokens ?? 800,  // ← Updated
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt }
    ]
  });

  const content = res.choices[0]?.message?.content || '';
  return content.trim();
}
