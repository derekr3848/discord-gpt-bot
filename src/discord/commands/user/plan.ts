import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { memory } from '../../../services/memory';
import { successEmbed, errorEmbed, toReplyOptions } from '../../../utils/embeds';
import { setStage } from '../../../services/coaching/roadmap';

export const data = new SlashCommandBuilder()
  .setName('plan')
  .setDescription('View or update your growth roadmap')
  .addSubcommand((sub) =>
    sub.setName('view').setDescription('Show your current roadmap stage and tasks')
  )
  .addSubcommand((sub) =>
    sub
      .setName('set_stage')
      .setDescription('Manually set your current stage')
      .addStringOption((opt) =>
        opt.setName('stage_id').setDescription('Stage ID (e.g. stage-1)').setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  const sub = interaction.options.getSubcommand();
  const userId = interaction.user.id;
  const roadmap = await memory.getRoadmap(userId);

  if (!roadmap) {
    await interaction.reply(
      toReplyOptions(
        errorEmbed(
          'No roadmap yet',
          'I need to onboard you first. Run `/start` to go through intake.'
        )
      )
    );
    return;
  }

  if (sub === 'view') {
    const current = roadmap.stages.find((s) => s.id === roadmap.currentStageId);
    if (!current) {
      await interaction.reply(
        toReplyOptions(errorEmbed('Error', 'Current stage not found in roadmap.'))
      );
      return;
    }

    const embed = successEmbed(
      `Current Stage: ${current.name}`,
      current.description,
      {
        fields: [
          { name: 'Objectives', value: current.objectives.join('\n').slice(0, 1024) || 'None' },
          { name: 'Tasks', value: current.tasks.join('\n').slice(0, 1024) || 'None' },
          { name: 'Habits', value: current.habits.join('\n').slice(0, 1024) || 'None' },
          { name: 'KPIs', value: current.kpis.join('\n').slice(0, 1024) || 'None' }
        ]
      }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'set_stage') {
    const stageId = interaction.options.getString('stage_id', true);
    const updated = await setStage(userId, stageId);
    if (!updated) {
      await interaction.reply(
        toReplyOptions(errorEmbed('Stage not found', `Stage ID \`${stageId}\` not found.`))
      );
      return;
    }
    await interaction.reply(
      toReplyOptions(
        successEmbed(
          'Stage updated',
          `You are now on stage: **${updated.currentStageId}**`
        )
      )
    );
  }
}

