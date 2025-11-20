import { memory } from '../../memory/memory';

export async function generateHiringDocs(userId: string, role: string) {
  return `Generated hiring docs for role: ${role} (User: ${userId})`;
}
