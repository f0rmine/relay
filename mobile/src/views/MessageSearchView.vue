<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start"><ion-back-button default-href="/conversations" text="" /></ion-buttons>
        <ion-title>{{ t('messageSearch.title') }}</ion-title>
      </ion-toolbar>
      <ion-toolbar>
        <ion-searchbar v-model="query" :debounce="400" :placeholder="t('messageSearch.placeholder')" @ionInput="runSearch" />
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <LoadingState v-if="searching" />
      <ErrorState v-else-if="error" :message="error" />
      <template v-else-if="results.length">
        <ion-list>
          <ion-item v-for="entry in results" :key="entry.message.id" button detail @click="open(entry)">
            <ion-label>
              <h3>{{ conversationTitle(entry.conversation_id) }}</h3>
              <p>{{ entry.message.text }}</p>
              <p class="date">{{ new Date(entry.message.created_at).toLocaleString() }}</p>
            </ion-label>
          </ion-item>
        </ion-list>
      </template>
      <EmptyState
        v-else-if="query.trim().length >= 2"
        :title="t('messageSearch.emptyTitle')"
        :text="t('messageSearch.emptyText')"
      />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  IonBackButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonItem,
  IonLabel,
  IonList,
  IonPage,
  IonSearchbar,
  IonTitle,
  IonToolbar
} from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { Message } from '@/api/types';
import EmptyState from '@/components/EmptyState.vue';
import ErrorState from '@/components/ErrorState.vue';
import LoadingState from '@/components/LoadingState.vue';
import { useAuthStore } from '@/stores/auth';
import { useConversationsStore } from '@/stores/conversations';

interface SearchEntry {
  conversation_id: string;
  message: Message;
}

const query = ref('');
const results = ref<SearchEntry[]>([]);
const searching = ref(false);
const error = ref('');
const router = useRouter();
const auth = useAuthStore();
const conversations = useConversationsStore();
const { t } = useI18n();
let searchSequence = 0;

async function runSearch() {
  const sequence = ++searchSequence;
  const value = query.value.trim();
  error.value = '';
  if (value.length < 2) {
    results.value = [];
    return;
  }
  searching.value = true;
  try {
    const response = await apiFetch<SearchEntry[]>(
      `/search/messages?q=${encodeURIComponent(value)}`
    );
    if (sequence === searchSequence) results.value = response;
  } catch (err: unknown) {
    if (sequence === searchSequence) error.value = displayError(err, t('messageSearch.failed'));
  } finally {
    if (sequence === searchSequence) searching.value = false;
  }
}

function conversationTitle(conversationId: string): string {
  const item = conversations.items.find((entry) => entry.id === conversationId);
  if (!item) return t('common.chat');
  if (item.kind === 'group') return item.title || t('conversations.groupChat');
  const peer = item.participants.find((user) => user.id !== auth.user?.id);
  return peer?.display_name || t('common.user');
}

function open(entry: SearchEntry) {
  void router.push({ path: `/chat/${entry.conversation_id}`, query: { m: entry.message.id } });
}
</script>
