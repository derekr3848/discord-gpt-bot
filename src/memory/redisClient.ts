import { createClient } from "redis";
import { env } from "../config/env";

export const redis = createClient({
  url: env.REDIS_URL,
  password: env.REDIS_PASSWORD
});

redis.connect();
