export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR'
}

function log(level: LogLevel, message: string, meta?: unknown) {
  const ts = new Date().toISOString();
  const base = `[${ts}] [${level}] ${message}`;
  if (meta) {
    // eslint-disable-next-line no-console
    console.log(base, JSON.stringify(meta, null, 2));
  } else {
    // eslint-disable-next-line no-console
    console.log(base);
  }
}

export const logger = {
  debug: (msg: string, meta?: unknown) => log(LogLevel.DEBUG, msg, meta),
  info: (msg: string, meta?: unknown) => log(LogLevel.INFO, msg, meta),
  warn: (msg: string, meta?: unknown) => log(LogLevel.WARN, msg, meta),
  error: (msg: string, meta?: unknown) => log(LogLevel.ERROR, msg, meta)
};
