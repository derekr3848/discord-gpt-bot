export async function simulateAction(userId: string, message: string) {
  return {
    preview: true,
    userId,
    message,
    result: `Simulated response for user ${userId}`
  };
}
