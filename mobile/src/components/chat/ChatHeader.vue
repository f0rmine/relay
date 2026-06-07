<template>
  <ion-toolbar>
    <ion-buttons slot="start">
      <ion-back-button default-href="/conversations" />
    </ion-buttons>
    <div class="chat-title">
      <Avatar :name="peer?.display_name || 'User'" :url="peer?.avatar_url" :size="34" />
      <div>
        <strong>{{ peer?.display_name || 'Chat' }}</strong>
        <OnlineStatusBadge :online="peer?.is_online" :last-seen="peer?.last_seen_at" />
      </div>
    </div>
  </ion-toolbar>
</template>

<script setup lang="ts">
import { IonBackButton, IonButtons, IonToolbar } from '@ionic/vue';
import type { User } from '@/api/types';
import Avatar from '@/components/users/Avatar.vue';
import OnlineStatusBadge from '@/components/users/OnlineStatusBadge.vue';

defineProps<{ peer?: User }>();
</script>

<style scoped>
.chat-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.chat-title strong {
  display: block;
  line-height: 1.1;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
