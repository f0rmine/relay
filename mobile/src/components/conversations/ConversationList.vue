<template>
  <ion-list v-if="items.length">
    <ConversationItem v-for="conversation in items" :key="conversation.id" :conversation="conversation" @open="$emit('open', $event)" />
  </ion-list>
  <EmptyState v-else :title="t('conversations.emptyTitle')" :text="t('conversations.emptyText')" />
</template>

<script setup lang="ts">
import { IonList } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import type { Conversation } from '@/api/types';
import EmptyState from '@/components/EmptyState.vue';
import ConversationItem from './ConversationItem.vue';

defineProps<{ items: Conversation[] }>();
defineEmits<{ open: [id: string] }>();
const { t } = useI18n();
</script>
