import { CommandInteraction, GuildMember } from "discord.js";
import { env } from "../../config/env";

export function isAdmin(interaction: CommandInteraction) {
  const userId = interaction.user.id;

  if (env.ADMIN_IDS.includes(userId)) return true;

  if (interaction.inGuild() && env.ADMIN_ROLE_ID) {
    const member = interaction.member as GuildMember;
    return member.roles.cache.has(env.ADMIN_ROLE_ID);
  }

  return false;
}
