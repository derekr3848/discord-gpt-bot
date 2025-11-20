import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { handleMindsetMessage } from '../../../services/coaching/mindset';
import { memory } from "../../../memory";
import { errorEmbed } from '../../../utils/embeds';

export const data = new SlashCommandBuilder()
  .setName('mindset')
  .setDescription('Mindset & identity-level support')
  .addStringOption((opt) =>
    opt.setName('issue').setDescription('What are you struggling with?').setRequired(true)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const profile = await memory.getProfile(userId);
  if (!profile) {
    await interaction.reply({ content: "Processing...", ephemeral: true });

    return;
  }

  const issue = interaction.options.getString('issue', true);
  await interaction.deferReply({ ephemeral: true });

  const result = await handleMindsetMessage(userId, issue);
  const response = await generateMindsetResponse(userId, text);

  await interaction.editReply({ content: mindset });

}

