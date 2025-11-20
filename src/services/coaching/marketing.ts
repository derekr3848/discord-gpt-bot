import { memory } from '../memory';
import { chatCompletion } from '../openaiClient';
import { marketingAssetsPrompt } from '../prompts';

export async function generateMarketingAssets(userId: string, kind: string, extra?: string) {
  const [profile, roadmap, offer] = await Promise.all([
    memory.getProfile(userId),
    memory.getRoadmap(userId),
    memory.getOffer(userId)
  ]);

  const content = await chatCompletion(
    'You are generating marketing assets for an agency/coaching business.',
    marketingAssetsPrompt({
      kind,
      profile,
      roadmap,
      offer,
      extraInstructions: extra
    }),
    { maxTokens: 1400 }
  );

  // Optionally store favorite outputs later
  return content;
}

