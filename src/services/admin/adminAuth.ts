import { CommandInteraction, GuildMember } from "discord.js";
import { env } from "../../config/env";

export function isAdmin(interaction: CommandInteraction): boolean {
  const userId = interaction.user.id;

  // 1️⃣ Check ENV whitelist (comma-separated IDs)
  if (env.ADMIN_IDS.includes(userId)) return true;

  // 2️⃣ Check admin role (must be in a guild)
  if (interaction.inGuild() && env.ADMIN_ROLE_ID) {
    const member = interaction.member as GuildMember;
    if (member?.roles?.cache?.has(env.ADMIN_ROLE_ID)) return true;
  }

  return false;
}
