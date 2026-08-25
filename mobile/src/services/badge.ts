import { Capacitor } from '@capacitor/core';

export async function setUnreadBadge(count: number): Promise<void> {
  if (!Capacitor.isNativePlatform() || count < 0) return;
  try {
    const { Badge } = await import('@capawesome/capacitor-badge');
    await Badge.set({ count });
  } catch {
    // badge is cosmetic; plugin may be missing on this build
  }
}

export async function clearUnreadBadge(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try {
    const { Badge } = await import('@capawesome/capacitor-badge');
    await Badge.clear();
  } catch {
    // ignore
  }
}
