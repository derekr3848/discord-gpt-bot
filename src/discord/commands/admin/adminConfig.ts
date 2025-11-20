import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { isAdminInteraction } from '../../../services/admin/adminAuth';
import { redis } from '../../../services/redisClient';
import { successEmbed, errorEmbed, adminAuditFooter } from '../../../utils/embeds';
import { logAdminAction } from '../../../services/admin/adminLog';

export const data = new SlashCommandBuilder()
  .setName('admin_config')
  .setDescription('Admin: override coaching configuration')
  .addSubcommand((sub) =>
    sub
      .setName('set_tone')
      .setDescription('Set global tone style')
      .addStringOption((opt) =>
        opt.setName('style').setDescription('Tone style text').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('set_roadmap_template')
      .setDescription('Set roadmap template ID')
      .addStringOption((opt) =>
        opt.setName('template_id').setDescription('Template ID').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('set_faith_mode')
      .setDescription('Faith integration mode')
      .addStringOption((opt) =>
        opt
          .setName('mode')
          .setDescription('Mode')
          .addChoices(
            { name: 'Global', value: 'global' },
            { name: 'User', value: 'user' },
            { name: 'Off', value: 'off' }
          )
          .setRequired(true)
      )
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdminInteraction(interaction)) {
    await interaction.reply({ embeds: [errorEmbed('Forbidden', 'Admin only.')], ephemeral: true });
    return;
  }

  const sub = interaction.options.getSubcommand();
  const actorId = interaction.user.id;

  if (sub === 'set_tone') {
    const style = interaction.options.getString('style', true);
    await redis.set('config:tone', style);
    const logId = await logAdminAction({
      actorId,
      action: 'config_set_tone',
      diff: { style }
    });
    const embed = successEmbed(
      'Config Updated',
      `**Action:** Set tone\n**Value:** ${style}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'set_roadmap_template') {
    const templateId = interaction.options.getString('template_id', true);
    await redis.set('config:roadmap_template', templateId);
    const logId = await logAdminAction({
      actorId,
      action: 'config_set_roadmap_template',
      diff: { templateId }
    });
    const embed = successEmbed(
      'Config Updated',
      `**Action:** Set roadmap template\n**Template ID:** ${templateId}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'set_faith_mode') {
    const mode = interaction.options.getString('mode', true);
    await redis.set('config:faith_mode', mode);
    const logId = await logAdminAction({
      actorId,
      action: 'config_set_faith_mode',
      diff: { mode }
    });
    const embed = successEmbed(
      'Config Updated',
      `**Action:** Set faith mode\n**Mode:** ${mode}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

