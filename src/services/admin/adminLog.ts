import { v4 as uuid } from 'uuid';
import { redis } from '../redisClient';
import { AdminLogRecord } from '../../utils/types';
import { nowISO } from '../../utils/time';

export async function logAdminAction(params: {
  actorId: string;
  targetUserId?: string;
  action: string;
  diff?: any;
}): Promise<string> {
  const id = 'LOG-' + uuid().split('-')[0].toUpperCase();
  const record: AdminLogRecord = {
    id,
    actorId: params.actorId,
    targetUserId: params.targetUserId,
    action: params.action,
    diff: params.diff,
    timestamp: nowISO()
  };

  const key = `admin:logs:${record.timestamp}:${id}`;
  await redis.set(key, JSON.stringify(record));
  return id;
}

