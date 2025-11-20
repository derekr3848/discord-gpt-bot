import Redis from 'ioredis';
import { env } from '../config/env';
import { log } from './logger';

export const redis = new Redis(env.REDIS_URL, {
  password: env.REDIS_PASSWORD,
  maxRetriesPerRequest: 3
});

redis.on('connect', () => log.info('Connected to Redis'));
redis.on('error', (err) => log.error('Redis error', err));

