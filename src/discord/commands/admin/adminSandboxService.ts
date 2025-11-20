export async function simulateUserMessage(userId: string, message: string) {
  return {
    preview: true,
    userId,
    input: message,
    result: `Simulated coaching response for user ${userId}.\n\n(This is preview mode — no memory written.)`
  };
}
