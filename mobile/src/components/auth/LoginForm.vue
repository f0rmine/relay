<template>
  <form @submit.prevent="submit">
    <ion-item>
      <ion-input v-model="login" label="Username or email" label-placement="stacked" autocomplete="username" required />
    </ion-item>
    <ion-item>
      <ion-input v-model="password" label="Password" label-placement="stacked" type="password" autocomplete="current-password" required />
    </ion-item>
    <ion-button class="submit" expand="block" type="submit" :disabled="loading">Log in</ion-button>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { IonButton, IonInput, IonItem } from '@ionic/vue';

defineProps<{ loading?: boolean }>();
const emit = defineEmits<{ submit: [login: string, password: string] }>();
const login = ref('');
const password = ref('');

function submit() {
  emit('submit', login.value, password.value);
}
</script>

<style scoped>
.submit {
  margin-top: 18px;
}
</style>
