export function nowISO(): string {
  return new Date().toISOString();
}

export function formatTimestampForDisplay(date = new Date()): string {
  // You’re in America/Chicago; we’ll label it CST/CDT generically
  return date.toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    hour12: false
  }) + ' CST';
}
