import Redis from "ioredis";
import { env } from "../config/env";

// Initialize Redis client
export const redis = new Redis(env.REDIS_URL);

// Handle connection errors
redis.on("error", (err) => {
  console.error("[REDIS ERROR]", err);
});

// Optional: Log successful connection
redis.on("connect", () => {
  console.log("🔌 Redis Connected (ioredis)");
});

