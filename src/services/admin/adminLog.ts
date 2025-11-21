import { redis } from "../../memory/redisClient";

import { v4 as uuid } from "uuid";

export async function logAdminAction(data: {
  userId: string;
  action: string;
  details?: any;
  invokedBy?: string;
}) {
  const logId: string = uuid();


  const timestamp = Date.now();

  const payload = {
    logId,
    timestamp,
    ...data
  };

  await redis.json.set(`admin:logs:${logId}`, "$", payload);

  return logId;
}
