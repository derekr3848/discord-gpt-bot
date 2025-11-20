import { redis } from "../../memory/redisClient";

export async function resetUserMemory(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  if (keys.length > 0) await redis.del(keys);
  return true;
}

export async function runMarketing(userId: string) {
  return `Generated marketing for user ${userId} (stub).`;
}

export async function runSalesReview(userId: string) {
  return `Ran sales review for ${userId} (stub).`;
}

export async function rebuildOffer(userId: string) {
  return `Rebuilt offer for ${userId} (stub).`;
}

export async function generateWeeklyPlan(userId: string) {
  return `Generated weekly plan for ${userId} (stub).`;
}
