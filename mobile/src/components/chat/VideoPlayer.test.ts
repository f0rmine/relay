// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Attachment } from '@/api/types';

const mocks = vi.hoisted(() => ({
  refreshTokens: vi.fn(),
  getAccessToken: vi.fn(async () => 'token-1'),
  reportError: vi.fn()
}));
vi.mock('@/api/client', () => ({ refreshTokens: mocks.refreshTokens }));
vi.mock('@/services/auth-storage', () => ({ getAccessToken: mocks.getAccessToken }));
vi.mock('@/services/errors', () => ({ reportError: mocks.reportError }));
vi.mock('@/config/env', () => ({ apiUrl: (path: string) => `https://api.test${path}` }));
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('@ionic/vue', () => ({
  IonButton: { name: 'IonButton', template: '<button v-bind="$attrs"><slot /></button>' },
  IonIcon: { name: 'IonIcon', template: '<i />' }
}));

import VideoPlayer from './VideoPlayer.vue';

const attachment = (overrides: Partial<Attachment> = {}): Attachment =>
  ({
    id: 'att-1',
    mime_type: 'video/mp4',
    original_filename: 'clip.mp4',
    file_size: 4,
    public_url: '',
    ...overrides
  }) as Attachment;

function streamResponse(chunks: Uint8Array[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    }
  });
  return new Response(body, { status: 200, headers: { 'content-length': '4' } });
}

describe('VideoPlayer', () => {
  beforeEach(() => {
    mocks.reportError.mockReset();
    mocks.refreshTokens.mockReset();
    URL.createObjectURL = vi.fn(() => 'blob:video');
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it('starts idle with a download button and no network traffic', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const wrapper = mount(VideoPlayer, { props: { attachment: attachment() } });
    expect(wrapper.attributes('data-state')).toBe('idle');
    expect(wrapper.find('[data-testid="video-download-button"]').exists()).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('streams the download with auth and becomes playable', async () => {
    const fetchMock = vi.fn(async () => streamResponse([new Uint8Array([1, 2]), new Uint8Array([3, 4])]));
    vi.stubGlobal('fetch', fetchMock);
    const wrapper = mount(VideoPlayer, { props: { attachment: attachment() } });
    await wrapper.find('[data-testid="video-download-button"]').trigger('click');
    await flushPromises();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://api.test/attachments/att-1/download');
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer token-1');
    expect(wrapper.attributes('data-state')).toBe('ready');
    expect(wrapper.find('[data-testid="video-element"]').attributes('src')).toBe('blob:video');
  });

  it('retries once with refreshed tokens on 401', async () => {
    mocks.refreshTokens.mockResolvedValue({ access_token: 'token-2' });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(streamResponse([new Uint8Array([1, 2, 3, 4])]));
    vi.stubGlobal('fetch', fetchMock);
    const wrapper = mount(VideoPlayer, { props: { attachment: attachment() } });
    await wrapper.find('[data-testid="video-download-button"]').trigger('click');
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const init = fetchMock.mock.calls[1][1] as RequestInit;
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer token-2');
    expect(wrapper.attributes('data-state')).toBe('ready');
  });

  it('returns to idle with an error and reports a failed download', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 500 })));
    const wrapper = mount(VideoPlayer, { props: { attachment: attachment() } });
    await wrapper.find('[data-testid="video-download-button"]').trigger('click');
    await flushPromises();
    expect(wrapper.attributes('data-state')).toBe('idle');
    expect(wrapper.text()).toContain('chat.downloadFailed');
    expect(mocks.reportError).toHaveBeenCalledWith('video.download', expect.any(Error));
  });

  it('plays local pending uploads without downloading', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const wrapper = mount(VideoPlayer, {
      props: { attachment: attachment({ id: 'local-1', public_url: 'blob:local' }) }
    });
    expect(wrapper.attributes('data-state')).toBe('ready');
    expect(wrapper.find('[data-testid="video-element"]').attributes('src')).toBe('blob:local');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
