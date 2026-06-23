<template>
  <div class="state" role="status" :aria-label="t('common.loading')"><ion-spinner name="crescent" /></div>
</template>

<script setup lang="ts">
import { IonSpinner } from '@ionic/vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
</script>

<style scoped>
.state {
  display: grid;
  place-items: center;
  min-height: 180px;
}
</style>
