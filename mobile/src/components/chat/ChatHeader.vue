<template>
  <ion-toolbar>
    <ion-buttons slot="start">
      <ion-back-button default-href="/conversations" text="" />
    </ion-buttons>
    <div class="chat-title" @click="openInfo">
      <Avatar :name="title || t('common.user')" :url="avatarUrl" :size="34" />
      <div>
        <strong>{{ title }}</strong>
        <OnlineStatusBadge
          v-if="!group"
          :online="peer?.is_online"
          :last-seen="peer?.last_seen_at"
        />
        <span v-else class="members">{{ membersLabel }}</span>
      </div>
    </div>
    <ion-buttons slot="end">
      <ion-button v-if="conversation" @click="goMedia" :aria-label="t('chat.mediaGallery')">
        <ion-icon :icon="imagesOutline" />
      </ion-button>
      <ion-button v-if="conversation" @click="goInfo" :aria-label="t('groups.info')">
        <ion-icon :icon="informationCircleOutline" />
      </ion-button>
    </ion-buttons>
  </ion-toolbar>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { IonBackButton, IonButton, IonButtons, IonIcon, IonToolbar } from '@ionic/vue';
import { imagesOutline, informationCircleOutline } from 'ionicons/icons';
import type { Conversation, User } from '@/api/types';
import { useI18n } from 'vue-i18n';
import Avatar from '@/components/users/Avatar.vue';
import OnlineStatusBadge from '@/components/users/OnlineStatusBadge.vue';

const props = defineProps<{ peer?: User; conversation?: Conversation | null }>();
const router = useRouter();
const { t } = useI18n();

const group = computed(() => props.conversation?.kind === 'group');
const avatarUrl = computed(() =>
  group.value ? props.conversation?.avatar_url : props.peer?.avatar_url
);
const title = computed(() =>
  group.value ? props.conversation?.title || t('conversations.groupChat') : props.peer?.display_name || t('common.chat')
);
const membersLabel = computed(() => {
  const count = props.conversation?.participants?.length || 0;
  return `${count} ${t('groups.members')}`;
});

function goInfo() {
  if (props.conversation) void router.push(`/chat/${props.conversation.id}/info`);
}
function goMedia() {
  if (props.conversation) void router.push(`/chat/${props.conversation.id}/media`);
}
function openInfo() {
  if (props.conversation) goInfo();
}
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
.members {
  font-size: 12px;
  color: var(--relay-muted);
}
</style>
