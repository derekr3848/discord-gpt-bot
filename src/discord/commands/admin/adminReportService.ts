import { redis } from "../../memory/redisClient";

export async function getEngagementReport() {
  const keys = await redis.keys("user:*:habits");
  return `Found ${keys.length} users with habit data.`;
}

export async function getStageReport() {
  return "Stage report not implemented yet.";
}

export async function getStuckUsersReport() {
  return "Stuck user report not implemented yet.";
}
