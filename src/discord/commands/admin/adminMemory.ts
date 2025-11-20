import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { isAdminInteraction } from '../../../services/admin/adminAuth';
import { memory } from '../../../services/memory';
import { successEmbed, errorEmbed, adminAuditFooter } from '../../../utils/embeds';
import { logAdminAction } from '../../../services/admin/adminLog';

export const data = new SlashCommandBuilder()
  .setName('admin_memory')
  .setDescription('Admin: CRUD access to user memory')
  .addSubcommand((sub) =>
    sub
      .setName('get')
      .setDescription('Get a specific memory key for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
      .addStringOption((opt) =>
        opt.setName('key').setDescription('Key suffix (e.g. profile)').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('set')
      .setDescription('Set a specific memory key for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
      .addStringOption((opt) =>
        opt.setName('key').setDescription('Key suffix (e.g. profile)').setRequired(true)
      )
      .addStringOption((opt) =>
        opt.setName('json').setDescription('JSON value').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('delete')
      .setDescription('Delete a specific memory key for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
      .addStringOption((opt) =>
        opt.setName('key').setDescription('Key suffix (e.g. profile)').setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName('export')
      .setDescription('Export all memory for a user')
      .addUserOption((opt) => opt.setName('user').setDescription('User').setRequired(true))
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdminInteraction(interaction)) {
    await interaction.reply({ embeds: [errorEmbed('Forbidden', 'Admin only.')], ephemeral: true });
    return;
  }

  const sub = interaction.options.getSubcommand();
  const actorId = interaction.user.id;
  const user = interaction.options.getUser('user', true);
  const userId = user.id;

  if (sub === 'get') {
    const keySuffix = interaction.options.getString('key', true);
    const key = `user:${userId}:${keySuffix}`;
    const raw = await memory.getRaw(key);
    const embed = successEmbed(
      'Memory Get',
      `**User:** <@${userId}>\n**Key:** \`${key}\`\n\n\`\`\`json\n${raw || 'null'}\n\`\`\``
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'set') {
    const keySuffix = interaction.options.getString('key', true);
    const key = `user:${userId}:${keySuffix}`;
    const json = interaction.options.getString('json', true);
    try {
      JSON.parse(json);
    } catch {
      await interaction.reply({
        embeds: [errorEmbed('Invalid JSON', 'Value must be valid JSON.')],
        ephemeral: true
      });
      return;
    }
    await memory.setRaw(key, json);
    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'memory_set',
      diff: { key, json }
    });
    const embed = successEmbed(
      'Memory Set',
      `**User:** <@${userId}>\n**Key:** \`${key}\`\n**Status:** Updated`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'delete') {
    const keySuffix = interaction.options.getString('key', true);
    const key = `user:${userId}:${keySuffix}`;
    await memory.del(key);
    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'memory_delete',
      diff: { key }
    });
    const embed = successEmbed(
      'Memory Delete',
      `**User:** <@${userId}>\n**Key:** \`${key}\`\n**Status:** Deleted`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else if (sub === 'export') {
    const keys = [
      'profile',
      'roadmap',
      'habits',
      'pushmode',
      'mindset',
      'offer',
      'history'
    ];
    const result: Record<string, any> = {};
    for (const suffix of keys) {
      const key = `user:${userId}:${suffix}`;
      const raw = await memory.getRaw(key);
      if (!raw) continue;
      try {
        result[suffix] = JSON.parse(raw);
      } catch {
        result[suffix] = raw;
      }
    }
    const logId = await logAdminAction({
      actorId,
      targetUserId: userId,
      action: 'memory_export',
      diff: { keys: Object.keys(result) }
    });

    const embed = successEmbed(
      'Memory Export',
      `**User:** <@${userId}>\n\n\`\`\`json\n${JSON.stringify(result, null, 2).slice(
        0,
        3900
      )}\n\`\`\``,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }
}

