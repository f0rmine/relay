export function activeConversationId(): string | undefined {
  const match = window.location.pathname.match(/^\/chat\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

export function openConversation(conversationId: string): void {
  window.dispatchEvent(
    new CustomEvent('relay:open-conversation', { detail: { conversationId } })
  );
}
