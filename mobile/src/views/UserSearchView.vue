<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start"><ion-back-button default-href="/conversations" /></ion-buttons>
        <ion-title>Search users</ion-title>
      </ion-toolbar>
      <ion-toolbar>
        <ion-searchbar v-model="query" :debounce="300" placeholder="Username, display name, email" @ionInput="search" />
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <ErrorState v-if="error" :message="error" />
      <ion-list v-if="results.length">
        <UserSearchResult v-for="user in results" :key="user.id" :user="user" @select="startChat" />
      </ion-list>
      <EmptyState v-else title="Find people" text="Registered users appear here." />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { IonBackButton, IonButtons, IonContent, IonHeader, IonList, IonPage, IonSearchbar, IonTitle, IonToolbar } from '@ionic/vue';
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

async function search() {
  error.value = '';
  if (!query.value.trim()) {
    results.value = [];
    return;
  }
  try {
    results.value = await apiFetch<User[]>(`/users/search?q=${encodeURIComponent(query.value)}`);
  } catch (err: unknown) {
    error.value = displayError(err, 'Search failed');
  }
}

async function startChat(user: User) {
  error.value = '';
  try {
    const conversation = await conversations.start(user.id);
    router.replace(`/chat/${conversation.id}`);
  } catch (err: unknown) {
    error.value = displayError(err, 'Could not start chat');
  }
}
</script>
