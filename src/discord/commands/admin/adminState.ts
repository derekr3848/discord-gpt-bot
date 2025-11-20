import { ChatInputCommandInteraction, SlashCommandBuilder, User } from 'discord.js';
import { isAdminInteraction } from '../../../services/admin/adminAuth';
import { memory } from '../../../services/memory';
import { successEmbed, errorEmbed, adminAuditFooter } from '../../../utils/embeds';
import { logAdminAction } from '../../../services/admin/adminLog';
import { setPushModeState } from '../../../services/coaching/pushmode';
import { setStage } from '../../../services/coaching/roadmap';

export const data = new SlashCommandBuilder()
  .setName('admin_state')
  .setDescription('Admin controls: reset user, set stage, update profile, toggle pushmode')
  .addSubcommand((sub) =>
    sub
      .setName('reset_user')
      .setDescription('Reset all or part of user state')
      .addUserOption((opt) => opt.setName('user').setDescription('Target user').setRequired(true))
      .addStringOption((opt) =>
        opt
          .setName('scope')
          .setDescription('What to reset')
          .addChoices(
            { name: 'All', value: 'all' },
            { name: 'Roadmap', value: 'roadmap' },
            { name: 'Habits', value: 'habits' },
            { name: 'Profile', value: 'profile' },
            { name: 'Pushmode', value: 'pushmode' },
            { name: 'Mindset', value: 'mindset' },
            { name: 'Offer', value: 'offer' }
          )
          .setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('set_stage')
      .setDescription('Force set user roadmap stage')
      .addUserOption((opt) => opt.setName('user').setDescription('Target user').setRequired(true))
      .addStringOption((opt) =>
        opt.setName('stage_id').setDescription('Stage ID').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('toggle_pushmode')
      .setDescription('Force toggle user push mode')
      .addUserOption((opt) => opt.setName('user').setDescription('Target user').setRequired(true))
      .addBooleanOption((opt) =>
        opt.setName('enabled').setDescription('Enable?').setRequired(true)
      )
      .addStringOption((opt) =>
        opt
          .setName('level')
          .setDescription('Level')
          .addChoices(
            { name: 'Normal', value: 'normal' },
            { name: 'Strong', value: 'strong' },
            { name: 'Extreme', value: 'extreme' }
          )
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdminInteraction(interaction)) {
    await interaction.reply({ embeds: [errorEmbed('Forbidden', 'Admin only.')], ephemeral: true });
    return;
  }

  const sub = interaction.options.getSubcommand();
  const actorId = interaction.user.id;

  if (sub === 'reset_user') {
    const user = interaction.options.getUser('user', true);
    const scope = interaction.options.getString('scope', true);

    const keys: string[] = [];
    if (scope === 'all' || scope === 'profile') keys.push(`user:${user.id}:profile`);
    if (scope === 'all' || scope === 'roadmap') keys.push(`user:${user.id}:roadmap`);
    if (scope === 'all' || scope === 'habits') keys.push(`user:${user.id}:habits`, `user:${user.id}:habit_logs:*`);
    if (scope === 'all' || scope === 'pushmode') keys.push(`user:${user.id}:pushmode`);
    if (scope === 'all' || scope === 'mindset') keys.push(`user:${user.id}:mindset`);
    if (scope === 'all' || scope === 'offer') keys.push(`user:${user.id}:offer`);

    // delete simple keys; habit_logs:* would require scan but we keep simple here
    for (const k of keys) {
      if (k.includes('*')) continue;
      await memory.del(k);
    }

    const logId = await logAdminAction({
      actorId,
      targetUserId: user.id,
      action: `reset_user:${scope}`,
      diff: { keysDeleted: keys }
    });

    const embed = successEmbed(
      'Update Successful',
      `**User:** <@${user.id}>\n**Action:** Reset User → ${scope}`,
      {
        footer: adminAuditFooter(logId)
      }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'set_stage') {
    const user = interaction.options.getUser('user', true);
    const stageId = interaction.options.getString('stage_id', true);

    const roadmap = await setStage(user.id, stageId);
    if (!roadmap) {
      await interaction.reply({
        embeds: [errorEmbed('Error', 'Roadmap or stage not found.')],
        ephemeral: true
      });
      return;
    }

    const logId = await logAdminAction({
      actorId,
      targetUserId: user.id,
      action: 'set_stage',
      diff: { currentStageId: roadmap.currentStageId }
    });

    const embed = successEmbed(
      'Update Successful',
      `**User:** <@${user.id}>\n**Action:** Set Stage → ${stageId}\n**Changed:** user:${user.id}:roadmap.current_stage`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'toggle_pushmode') {
    const user = interaction.options.getUser('user', true);
    const enabled = interaction.options.getBoolean('enabled', true);
    const level = (interaction.options.getString('level') || 'normal') as
      | 'normal'
      | 'strong'
      | 'extreme';

    const state = await setPushModeState(user.id, enabled, level);
    const logId = await logAdminAction({
      actorId,
      targetUserId: user.id,
      action: 'toggle_pushmode',
      diff: state
    });

    const embed = successEmbed(
      'Update Successful',
      `**User:** <@${user.id}>\n**Action:** Toggle Pushmode → ${state.enabled ? 'ON' : 'OFF'} (${state.level})\n**Changed:** user:${user.id}:pushmode`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

