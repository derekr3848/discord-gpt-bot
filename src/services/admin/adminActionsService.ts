import { redis } from "../../memory/redisClient";

export async function resetUserMemory(userId: string) {
  const keys = await redis.keys(`user:${userId}:*`);
  for (const key of keys) {
    await redis.del(key);
  }
  return { ok: true, deleted: keys.length };
}

// ---- missing stubs added 👇 ----

export async function runMarketing(userId: string) {
  return `Ran marketing for user ${userId}`;
}

export async function runSalesReview(userId: string) {
  return `Performed sales review for user ${userId}`;
}

export async function rebuildOffer(userId: string) {
  return `Rebuilt offer for user ${userId}`;
}

export async function generateWeeklyPlan(userId: string) {
  return `Generated weekly plan for ${userId}`;
}
