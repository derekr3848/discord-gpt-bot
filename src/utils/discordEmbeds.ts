import { APIEmbed, EmbedBuilder } from 'discord.js';
import { formatTimestampForDisplay } from './time';

export function buildAdminEmbed(opts: {
  title: string;
  description?: string;
  fields?: { name: string; value: string; inline?: boolean }[];
  logId: string;
}): APIEmbed {
  const builder = new EmbedBuilder()
    .setTitle(opts.title)
    .setDescription(opts.description ?? '')
    .setColor(0x5865f2)
    .setFooter({
      text: `Log ID: ${opts.logId} • ${formatTimestampForDisplay()}`
    });

  if (opts.fields?.length) {
    builder.addFields(opts.fields);
  }

  return builder.toJSON();
}
