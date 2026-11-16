// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  replace: vi.fn(),
  upsert: vi.fn(),
  token: 'tok/en'
}));
vi.mock('@/api/client', () => ({
  apiFetch: mocks.apiFetch,
  displayError: (_err: unknown, fallback: string) => fallback
}));
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { token: mocks.token } }),
  useRouter: () => ({ replace: mocks.replace })
}));
vi.mock('@/stores/conversations', () => ({ useConversationsStore: () => ({ upsert: mocks.upsert }) }));
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock('@ionic/vue', () => {
  const pass = (name: string) => ({ name, template: '<div><slot /></div>' });
  return {
    IonBackButton: pass('IonBackButton'),
    IonButtons: pass('IonButtons'),
    IonContent: pass('IonContent'),
    IonHeader: pass('IonHeader'),
    IonPage: pass('IonPage'),
    IonTitle: pass('IonTitle'),
    IonToolbar: pass('IonToolbar'),
    IonButton: {
      name: 'IonButton',
      props: ['disabled'],
      emits: ['click'],
      template: '<button class="ion-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
    }
  };
});
vi.mock('@/components/ErrorState.vue', () => ({
  default: { name: 'ErrorState', props: ['message'], template: '<p class="error">{{ message }}</p>' }
}));
vi.mock('@/components/LoadingState.vue', () => ({ default: { name: 'LoadingState', template: '<p class="loading" />' } }));

import InviteView from './InviteView.vue';

const preview = (overrides = {}) => ({
  conversation_id: 'conv-1',
  title: 'Team',
  participant_count: 3,
  is_member: false,
  ...overrides
});

describe('InviteView', () => {
  beforeEach(() => {
    mocks.apiFetch.mockReset();
    mocks.replace.mockReset();
    mocks.upsert.mockReset();
  });

  it('loads the preview with an encoded token', async () => {
    mocks.apiFetch.mockResolvedValueOnce(preview());
    const wrapper = mount(InviteView);
    await flushPromises();
    expect(mocks.apiFetch).toHaveBeenCalledWith('/invite/tok%2Fen');
    expect(wrapper.text()).toContain('Team');
    expect(wrapper.find('.ion-button').text()).toBe('invite.join');
  });

  it('joins, stores the conversation and opens it', async () => {
    mocks.apiFetch.mockResolvedValueOnce(preview()).mockResolvedValueOnce({ id: 'conv-1' });
    const wrapper = mount(InviteView);
    await flushPromises();
    await wrapper.find('.ion-button').trigger('click');
    await flushPromises();
    expect(mocks.apiFetch).toHaveBeenLastCalledWith('/invite/tok%2Fen/join', { method: 'POST' });
    expect(mocks.upsert).toHaveBeenCalledWith({ id: 'conv-1' });
    expect(mocks.replace).toHaveBeenCalledWith('/chat/conv-1');
  });

  it('opens the chat directly for existing members', async () => {
    mocks.apiFetch.mockResolvedValueOnce(preview({ is_member: true }));
    const wrapper = mount(InviteView);
    await flushPromises();
    await wrapper.find('.ion-button').trigger('click');
    expect(mocks.apiFetch).toHaveBeenCalledTimes(1);
    expect(mocks.replace).toHaveBeenCalledWith('/chat/conv-1');
  });

  it('shows an error when the join fails and stays on the page', async () => {
    mocks.apiFetch.mockResolvedValueOnce(preview()).mockRejectedValueOnce(new Error('expired'));
    const wrapper = mount(InviteView);
    await flushPromises();
    await wrapper.find('.ion-button').trigger('click');
    await flushPromises();
    expect(wrapper.find('.error').text()).toBe('invite.joinFailed');
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('shows a load error for an invalid invite', async () => {
    mocks.apiFetch.mockRejectedValueOnce(new Error('not found'));
    const wrapper = mount(InviteView);
    await flushPromises();
    expect(wrapper.text()).toContain('invite.loadFailed');
  });
});
