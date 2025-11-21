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
    return redis.json.get(`user:${userId}:profile`);
  },

  async setProfile(userId: string, profile: any) {
    return redis.json.set(`user:${userId}:profile`, "$", profile);
  },

  // ==========================
  // ROADMAP
  // ==========================
  async getRoadmap(userId: string) {
    return redis.json.get(`user:${userId}:roadmap`);
  },

  async setRoadmap(userId: string, roadmap: any) {
    return redis.json.set(`user:${userId}:roadmap`, "$", roadmap);
  },

  // ==========================
  // HABITS
  // ==========================
  async getHabits(userId: string) {
    return redis.json.get(`user:${userId}:habits`);
  },

  async setHabits(userId: string, habits: any) {
    return redis.json.set(`user:${userId}:habits`, "$", habits);
  },

  async logHabitCompletion(userId: string, habitId: string, date: string) {
    return redis.sAdd(`user:${userId}:habit_logs:${habitId}`, date);
  }
};
