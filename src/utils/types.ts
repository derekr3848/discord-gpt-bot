export type FaithPreference = 'off' | 'light' | 'strong';

export interface UserProfile {
  userId: string;
  username?: string;
  timezone?: string;
  businessName?: string;
  niche?: string;
  currentRevenue?: string;
  primaryGoals?: string;
  leadSources?: string;
  salesProcess?: string;
  teamSize?: string;
  techStack?: string;
  bottlenecks?: string[];
  faithPreference: FaithPreference;
  tonePreference?: 'soft' | 'direct' | 'tough-love';
  communicationStyle?: 'short' | 'detailed';
  createdAt: string;
  updatedAt: string;
}

export interface RoadmapStage {
  id: string;
  name: string;
  description: string;
  objectives: string[];
  tasks: string[];
  habits: string[];
  kpis: string[];
  status: 'locked' | 'active' | 'completed';
}

export interface UserRoadmap {
  userId: string;
  currentStageId: string;
  stages: RoadmapStage[];
  lastUpdated: string;
}

export interface Habit {
  id: string;
  description: string;
  frequency: 'daily' | 'weekly' | 'custom';
  customCron?: string;
  createdAt: string;
  updatedAt: string;
}

export interface UserHabits {
  userId: string;
  habits: Habit[];
}

export interface PushModeState {
  enabled: boolean;
  level: 'normal' | 'strong' | 'extreme';
  lastUpdated: string;
}

export interface MindsetState {
  userId: string;
  themes: string[];
  notes: string;
  lastUpdated: string;
}

export interface OfferModel {
  userId: string;
  offerName: string;
  avatar: string;
  problem: string;
  promise: string;
  pricePoint: string;
  uniqueMechanism: string;
  programStructure: string;
  guarantees: string;
  backendSystems: string;
  lastUpdated: string;
}

export interface AdminLogRecord {
  id: string;
  actorId: string;
  targetUserId?: string;
  action: string;
  diff?: any;
  timestamp: string;
}

