import { redis } from "../../../memory/redisClient";

export async function getEngagementReport() {
  const keys = await redis.keys("user:*:habits");
  return `Users with habit data: ${keys.length}`;
}

export async function getStuckUsersReport() {
  return "Stub: stuck users not yet implemented.";
}
