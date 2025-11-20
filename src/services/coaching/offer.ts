import { memory } from '../memory';
import { chatCompletion } from '../openaiClient';
import { offerBuilderPrompt } from '../prompts';
import { OfferModel } from '../../utils/types';
import { nowISO } from '../../utils/time';

export interface OfferWizardState {
  stepIndex: number;
  answers: Record<string, string>;
}

const OFFER_QUESTIONS = [
  { key: 'avatar', question: 'Who is your target avatar? (be specific)' },
  { key: 'problem', question: 'What painful problem do you solve for them?' },
  { key: 'promise', question: 'What outcome or transformation do you promise?' },
  { key: 'pricePoint', question: 'What is your current or ideal price point?' },
  { key: 'proof', question: 'What proof or case studies do you have (or can we create)?' }
];

export async function startOfferWizard(userId: string): Promise<OfferWizardState> {
  const state: OfferWizardState = { stepIndex: 0, answers: {} };
  await memory.setRaw(`user:${userId}:offer_state`, JSON.stringify(state));
  return state;
}

export async function getOfferWizardState(userId: string): Promise<OfferWizardState | null> {
  const raw = await memory.getRaw(`user:${userId}:offer_state`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as OfferWizardState;
  } catch {
    return null;
  }
}

export async function updateOfferWizardState(
  userId: string,
  updater: (state: OfferWizardState) => OfferWizardState
): Promise<OfferWizardState> {
  const current = (await getOfferWizardState(userId)) || { stepIndex: 0, answers: {} };
  const next = updater(current);
  await memory.setRaw(`user:${userId}:offer_state`, JSON.stringify(next));
  return next;
}

export async function clearOfferWizardState(userId: string) {
  await memory.del(`user:${userId}:offer_state`);
}

export function getCurrentOfferQuestion(
  state: OfferWizardState
): { key: string; question: string } | null {
  return OFFER_QUESTIONS[state.stepIndex] || null;
}

export async function finalizeOffer(userId: string): Promise<{ offer: OfferModel; raw: string }> {
  const state = await getOfferWizardState(userId);
  if (!state) throw new Error('no offer state');

  const response = await chatCompletion(
    'You are building a powerful offer for an agency/coaching business.',
    offerBuilderPrompt(state.answers),
    { maxTokens: 1600 }
  );

  const match = response.match(/\[OFFER_JSON\]\s*([\s\S]+)/);
  const jsonText = match ? match[1].trim() : '{}';
  const parsed = JSON.parse(jsonText);

  const now = nowISO();
  const offer: OfferModel = {
    userId,
    offerName: parsed.offerName,
    avatar: parsed.avatar,
    problem: parsed.problem,
    promise: parsed.promise,
    pricePoint: parsed.pricePoint,
    uniqueMechanism: parsed.uniqueMechanism,
    programStructure: parsed.programStructure,
    guarantees: parsed.guarantees,
    backendSystems: parsed.backendSystems,
    lastUpdated: now
  };

  await memory.setOffer(userId, offer);
  await clearOfferWizardState(userId);
  return { offer, raw: response };
}

