<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar style="--background: transparent;">
        <ion-buttons slot="end">
          <LanguageSelector />
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="page-content">
      <div class="content-wrap auth-card">
        <h1>Relay</h1>
        <template v-if="challengeToken">
          <h2>{{ t('auth.twoFactor.title') }}</h2>
          <p class="muted">{{ t('auth.twoFactor.subtitle') }}</p>
          <ErrorState v-if="error" :message="error" />
          <form @submit.prevent="verifyTwoFactor">
            <ion-item>
              <ion-input
                v-model="twoFactorCode"
                :label="t('auth.twoFactor.codeLabel')"
                label-placement="stacked"
                inputmode="numeric"
                autocomplete="one-time-code"
                :placeholder="t('auth.twoFactor.codeHint')"
                required
              />
            </ion-item>
            <ion-button class="submit" expand="block" type="submit" :disabled="auth.loading || !twoFactorCode.trim()">
              {{ t('auth.twoFactor.verify') }}
            </ion-button>
          </form>
          <ion-button fill="clear" expand="block" @click="challengeToken = null; twoFactorCode = ''; error = ''">
            {{ t('auth.twoFactor.back') }}
          </ion-button>
        </template>
        <template v-else>
          <p class="muted">{{ t('auth.login.subtitle') }}</p>
          <StatusState v-if="resetComplete" :message="t('auth.reset.success')" />
          <ErrorState v-if="error" :message="error" />
          <LoginForm :loading="auth.loading" @submit="submit" />
          <ion-button fill="clear" expand="block" router-link="/forgot-password">{{ t('auth.login.forgotPassword') }}</ion-button>
          <ion-button fill="clear" expand="block" router-link="/register">{{ t('auth.login.createAccount') }}</ion-button>
        </template>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { IonButton, IonContent, IonPage, IonHeader, IonInput, IonItem, IonToolbar, IonButtons } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import LoginForm from '@/components/auth/LoginForm.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import ErrorState from '@/components/ErrorState.vue';
import StatusState from '@/components/StatusState.vue';
import { displayError } from '@/api/client';
import { useAuthStore } from '@/stores/auth';

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const error = ref('');
const challengeToken = ref<string | null>(null);
const twoFactorCode = ref('');
const { t } = useI18n();
const resetComplete = computed(() => route.query.reset === 'success');

async function submit(login: string, password: string) {
  error.value = '';
  try {
    const result = await auth.login(login, password);
    if ('requires_2fa' in result && result.requires_2fa) {
      challengeToken.value = result.challenge_token;
      twoFactorCode.value = '';
      return;
    }
    router.replace('/conversations');
  } catch (err: unknown) {
    error.value = displayError(err, t('auth.login.failed'));
  }
}

async function verifyTwoFactor() {
  if (!challengeToken.value || !twoFactorCode.value.trim()) return;
  error.value = '';
  try {
    await auth.verifyTwoFactor(challengeToken.value, twoFactorCode.value.trim());
    challengeToken.value = null;
    twoFactorCode.value = '';
    router.replace('/conversations');
  } catch (err: unknown) {
    error.value = displayError(err, t('auth.twoFactor.failed'));
  }
}
</script>

<style scoped>
.submit {
  margin-top: 18px;
}
</style>
