import { EmbedBuilder } from "discord.js";

/**
 * Create a success embed
 */
export function successEmbed(
  title: string,
  description: string,
  options?: {
    fields?: { name: string; value: string; inline?: boolean }[];
  }
) {
  const embed = new EmbedBuilder()
    .setTitle(title)
    .setDescription(description)
    .setColor(0x00ff85);

  if (options?.fields) {
    embed.addFields(options.fields);
  }

  return embed;
}

/**
 * Create an error embed
 */
export function errorEmbed(title: string, description: string) {
  return new EmbedBuilder()
    .setTitle(`❌ ${title}`)
    .setDescription(description)
    .setColor(0xff2e2e);
}

/**
 * Wrap embeds into reply-friendly object formatting
 */
export function toReplyOptions(embed: any, ephemeral = true) {
  return {
    embeds: [embed],
    ephemeral
  };
}
