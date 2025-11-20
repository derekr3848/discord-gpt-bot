import { redis } from "../../memory/redisClient";

// Already exists
export async function getUserMemory(userId: string) { /* keep your version */ }

// Already exists
export async function setUserMemory(userId: string, key: string, value: any) {
  return redis.set(`user:${userId}:${key}`, JSON.stringify(value));
}

// Already exists
export async function deleteUserMemory(userId: string, key: string) {
  return redis.del(`user:${userId}:${key}`);
}

// Add aliases to satisfy old imports 👇
export const setUserMemoryKey = setUserMemory;
export const deleteUserMemoryKey = deleteUserMemory;
