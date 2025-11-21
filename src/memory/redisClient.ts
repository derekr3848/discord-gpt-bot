import { createClient } from "redis";
import { env } from "../config/env";

export const redis = createClient({
  url: env.REDIS_URL,
  password: env.REDIS_PASSWORD
});

redis.on("error", (err) => {
  console.error("[REDIS ERROR]", err);
});

export async function connectRedis() {
  if (!redis.isOpen) {
    await redis.connect();
    console.log("🔌 Redis Connected");
  }
}

// Automatically connect on import
connectRedis();
