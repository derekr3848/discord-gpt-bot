import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { memory } from '../../../services/memory';
import { chatCompletion } from '../../../services/openaiClient';
import { hiringPrompt } from '../../../services/prompts';
import { errorEmbed } from '../../../utils/embeds';

export const data = new SlashCommandBuilder()
  .setName('hiring')
  .setDescription('Hiring & training assistant')
  .addStringOption((opt) =>
    opt
      .setName('mode')
      .setDescription('What do you want?')
      .addChoices(
        { name: 'Job description', value: 'jd' },
        { name: 'Interview script', value: 'interview' },
        { name: 'SOP / onboarding', value: 'sop' }
      )
      .setRequired(true)
  )
  .addStringOption((opt) =>
    opt.setName('role').setDescription('Role (setter, closer, VA, etc.)').setRequired(true)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const profile = await memory.getProfile(userId);
  if (!profile) {
    await interaction.reply({
      embeds: [errorEmbed('No profile', 'Run `/start` first.')],
      ephemeral: true
    });
    return;
  }

  const mode = interaction.options.getString('mode', true) as 'jd' | 'interview' | 'sop';
  const role = interaction.options.getString('role', true);

  await interaction.deferReply({ ephemeral: true });

  const output = await chatCompletion(
    'You are a hiring and training assistant for an agency/coaching business.',
    hiringPrompt({ mode, role, profile }),
    { maxTokens: 1500 }
  );

  await interaction.editReply({
    content: 'Here is your hiring output:\n```markdown\n' + output.slice(0, 3900) + '\n```',
    embeds: [],
    ephemeral: true
  });
}

