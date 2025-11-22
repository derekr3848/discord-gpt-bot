import { redis } from "./redisClient";

export const memory = {
  // ==========================
  // GENERIC RAW ACCESS
  // ==========================
  async setRaw(key: string, value: string) {
    return redis.set(key, value);
  },

  async getRaw(key: string) {
    return redis.get(key);
  },

  async del(key: string) {
    return redis.del(key);
  },

  // ==========================
  // PROFILE
  // ==========================
  async getProfile(userId: string) {
    const raw = await redis.get(`user:${userId}:profile`);
    return raw ? JSON.parse(raw) : null;
  },

  async setProfile(userId: string, profile: any) {
    return redis.set(`user:${userId}:profile`, JSON.stringify(profile));
  },

  // ==========================
  // ROADMAP
  // ==========================
  async getRoadmap(userId: string) {
    const raw = await redis.get(`user:${userId}:roadmap`);
    return raw ? JSON.parse(raw) : null;
  },

  async setRoadmap(userId: string, roadmap: any) {
    return redis.set(`user:${userId}:roadmap`, JSON.stringify(roadmap));
  },

  // ==========================
  // HABITS
  // ==========================
  async getHabits(userId: string) {
    const raw = await redis.get(`user:${userId}:habits`);
    return raw ? JSON.parse(raw) : null;
  },

  async setHabits(userId: string, habits: any) {
    return redis.set(`user:${userId}:habits`, JSON.stringify(habits));
  },

  async logHabitCompletion(userId: string, habitId: string, date: string) {
    return redis.sadd(`user:${userId}:habit_logs:${habitId}`, date);
  },

  // ==========================
  // OFFER
  // ==========================
  async getOffer(userId: string) {
    const raw = await redis.get(`user:${userId}:offer`);
    return raw ? JSON.parse(raw) : null;
  },

  async setOffer(userId: string, offer: any) {
    return redis.set(`user:${userId}:offer`, JSON.stringify(offer));
  },

  // ==========================
  // MINDSET
  // ==========================
  async getMindset(userId: string) {
    const raw = await redis.get(`user:${userId}:mindset`);
    return raw ? JSON.parse(raw) : null;
  },
  
  async setMindset(userId: string, mindset: any) {
    return redis.set(`user:${userId}:mindset`, JSON.stringify(mindset));
  }
};
