import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { isAdminInteraction } from '../../../services/admin/adminAuth';
import { memory } from '../../../services/memory';
import { redis } from '../../../services/redisClient';
import { coachingSystemPrompt } from '../../../services/prompts';
import { chatCompletion } from '../../../services/openaiClient';
import { successEmbed, errorEmbed, adminAuditFooter } from '../../../utils/embeds';
import { logAdminAction } from '../../../services/admin/adminLog';

export const data = new SlashCommandBuilder()
  .setName('admin_sandbox')
  .setDescription('Admin: sandbox & preview')
  .addSubcommand((sub) =>
    sub
      .setName('simulate')
      .setDescription('Preview what the bot would say to a user')
      .addUserOption((opt) => opt.setName('user').setDescription('Target user').setRequired(true))
      .addStringOption((opt) =>
        opt
          .setName('message')
          .setDescription('Message as if from user')
          .setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('dry_run')
      .setDescription('Dry-run an action with no memory writes')
      .addStringOption((opt) =>
        opt.setName('action').setDescription('Describe the action').setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdminInteraction(interaction)) {
    await interaction.reply({ embeds: [errorEmbed('Forbidden', 'Admin only.')], ephemeral: true });
    return;
  }

  const sub = interaction.options.getSubcommand();
  const actorId = interaction.user.id;

  if (sub === 'simulate') {
    const user = interaction.options.getUser('user', true);
    const userId = user.id;
    const message = interaction.options.getString('message', true);

    const [profile, roadmap, pushmode, offer, tone, faithMode] = await Promise.all([
      memory.getProfile(userId),
      memory.getRoadmap(userId),
      memory.getPushMode(userId),
      memory.getOffer(userId),
      redis.get('config:tone'),
      redis.get('config:faith_mode')
    ]);

    const system = coachingSystemPrompt({
      profile,
      roadmap,
      pushMode: pushmode,
      offer,
      globalTone: tone,
      globalFaithMode: (faithMode as any) || 'user'
    });

    const response = await chatCompletion(system, message, { maxTokens: 1200 });

    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'sandbox_simulate',
      diff: { message }
    });

    const embed = successEmbed(
      'Admin Preview: Simulate',
      `**User:** <@${userId}>\n**Admin Preview:**\n\n${response.slice(0, 3800)}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'dry_run') {
    const action = interaction.options.getString('action', true);
    const logId = await logAdminAction({
      actorId,
      action: 'sandbox_dry_run',
      diff: { action }
    });

    const embed = successEmbed(
      'Admin Dry Run',
      `**Admin Preview:**\nAction (no writes): ${action}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

