<template>
  <form @submit.prevent="submit">
    <ion-item>
      <ion-input v-model="login" :label="t('auth.login.loginLabel')" label-placement="stacked" autocomplete="username" required />
    </ion-item>
    <ion-item>
      <ion-input v-model="password" :label="t('common.password')" label-placement="stacked" type="password" autocomplete="current-password" required />
    </ion-item>
    <ion-button class="submit" expand="block" type="submit" :disabled="loading">{{ t('auth.login.action') }}</ion-button>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { IonButton, IonInput, IonItem } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

defineProps<{ loading?: boolean }>();
const emit = defineEmits<{ submit: [login: string, password: string] }>();
const login = ref('');
const password = ref('');
const { t } = useI18n();

function submit() {
  emit('submit', login.value, password.value);
}
</script>

<style scoped>
.submit {
  margin-top: 18px;
}
</style>
