<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start"><ion-back-button default-href="/conversations" text="" /></ion-buttons>
        <ion-title>{{ t('search.title') }}</ion-title>
      </ion-toolbar>
      <ion-toolbar>
        <ion-searchbar v-model="query" :debounce="300" :placeholder="t('search.placeholder')" @ionInput="search" />
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <ErrorState v-if="error" :message="error" />
      <ion-list v-if="results.length">
        <UserSearchResult v-for="user in results" :key="user.id" :user="user" @select="startChat" />
      </ion-list>
      <EmptyState v-else :title="t('search.emptyTitle')" :text="t('search.emptyText')" />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonBackButton, IonButtons, IonContent, IonHeader, IonList, IonPage, IonSearchbar, IonTitle, IonToolbar } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { User } from '@/api/types';
import EmptyState from '@/components/EmptyState.vue';
import ErrorState from '@/components/ErrorState.vue';
import UserSearchResult from '@/components/users/UserSearchResult.vue';
import { useConversationsStore } from '@/stores/conversations';

const query = ref('');
const results = ref<User[]>([]);
const error = ref('');
const router = useRouter();
const conversations = useConversationsStore();
const { t } = useI18n();
let searchSequence = 0;

async function search() {
  const sequence = ++searchSequence;
  const value = query.value.trim();
  error.value = '';
  if (!value) {
    results.value = [];
    return;
  }
  try {
    const response = await apiFetch<User[]>(`/users/search?q=${encodeURIComponent(value)}`);
    if (sequence === searchSequence) results.value = response;
  } catch (err: unknown) {
    if (sequence === searchSequence) error.value = displayError(err, t('search.failed'));
  }
}

async function startChat(user: User) {
  error.value = '';
  try {
    const conversation = await conversations.start(user.id);
    router.replace(`/chat/${conversation.id}`);
  } catch (err: unknown) {
    error.value = displayError(err, t('search.startFailed'));
  }
}
</script>

<style scoped>
ion-searchbar {
  --color: #ffffff;
}
</style>
