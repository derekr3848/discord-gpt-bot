import { memory } from '../memory';
import { chatCompletion } from '../openaiClient';
import { intakeDiagnosisPrompt, roadmapGenerationPrompt } from '../prompts';
import { UserProfile, UserRoadmap } from '../../utils/types';
import { nowISO } from '../../utils/time';

export const INTAKE_QUESTIONS: { key: string; question: string }[] = [
  { key: 'currentRevenue', question: 'What is your current monthly revenue (roughly)?' },
  { key: 'offer', question: 'Describe your main offer(s) in 1-3 sentences.' },
  { key: 'niche', question: 'Who is your target niche / ideal client?' },
  { key: 'leadSources', question: 'What are your main lead sources right now?' },
  { key: 'salesProcess', question: 'Describe your sales process (DM -> call, VSL -> call, etc.).' },
  { key: 'teamSize', question: 'What is your current team size and key roles?' },
  { key: 'techStack', question: 'What CRM/tech stack do you use (e.g. GHL)?' },
  {
    key: 'bottlenecks',
    question:
      'What do you feel are your biggest bottlenecks? (e.g. lead gen, offer, sales, fulfillment, retention, mindset, hiring)'
  },
  { key: 'goals', question: 'What is your target monthly revenue and by when?' },
  {
    key: 'faithPreference',
    question:
      'How much do you want faith / Christian language integrated? (off, light, strong)'
  }
];

export interface IntakeState {
  stepIndex: number;
  answers: Record<string, string>;
}

export async function startIntake(userId: string): Promise<IntakeState> {
  const state: IntakeState = { stepIndex: 0, answers: {} };
  await memory.setRaw(`user:${userId}:intake_state`, JSON.stringify(state));
  return state;
}

export async function getIntakeState(userId: string): Promise<IntakeState | null> {
  const raw = await memory.getRaw(`user:${userId}:intake_state`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as IntakeState;
  } catch {
    return null;
  }
}

export async function updateIntakeState(
  userId: string,
  updater: (state: IntakeState) => IntakeState
): Promise<IntakeState> {
  const current = (await getIntakeState(userId)) || { stepIndex: 0, answers: {} };
  const next = updater(current);
  await memory.setRaw(`user:${userId}:intake_state`, JSON.stringify(next));
  return next;
}

export async function clearIntakeState(userId: string): Promise<void> {
  await memory.del(`user:${userId}:intake_state`);
}

export async function finalizeIntake(userId: string, username: string): Promise<{
  profile: UserProfile;
  roadmap: UserRoadmap | null;
  diagnosisText: string;
}> {
  const state = await getIntakeState(userId);
  if (!state) {
    throw new Error('No intake state');
  }

  const answers = state.answers;

  // Build diagnosis
  const diagnosisText = await chatCompletion(
    'You are diagnosing an agency/coaching business and summarizing their situation.',
    intakeDiagnosisPrompt(answers),
    { maxTokens: 1200 }
  );

  // Extract bottleneck map JSON from the [BOTTLENECK_MAP_JSON] section
  const bottleneckJsonMatch = diagnosisText.match(/\[BOTTLENECK_MAP_JSON\]\s*([\s\S]+)/);
  const bottleneckJson = bottleneckJsonMatch ? bottleneckJsonMatch[1].trim() : '{}';

  const now = nowISO();

  const profile: UserProfile = {
    userId,
    username,
    timezone: undefined,
    businessName: username + "'s business",
    niche: answers['niche'],
    currentRevenue: answers['currentRevenue'],
    leadSources: answers['leadSources'],
    salesProcess: answers['salesProcess'],
    teamSize: answers['teamSize'],
    techStack: answers['techStack'],
    primaryGoals: answers['goals'],
    bottlenecks: answers['bottlenecks']
      ? answers['bottlenecks'].split(',').map((s) => s.trim())
      : [],
    faithPreference:
      (answers['faithPreference'] as any) === 'strong' ||
      (answers['faithPreference'] as any) === 'light'
        ? (answers['faithPreference'] as any)
        : 'off',
    tonePreference: 'direct',
    communicationStyle: 'short',
    createdAt: now,
    updatedAt: now
  };

  await memory.setProfile(userId, profile);

  // Generate roadmap from bottleneck map
  let roadmap: UserRoadmap | null = null;
  try {
    const roadmapJson = await chatCompletion(
      'You are building a JSON roadmap only.',
      roadmapGenerationPrompt({
        profile,
        bottleneckMapJson: bottleneckJson,
        goalTimeline: answers['goals'] || ''
      }),
      { maxTokens: 1600 }
    );

    const parsed = JSON.parse(roadmapJson);
    roadmap = {
      userId,
      currentStageId: parsed.currentStageId,
      stages: parsed.stages,
      lastUpdated: now
    };
    await memory.setRoadmap(userId, roadmap);
  } catch {
    roadmap = null;
  }

  await clearIntakeState(userId);

  return { profile, roadmap, diagnosisText };
}

