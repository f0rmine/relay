<template>
  <ion-item button @click="$emit('select', user)">
    <Avatar slot="start" :name="user.display_name" :url="user.avatar_url" />
    <ion-label>
      <h2>{{ user.display_name }}</h2>
      <p>@{{ user.username }}</p>
    </ion-label>
    <OnlineStatusBadge :online="user.is_online" :last-seen="user.last_seen_at" />
  </ion-item>
</template>

<script setup lang="ts">
import { IonItem, IonLabel } from '@ionic/vue';
import type { User } from '@/api/types';
import Avatar from './Avatar.vue';
import OnlineStatusBadge from './OnlineStatusBadge.vue';

defineProps<{ user: User }>();
defineEmits<{ select: [user: User] }>();
</script>
