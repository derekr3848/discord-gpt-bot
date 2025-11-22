import Redis from "ioredis";
import { env } from "../config/env";

export const redis = new Redis(env.REDIS_URL);  // no password config needed separately if URL contains it

redis.on("error", (err) => {
  console.error("[REDIS ERROR]", err);
});

export async function connectRedis() {
  console.log("🔌 Redis Connected");
}
