import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { generateMarketingAssets } from '../../../services/coaching/marketing';
import { successEmbed, errorEmbed } from '../../../utils/embeds';
import { memory } from '../../../services/memory';

export const data = new SlashCommandBuilder()
  .setName('marketing')
  .setDescription('Generate marketing assets tailored to your offer')
  .addStringOption((opt) =>
    opt
      .setName('kind')
      .setDescription('Type of assets')
      .addChoices(
        { name: 'Meta ads', value: 'ads' },
        { name: 'Short-form scripts', value: 'short-form scripts' },
        { name: 'Email sequence', value: 'email sequence' },
        { name: 'Social posts', value: 'social posts' }
      )
      .setRequired(true)
  )
  .addStringOption((opt) =>
    opt
      .setName('extra')
      .setDescription('Any extra instructions (optional)')
      .setRequired(false)
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const userId = interaction.user.id;
  const profile = await memory.getProfile(userId);
  if (!profile) {
    await interaction.reply({
      embeds: [errorEmbed('No profile', 'Run `/start` first so I understand your business.')],
      ephemeral: true
    });
    return;
  }

  const kind = interaction.options.getString('kind', true);
  const extra = interaction.options.getString('extra') || undefined;
  await interaction.deferReply({ ephemeral: true });

  const assets = await generateMarketingAssets(userId, kind, extra);
  const embed = successEmbed(
    'Marketing assets generated',
    'Here are your tailored assets:\n\n```markdown\n' +
      assets.slice(0, 3900) +
      '\n```'
  );

  await interaction.editReply({ embeds: [embed] });
}

