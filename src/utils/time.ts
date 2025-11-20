import { env } from '../config/env';

export function nowISO(): string {
  return new Date().toISOString();
}

export function formatTimestamp(date: Date = new Date()): string {
  // simple UTC string; you can adjust to env.TIMEZONE using a tz lib if you want
  return date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
}

