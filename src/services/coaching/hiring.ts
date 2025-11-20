export async function generateJobDescription(userId: string, role: string) {
  return `**Job Description for ${role}**\n- Responsibilities...\n- Requirements...\n- KPIs...\n(Generated for user ${userId})`;
}

export async function generateInterviewQuestions(userId: string, role: string) {
  return `**Interview Questions for ${role}**\n1. What makes you qualified?\n2. Tell me about past results.\n3. KPIs?\n(Generated for user ${userId})`;
}

export async function generateSOP(userId: string, role: string) {
  return `**SOP for ${role}**\nStep 1: Do the task\nStep 2: Measure KPIs\nStep 3: Report to manager\n(Generated for user ${userId})`;
}
