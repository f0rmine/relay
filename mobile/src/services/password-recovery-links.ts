import { resetTokenFromDeepLink } from '@/utils/password-recovery';

interface DeepLinkApp {
  addListener(
    eventName: 'appUrlOpen',
    listener: (event: { url: string }) => void
  ): Promise<unknown>;
  getLaunchUrl(): Promise<{ url: string } | undefined>;
}

interface DeepLinkRouter {
  isReady(): Promise<void>;
  replace(location: { path: string; query: { token: string } }): unknown;
}

export function registerPasswordRecoveryLinks(app: DeepLinkApp, router: DeepLinkRouter) {
  let lastHandledToken: string | null = null;

  function open(url: string | undefined) {
    if (!url) return;
    const token = resetTokenFromDeepLink(url);
    if (!token || token === lastHandledToken) return;
    lastHandledToken = token;
    void router.isReady()
      .then(() => router.replace({
        path: '/reset-password',
        query: { token }
      }))
      .catch(() => {
        if (lastHandledToken === token) lastHandledToken = null;
      });
  }

  void app.addListener('appUrlOpen', ({ url }) => open(url));
  void app.getLaunchUrl()
    .then((launch) => open(launch?.url))
    .catch(() => undefined);
}
