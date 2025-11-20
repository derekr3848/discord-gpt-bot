import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { startIntake, getIntakeState, INTAKE_QUESTIONS, updateIntakeState, finalizeIntake } from '../../../services/coaching/intake';
import { successEmbed, errorEmbed, toReplyOptions } from '../../../utils/embeds';
import { memory } from '../../../services/memory';

export const data = new SlashCommandBuilder()
  .setName('start')
  .setDescription('Begin onboarding intake and diagnosis');

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;

  const existingProfile = await memory.getProfile(userId);
  if (existingProfile) {
    await interaction.reply(
      toReplyOptions(
        successEmbed(
          'Onboarding already completed',
          'You already have a profile. Use `/plan`, `/offer`, `/marketing`, etc. If you want to re-run, use `/start` again and I will overwrite your profile.'
        )
      )
    );
    return;
  }

  const state = await startIntake(userId);
  const q = INTAKE_QUESTIONS[state.stepIndex];

  await interaction.reply({
    embeds: [
      successEmbed(
        'Onboarding started',
        `I'll DM you a series of questions to understand your business.\n\nFirst question:\n**${q.question}**\n\nReply to me in DM with your answer.`
      )
    ],
    ephemeral: true
  });

  const dm = await interaction.user.createDM();
  await dm.send(
    `Hey, I’m Ave Crux AI Coach. Let’s get you onboarded.\n\n**Q1:** ${q.question}`
  );
}

// DM message handler (in index.ts) will call this helper when user is in intake state
export async function handleIntakeAnswer(userId: string, content: string) {
  const state = await getIntakeState(userId);
  if (!state) return null;
  const idx = state.stepIndex;
  const q = INTAKE_QUESTIONS[idx];
  if (!q) return null;

  const nextState = await updateIntakeState(userId, (s) => {
    s.answers[q.key] = content.trim();
    s.stepIndex = s.stepIndex + 1;
    return s;
  });

  const nextQ = INTAKE_QUESTIONS[nextState.stepIndex];

  return { done: !nextQ, nextQuestion: nextQ };
}

export async function completeIntakeFlow(userId: string, username: string) {
  const { profile, roadmap, diagnosisText } = await finalizeIntake(userId, username);
  return { profile, roadmap, diagnosisText };
}

