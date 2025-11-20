import { redis } from "../../memory/redisClient";

export async function getUserMemory(userId: string, key: string) {
  return await redis.json.get(`user:${userId}:${key}`);
}

export async function setUserMemoryKey(userId: string, key: string, value: any) {
  return redis.json.set(`user:${userId}:${key}`, "$", value);
}

export async function deleteUserMemoryKey(userId: string, key: string) {
  return redis.del(`user:${userId}:${key}`);
}
