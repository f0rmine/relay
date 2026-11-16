<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-back-button :default-href="`/chat/${conversationId}/info`" text="" />
        </ion-buttons>
        <ion-title>{{ t('e2ee.safetyNumbers') }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <p class="notice" data-testid="e2ee-phase-notice">{{ t('e2ee.notYetE2ee') }}</p>
      <ErrorState v-if="error" :message="error" />
      <p v-if="e2ee.status !== 'ready'" class="muted pad">{{ statusText }}</p>
      <LoadingState v-else-if="loading" />

      <section v-for="entry in entries" :key="entry.user.id" class="contact" data-testid="safety-entry">
        <h3>{{ entry.user.display_name }}</h3>

        <p v-if="!entry.keys" class="muted">{{ t('e2ee.noKeys', { name: entry.user.display_name }) }}</p>
        <template v-else>
          <div v-if="entry.keys.pinned.changedTo" class="warning" data-testid="key-changed">
            <p>{{ t('e2ee.keyChanged', { name: entry.user.display_name }) }}</p>
            <ion-button size="small" fill="outline" @click="acceptChange(entry.user.id)">
              {{ t('e2ee.acceptChange') }}
            </ion-button>
          </div>
          <template v-else>
            <p class="muted">{{ t('e2ee.explain', { name: entry.user.display_name }) }}</p>
            <div class="digits" data-testid="safety-digits">
              <span v-for="(group, index) in entry.groups" :key="index">{{ group }}</span>
            </div>
            <p v-if="entry.keys.rejectedDevices" class="warning-text">
              {{ t('e2ee.rejectedDevices', { count: entry.keys.rejectedDevices }) }}
            </p>
            <div class="verify-row">
              <span v-if="entry.keys.pinned.verified" class="verified">✓ {{ t('e2ee.verified') }}</span>
              <ion-button
                size="small"
                :fill="entry.keys.pinned.verified ? 'clear' : 'solid'"
                @click="toggleVerified(entry.user.id, !entry.keys.pinned.verified)"
              >
                {{ entry.keys.pinned.verified ? t('e2ee.unmarkVerified') : t('e2ee.markVerified') }}
              </ion-button>
            </div>
          </template>
        </template>
      </section>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonPage,
  IonTitle,
  IonToolbar
} from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { Conversation, User } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import LoadingState from '@/components/LoadingState.vue';
import { groupDigits } from '@/crypto/safety-number';
import { useAuthStore } from '@/stores/auth';
import { useConversationsStore } from '@/stores/conversations';
import { type ContactKeys, useE2eeStore } from '@/stores/e2ee';

interface Entry {
  user: User;
  keys: ContactKeys | null;
  groups: string[];
}

const route = useRoute();
const auth = useAuthStore();
const conversations = useConversationsStore();
const e2ee = useE2eeStore();
const { t } = useI18n();
const conversationId = String(route.params.id);
const entries = ref<Entry[]>([]);
const loading = ref(false);
const error = ref('');

const statusText = computed(() => {
  switch (e2ee.status) {
    case 'needs-link':
      return t('e2ee.statusNeedsLink');
    case 'error':
      return t('e2ee.statusError');
    default:
      return t('e2ee.statusWorking');
  }
});

async function load() {
  if (e2ee.status !== 'ready') return;
  loading.value = true;
  error.value = '';
  try {
    let conversation = conversations.items.find((item) => item.id === conversationId);
    if (!conversation) {
      conversation = await apiFetch<Conversation>(`/conversations/${conversationId}`);
      conversations.applyConversationInfo(conversation);
    }
    const others = conversation.participants.filter((user) => user.id !== auth.user?.id);
    entries.value = await Promise.all(
      others.map(async (user) => {
        const keys = await e2ee.contactKeys(user.id);
        const number = keys && !keys.pinned.changedTo ? e2ee.safetyNumberWith(keys) : null;
        return { user, keys, groups: number ? groupDigits(number) : [] };
      })
    );
  } catch (err: unknown) {
    error.value = displayError(err, t('e2ee.loadFailed'));
  } finally {
    loading.value = false;
  }
}

async function toggleVerified(userId: string, verified: boolean) {
  await e2ee.setVerified(userId, verified);
  await load();
}

async function acceptChange(userId: string) {
  await e2ee.acceptKeyChange(userId);
  await load();
}

onMounted(() => {
  void e2ee.ensure().then(load);
});
watch(() => e2ee.status, (status) => {
  if (status === 'ready' && !entries.value.length) void load();
});
</script>

<style scoped>
.notice {
  margin: 12px 16px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--ion-color-light);
  font-size: 13px;
}
.pad {
  padding: 0 16px;
}
.muted {
  color: var(--relay-muted);
  font-size: 13px;
}
.contact {
  margin: 8px 16px 20px;
}
.contact h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.digits {
  display: grid;
  grid-template-columns: repeat(4, auto);
  justify-content: start;
  gap: 6px 14px;
  margin: 10px 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 17px;
  letter-spacing: 1px;
}
.verify-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.verified {
  color: var(--ion-color-success);
  font-weight: 600;
}
.warning {
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--ion-color-danger-rgb), 0.12);
}
.warning p {
  margin: 0 0 8px;
}
.warning-text {
  color: var(--ion-color-danger);
  font-size: 13px;
}
</style>
