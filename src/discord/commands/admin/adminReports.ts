import { ChatInputCommandInteraction, SlashCommandBuilder } from 'discord.js';
import { isAdminInteraction } from '../../../services/admin/adminAuth';
import { redis } from '../../../services/redisClient';
import { successEmbed, errorEmbed, adminAuditFooter } from '../../../utils/embeds';
import { logAdminAction } from '../../../services/admin/adminLog';

export const data = new SlashCommandBuilder()
  .setName('admin_report')
  .setDescription('Admin analytics & reporting')
  .addSubcommand((sub) =>
    sub.setName('engagement').setDescription('Active vs inactive users (last 7 days)')
  )
  .addSubcommand((sub) =>
    sub.setName('stages').setDescription('Stage distribution across users')
  )
  .addSubcommand((sub) =>
    sub.setName('habits').setDescription('Users with habits defined')
  )
  .addSubcommand((sub) =>
    sub.setName('stuck_users').setDescription('Users with no recent habit completions')
  );

export async function execute(interaction: ChatInputCommandInteraction) {
  if (!isAdminInteraction(interaction)) {
    await interaction.reply({ embeds: [errorEmbed('Forbidden', 'Admin only.')], ephemeral: true });
    return;
  }
  const sub = interaction.options.getSubcommand();
  const actorId = interaction.user.id;

  await interaction.deferReply({ ephemeral: true });

  // NOTE: For simplicity we use Redis SCAN and some heuristics.
  if (sub === 'engagement') {
    const historyKeys: string[] = [];
    let cursor = '0';
    do {
      const [next, keys] = await redis.scan(cursor, 'MATCH', 'user:*:history', 'COUNT', 100);
      cursor = next;
      historyKeys.push(...keys);
    } while (cursor !== '0');

    const now = Date.now();
    let active = 0;
    let inactive = 0;

    for (const key of historyKeys) {
      const len = await redis.llen(key);
      if (len === 0) continue;
      const last = await redis.lindex(key, 0);
      if (!last) continue;
      try {
        const parsed = JSON.parse(last);
        const ts = new Date(parsed.ts).getTime();
        const diffDays = (now - ts) / (1000 * 60 * 60 * 24);
        if (diffDays <= 7) active++;
        else inactive++;
      } catch {}
    }

    const logId = await logAdminAction({
      actorId,
      action: 'report_engagement',
      diff: { active, inactive }
    });

    const embed = successEmbed(
      'Engagement Report',
      `**Active users (≤7d):** ${active}\n**Inactive users (>7d):** ${inactive}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.editReply({ embeds: [embed] });
  } else if (sub === 'stages') {
    const roadmapKeys: string[] = [];
    let cursor = '0';
    do {
      const [next, keys] = await redis.scan(cursor, 'MATCH', 'user:*:roadmap', 'COUNT', 100);
      cursor = next;
      roadmapKeys.push(...keys);
    } while (cursor !== '0');

    const counts: Record<string, number> = {};
    for (const key of roadmapKeys) {
      const raw = await redis.get(key);
      if (!raw) continue;
      try {
        const parsed = JSON.parse(raw);
        const stageId = parsed.currentStageId || 'unknown';
        counts[stageId] = (counts[stageId] || 0) + 1;
      } catch {}
    }

    const fields = Object.entries(counts).map(([stage, count]) => ({
      name: stage,
      value: `${count} users`
    }));

    const logId = await logAdminAction({
      actorId,
      action: 'report_stages',
      diff: counts
    });

    const embed = successEmbed(
      'Stage Distribution',
      'Users per roadmap stage:',
      { fields, footer: adminAuditFooter(logId) }
    );
    await interaction.editReply({ embeds: [embed] });
  } else if (sub === 'habits') {
    const habitKeys: string[] = [];
    let cursor = '0';
    do {
      const [next, keys] = await redis.scan(cursor, 'MATCH', 'user:*:habits', 'COUNT', 100);
      cursor = next;
      habitKeys.push(...keys);
    } while (cursor !== '0');

    let withHabits = 0;
    let withoutHabits = 0;

    for (const key of habitKeys) {
      const raw = await redis.get(key);
      if (!raw) continue;
      try {
        const parsed = JSON.parse(raw);
        if (parsed.habits && parsed.habits.length > 0) withHabits++;
        else withoutHabits++;
      } catch {}
    }

    const logId = await logAdminAction({
      actorId,
      action: 'report_habits',
      diff: { withHabits, withoutHabits }
    });

    const embed = successEmbed(
      'Habit Report',
      `**Users with habits:** ${withHabits}\n**Users without habits:** ${withoutHabits}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.editReply({ embeds: [embed] });
  } else if (sub === 'stuck_users') {
    // Very simple heuristic: users with habits but 0 habit_logs
    const habitKeys: string[] = [];
    let cursor2 = '0';
    do {
      const [next, keys] = await redis.scan(cursor2, 'MATCH', 'user:*:habits', 'COUNT', 100);
      cursor2 = next;
      habitKeys.push(...keys);
    } while (cursor2 !== '0');

    const stuckUsers: string[] = [];
    for (const key of habitKeys) {
      const raw = await redis.get(key);
      if (!raw) continue;
      try {
        const parsed = JSON.parse(raw);
        const userId = parsed.userId;
        if (!parsed.habits || parsed.habits.length === 0) continue;
        let anyLogs = false;
        for (const h of parsed.habits) {
          const logKey = `user:${userId}:habit_logs:${h.id}`;
          const count = await redis.scard(logKey);
          if (count > 0) {
            anyLogs = true;
            break;
          }
        }
        if (!anyLogs) stuckUsers.push(userId);
      } catch {}
    }

    const logId = await logAdminAction({
      actorId,
      action: 'report_stuck_users',
      diff: { stuckUsersCount: stuckUsers.length }
    });

    const embed = successEmbed(
      'Stuck Users Report',
      `Users with habits but no completions:\n${stuckUsers.map((id) => `<@${id}>`).join('\n') || 'None'}`,
      { footer: adminAuditFooter(logId) }
    );
    await interaction.editReply({ embeds: [embed] });
  }
}

