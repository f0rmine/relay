<template>
  <div class="language-selector-wrapper">
    <ion-button :id="triggerId" fill="clear" class="language-btn">
      <ion-icon :icon="globeOutline" :slot="iconOnly ? 'icon-only' : 'start'"></ion-icon>
      <span v-if="!iconOnly" class="lang-text">{{ currentLangName }}</span>
    </ion-button>

    <ion-popover :trigger="triggerId" trigger-action="click" alignment="center">
      <ion-content>
        <ion-list lines="none" class="lang-list">
          <ion-item button :color="locale === 'en' ? 'light' : ''" @click="selectLocale('en')">
            <ion-label>{{ t('language.english') }}</ion-label>
            <ion-icon v-if="locale === 'en'" :icon="checkmark" slot="end" color="primary"></ion-icon>
          </ion-item>
          <ion-item button :color="locale === 'uk' ? 'light' : ''" @click="selectLocale('uk')">
            <ion-label>{{ t('language.ukrainian') }}</ion-label>
            <ion-icon v-if="locale === 'uk'" :icon="checkmark" slot="end" color="primary"></ion-icon>
          </ion-item>
        </ion-list>
      </ion-content>
    </ion-popover>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { 
  IonButton, IonIcon, IonPopover, IonContent, IonList, IonItem, IonLabel, popoverController 
} from '@ionic/vue';
import { globeOutline, checkmark } from 'ionicons/icons';
import { useI18n } from 'vue-i18n';
import { isSupportedLocale, setLocale } from '@/i18n';

defineProps<{ iconOnly?: boolean }>();

const triggerId = `lang-trigger-${Math.random().toString(36).substring(2, 9)}`;

const { locale, t } = useI18n();

const currentLangName = computed(() => locale.value.toUpperCase());

async function selectLocale(newLocale: string) {
  if (isSupportedLocale(newLocale)) {
    setLocale(newLocale);
    const popover = await popoverController.getTop();
    if (popover) {
      popover.dismiss();
    }
  }
}
</script>

<style scoped>
.language-selector-wrapper {
  display: inline-block;
}
.language-btn {
  --padding-start: 8px;
  --padding-end: 8px;
  margin: 0;
  text-transform: none;
  font-weight: 500;
  font-size: 14px;
}
.lang-text {
  margin-left: 4px;
}
.lang-list {
  padding: 4px 0;
}
</style>
