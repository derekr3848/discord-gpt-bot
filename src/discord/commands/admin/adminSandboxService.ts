export async function simulateUserMessage(userId: string, message: string) {
  return {
    preview: true,
    userId,
    message,
    result: `Simulated chatbot response for user ${userId}`
  };
}
