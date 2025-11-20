import {
  APIEmbed,
  Colors,
  EmbedBuilder,
  InteractionReplyOptions,
  MessageCreateOptions
} from 'discord.js';
import { formatTimestamp } from './time';

export function adminEmbedBase(title: string): EmbedBuilder {
  return new EmbedBuilder()
    .setTitle(title)
    .setColor(Colors.Blurple)
    .setTimestamp(new Date());
}

export function successEmbed(
  title: string,
  description: string,
  extra?: Partial<APIEmbed>
): EmbedBuilder {
  const base = new EmbedBuilder()
    .setTitle(title)
    .setDescription(description)
    .setColor(Colors.Green)
    .setTimestamp(new Date());

  if (extra?.fields) base.setFields(extra.fields);
  if (extra?.footer) base.setFooter(extra.footer);
  return base;
}

export function errorEmbed(message: string): EmbedBuilder {
  return new EmbedBuilder()
    .setTitle('Error')
    .setDescription(message)
    .setColor(Colors.Red)
    .setTimestamp(new Date());
}

export function toReplyOptions(embed: EmbedBuilder): InteractionReplyOptions {
  return { embeds: [embed], ephemeral: true };
}

export function simpleMessage(embed: EmbedBuilder): MessageCreateOptions {
  return { embeds: [embed] };
}

export function adminAuditFooter(logId: string): { text: string } {
  return { text: `Log ID: ${logId} • ${formatTimestamp()}` };
}

