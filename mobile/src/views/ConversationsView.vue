<template>
  <ion-page>
    <ion-header>
      <ion-toolbar>
        <ion-title>Chats</ion-title>
        <ion-buttons slot="end">
          <ion-button router-link="/search"><ion-icon :icon="searchOutline" /></ion-button>
          <ion-button router-link="/profile"><ion-icon :icon="personCircleOutline" /></ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <LoadingState v-if="conversations.loading" />
      <ConversationList v-else :items="conversations.items" @open="open" />
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { IonButton, IonButtons, IonContent, IonHeader, IonIcon, IonPage, IonTitle, IonToolbar, onIonViewWillEnter } from '@ionic/vue';
import { personCircleOutline, searchOutline } from 'ionicons/icons';
import ConversationList from '@/components/conversations/ConversationList.vue';
import LoadingState from '@/components/LoadingState.vue';
import { useConversationsStore } from '@/stores/conversations';

const conversations = useConversationsStore();
const router = useRouter();

onIonViewWillEnter(() => conversations.fetchAll());

function open(id: string) {
  router.push(`/chat/${id}`);
}
</script>
