import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { setPushModeState } from '../../../services/coaching/pushmode';
import { successEmbed, toReplyOptions } from '../../../utils/embeds';

export const data = new SlashCommandBuilder()
  .setName('pushmode')
  .setDescription('Toggle tough-love accountability mode')
  .addBooleanOption((opt) =>
    opt.setName('enabled').setDescription('Enable push mode?').setRequired(true)
  )
  .addStringOption((opt) =>
    opt
      .setName('level')
      .setDescription('Intensity level')
      .addChoices(
        { name: 'Normal', value: 'normal' },
        { name: 'Strong', value: 'strong' },
        { name: 'Extreme', value: 'extreme' }
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const enabled = interaction.options.getBoolean('enabled', true);
  const level = (interaction.options.getString('level') || 'normal') as
    | 'normal'
    | 'strong'
    | 'extreme';
  const userId = interaction.user.id;

  const state = await setPushModeState(userId, enabled, level);

  await interaction.reply(
    toReplyOptions(
      successEmbed(
        'Push mode updated',
        `Push mode is now **${state.enabled ? 'ON' : 'OFF'}** at level **${state.level}**.`
      )
    )
  );
}

