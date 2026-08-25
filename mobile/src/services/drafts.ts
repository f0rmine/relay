const KEY_PREFIX = 'relay:draft:';

export function saveDraft(conversationId: string, text: string): void {
  try {
    if (text) window.localStorage.setItem(KEY_PREFIX + conversationId, text);
    else window.localStorage.removeItem(KEY_PREFIX + conversationId);
  } catch {
    // storage may be unavailable; drafts are best-effort
  }
}

export function loadDraft(conversationId: string): string {
  try {
    return window.localStorage.getItem(KEY_PREFIX + conversationId) || '';
  } catch {
    return '';
  }
}

export function clearDraft(conversationId: string): void {
  try {
    window.localStorage.removeItem(KEY_PREFIX + conversationId);
  } catch {
    // ignore
  }
}
