import type { CapacitorConfig } from '@capacitor/cli';

const allowCleartext = process.env.CAPACITOR_ALLOW_CLEARTEXT === 'true';

const config: CapacitorConfig = {
  appId: 'com.relay.messenger',
  appName: 'Relay',
  webDir: 'dist',
  server: {
    androidScheme: allowCleartext ? 'http' : 'https',
    cleartext: allowCleartext
  }
};

export default config;
