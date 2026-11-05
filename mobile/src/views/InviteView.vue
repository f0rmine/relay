<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-buttons slot="start"><ion-back-button default-href="/conversations" text="" /></ion-buttons>
        <ion-title>{{ t('invite.title') }}</ion-title>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <LoadingState v-if="loading" />
      <template v-else-if="preview">
        <div class="wrap">
          <h2>{{ preview.title || t('conversations.groupChat') }}</h2>
          <p class="muted">{{ t('invite.participants', { count: preview.participant_count }) }}</p>
          <p v-if="preview.is_member" class="muted">{{ t('invite.alreadyMember') }}</p>
        </div>
        <ErrorState v-if="error" :message="error" />
        <ion-button
          v-if="preview.is_member"
          expand="block"
          class="action"
          :disabled="joining"
          @click="openChat"
        >
          {{ t('invite.openChat') }}
        </ion-button>
        <ion-button
          v-else
          expand="block"
          class="action"
          :disabled="joining"
          @click="join"
        >
          {{ joining ? t('invite.joining') : t('invite.join') }}
        </ion-button>
      </template>
      <template v-else>
        <ErrorState :message="error || t('invite.invalid')" />
        <ion-button expand="block" fill="clear" @click="goConversations">
          {{ t('conversations.title') }}
        </ion-button>
      </template>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { IonBackButton, IonButton, IonButtons, IonContent, IonHeader, IonPage, IonTitle, IonToolbar } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { Conversation, InvitePreview } from '@/api/types';
import ErrorState from '@/components/ErrorState.vue';
import LoadingState from '@/components/LoadingState.vue';
import { useConversationsStore } from '@/stores/conversations';

const route = useRoute();
const router = useRouter();
const conversations = useConversationsStore();
const { t } = useI18n();
const token = String(route.params.token);
const preview = ref<InvitePreview | null>(null);
const loading = ref(true);
const joining = ref(false);
const error = ref('');

onMounted(loadPreview);

async function loadPreview() {
  loading.value = true;
  error.value = '';
  try {
    preview.value = await apiFetch<InvitePreview>(`/invite/${encodeURIComponent(token)}`);
  } catch (err: unknown) {
    preview.value = null;
    error.value = displayError(err, t('invite.loadFailed'));
  } finally {
    loading.value = false;
  }
}

function openChat() {
  if (preview.value) void router.replace(`/chat/${preview.value.conversation_id}`);
}

function goConversations() {
  void router.replace('/conversations');
}

async function join() {
  if (joining.value) return;
  joining.value = true;
  error.value = '';
  try {
    const joined = await apiFetch<Conversation>(`/invite/${encodeURIComponent(token)}/join`, { method: 'POST' });
    conversations.upsert(joined);
    void router.replace(`/chat/${joined.id}`);
  } catch (err: unknown) {
    error.value = displayError(err, t('invite.joinFailed'));
  } finally {
    joining.value = false;
  }
}
</script>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 32px 16px 12px;
  text-align: center;
}
.wrap h2 {
  margin: 0;
}
.muted {
  color: var(--relay-muted);
}
.action {
  margin: 16px;
}
</style>
