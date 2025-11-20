import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { analyzeSalesCall } from '../../../services/coaching/sales';
import { memory } from "../../../memory";
import { errorEmbed } from '../../../utils/embeds';

export const data = new SlashCommandBuilder()
  .setName('sales_review')
  .setDescription('Analyze a sales call transcript')
  .addStringOption((opt) =>
    opt
      .setName('transcript')
      .setDescription('Paste your call transcript or bullet summary')
      .setRequired(true)
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

  const transcript = interaction.options.getString('transcript', true);
  await interaction.deferReply({ ephemeral: true });

  const result = await analyzeSalesCall(userId, transcript);

  await interaction.editReply({
    content: 'Here is your sales call analysis:',
    embeds: [],
    ephemeral: true
  });

  // send in DM too (for length)
  const dm = await interaction.user.createDM();
  await dm.send('**Sales Call Analysis**\n\n' + result.slice(0, 6000));
}

