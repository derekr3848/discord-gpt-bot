import { GuildMember, Interaction } from 'discord.js';
import { env } from '../../config/env';

export function isAdminInteraction(interaction: Interaction): boolean {
  const userId = interaction.user?.id;
  if (!userId) return false;

  if (env.ADMIN_IDS.includes(userId)) return true;

  const member = interaction.member as GuildMember | null;
  if (!member) return false;

  if (env.ADMIN_ROLE_ID && member.roles.cache.has(env.ADMIN_ROLE_ID)) {
    return true;
  }

  return false;
}

