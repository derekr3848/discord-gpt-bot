import { redis } from "../../memory/redisClient";

export async function getUserMemory(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  const data: Record<string, any> = {};

  for (const key of keys) {
    data[key] = await redis.get(key);
  }

  return data;
}

export async function setUserMemory(userId: string, key: string, value: any) {
  return redis.set(`user:${userId}:${key}`, JSON.stringify(value));
}

export async function deleteUserMemory(userId: string, key: string) {
  return redis.del(`user:${userId}:${key}`);
}
