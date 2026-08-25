<template>
  <div>
    <ion-searchbar v-model="query" :debounce="300" :placeholder="t('search.placeholder')" @ionInput="search" />
    <ion-list>
      <UserSearchResult v-for="user in results" :key="user.id" :user="user" @select="toggle" />
    </ion-list>
    <p v-if="!results.length && query.trim()" class="empty">{{ t('search.emptyText') }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { IonList, IonSearchbar } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { apiFetch, displayError } from '@/api/client';
import type { User } from '@/api/types';
import UserSearchResult from '@/components/users/UserSearchResult.vue';

const props = defineProps<{ selectedIds?: Set<string> }>();
const emit = defineEmits<{ toggle: [user: User] }>();
const query = ref('');
const results = ref<User[]>([]);
const { t } = useI18n();
let searchSequence = 0;

async function search() {
  const sequence = ++searchSequence;
  const value = query.value.trim();
  if (!value) {
    results.value = [];
    return;
  }
  try {
    const response = await apiFetch<User[]>(`/users/search?q=${encodeURIComponent(value)}`);
    if (sequence === searchSequence) results.value = response;
  } catch (err: unknown) {
    displayError(err, t('search.failed'));
    if (sequence === searchSequence) results.value = [];
  }
}

function toggle(user: User) {
  void props;
  emit('toggle', user);
}
</script>

<style scoped>
.empty {
  padding: 12px 16px;
  color: var(--relay-muted);
}
</style>
