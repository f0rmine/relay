<template>
  <form @submit.prevent="submit">
    <ion-item>
      <ion-input v-model="displayName" :label="t('common.displayName')" label-placement="stacked" required />
    </ion-item>
    <ion-item>
      <ion-input v-model="username" :label="t('common.username')" label-placement="stacked" autocomplete="username" required />
    </ion-item>
    <ion-item>
      <ion-input v-model="email" :label="t('common.email')" label-placement="stacked" type="email" autocomplete="email" required />
    </ion-item>
    <ion-item>
      <ion-input v-model="password" :label="t('common.password')" label-placement="stacked" type="password" autocomplete="new-password" required />
    </ion-item>
    <ion-button class="submit" expand="block" type="submit" :disabled="loading">{{ t('auth.register.action') }}</ion-button>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { IonButton, IonInput, IonItem } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

defineProps<{ loading?: boolean }>();
const emit = defineEmits<{ submit: [username: string, displayName: string, email: string, password: string] }>();
const username = ref('');
const displayName = ref('');
const email = ref('');
const password = ref('');
const { t } = useI18n();

function submit() {
  emit('submit', username.value, displayName.value, email.value, password.value);
}
</script>

<style scoped>
.submit {
  margin-top: 18px;
}
</style>
