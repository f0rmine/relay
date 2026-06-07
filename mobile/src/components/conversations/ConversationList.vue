<template>
  <ion-list v-if="items.length">
    <ConversationItem v-for="conversation in items" :key="conversation.id" :conversation="conversation" @open="$emit('open', $event)" />
  </ion-list>
  <EmptyState v-else title="No conversations" text="Search for a user to start chatting." />
</template>

<script setup lang="ts">
import { IonList } from '@ionic/vue';
import type { Conversation } from '@/api/types';
import EmptyState from '@/components/EmptyState.vue';
import ConversationItem from './ConversationItem.vue';

defineProps<{ items: Conversation[] }>();
defineEmits<{ open: [id: string] }>();
</script>
