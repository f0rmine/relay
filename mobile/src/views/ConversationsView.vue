<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ t('conversations.title') }}</ion-title>
        <ion-buttons slot="end">
          <ion-button router-link="/search" :aria-label="t('conversations.search')"><ion-icon :icon="searchOutline" /></ion-button>
          <ion-button router-link="/profile" :aria-label="t('conversations.profile')"><ion-icon :icon="personCircleOutline" /></ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <LoadingState v-if="conversations.loading" />
      <ErrorState v-else-if="error" :message="error" />
      <ConversationList v-else :items="conversations.items" @open="open" />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { IonButton, IonButtons, IonContent, IonHeader, IonIcon, IonPage, IonTitle, IonToolbar, onIonViewWillEnter } from '@ionic/vue';
import { personCircleOutline, searchOutline } from 'ionicons/icons';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { displayError } from '@/api/client';
import ConversationList from '@/components/conversations/ConversationList.vue';
import ErrorState from '@/components/ErrorState.vue';
import LoadingState from '@/components/LoadingState.vue';
import { useConversationsStore } from '@/stores/conversations';

const conversations = useConversationsStore();
const router = useRouter();
const error = ref('');
const { t } = useI18n();

onIonViewWillEnter(loadConversations);

async function loadConversations() {
  error.value = '';
  try {
    await conversations.fetchAll();
  } catch (err: unknown) {
    error.value = displayError(err, t('conversations.loadFailed'));
  }
}

function open(id: string) {
  router.push(`/chat/${id}`);
}
</script>
