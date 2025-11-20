import { redis } from "../../memory/redisClient";

export async function resetUserMemory(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  for (const key of keys) {
    await redis.del(key);
  }
  return { ok: true, deleted: keys.length };
}
