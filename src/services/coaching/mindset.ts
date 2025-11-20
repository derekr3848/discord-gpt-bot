import { memory } from '../memory';
import { chatCompletion } from '../openaiClient';
import { mindsetPrompt } from '../prompts';
import { MindsetState } from '../../utils/types';
import { nowISO } from '../../utils/time';

export async function handleMindsetMessage(userId: string, message: string): Promise<string> {
  const profile = await memory.getProfile(userId);
  const ms = (await memory.getMindset(userId)) || {
    userId,
    themes: [],
    notes: '',
    lastUpdated: nowISO()
  };

  const faith = profile?.faithPreference ?? 'off';

  const result = await chatCompletion(
    'You are a business mindset coach (not a therapist).',
    mindsetPrompt({
      message,
      profile,
      faithPreference: faith
    }),
    { maxTokens: 900 }
  );

  // simple theme detection: just append message snippet
  ms.themes.push(message.slice(0, 100));
  ms.notes = (ms.notes || '') + '\n' + nowISO() + ' - ' + message.slice(0, 200);
  ms.lastUpdated = nowISO();
  await memory.setMindset(userId, ms);

  return result;
}

