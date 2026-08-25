<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start">
          <ion-back-button default-href="/conversations" text="" />
        </ion-buttons>
        <ion-title>{{ t('groups.newTitle') }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <div class="wrap">
        <ion-input
          v-model="title"
          :label="t('groups.name')"
          label-placement="stacked"
          :placeholder="t('groups.namePlaceholder')"
        />
        <ErrorState v-if="error" :message="error" />
        <ion-button expand="block" class="action" :disabled="!canCreate || creating" @click="create">
          {{ t('groups.create') }}
        </ion-button>
      </div>
      <UserSearchList :selected-ids="selectedIds" @toggle="toggle" />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  IonBackButton,
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonPage,
  IonTitle,
  IonToolbar
} from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { Conversation, User } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import UserSearchList from '@/components/users/UserSearchList.vue';

const router = useRouter();
const { t } = useI18n();
const title = ref('');
const error = ref('');
const creating = ref(false);
const selected = ref<User[]>([]);
const selectedIds = computed(() => new Set(selected.value.map((user) => user.id)));
const canCreate = computed(() => title.value.trim().length > 0 && selected.value.length >= 2);

function toggle(user: User) {
  const index = selected.value.findIndex((entry) => entry.id === user.id);
  if (index >= 0) selected.value.splice(index, 1);
  else selected.value.push(user);
}

async function create() {
  if (!canCreate.value) return;
  creating.value = true;
  error.value = '';
  try {
    const conversation = await apiFetch<Conversation>('/conversations/group', {
      method: 'POST',
      body: JSON.stringify({
        title: title.value.trim(),
        participant_ids: selected.value.map((user) => user.id)
      })
    });
    void router.replace(`/chat/${conversation.id}`);
  } catch (err: unknown) {
    error.value = displayError(err, t('groups.createFailed'));
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.wrap {
  padding: 12px;
  display: grid;
  gap: 10px;
}
</style>
