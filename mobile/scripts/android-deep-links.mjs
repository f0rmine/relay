const BLOCK_START = '<!-- RELAY_PASSWORD_RESET_DEEP_LINK_START -->';
const BLOCK_END = '<!-- RELAY_PASSWORD_RESET_DEEP_LINK_END -->';
const BLOCK_PATTERN = new RegExp(
  `\\n\\s*${BLOCK_START}[\\s\\S]*?${BLOCK_END}\\n?`,
  'g'
);

export function normalizeAppLinkHost(value) {
  const host = value?.trim().toLowerCase();
  if (!host) return null;
  if (
    host.length > 253
    || !/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(host)
  ) {
    throw new Error('CAPACITOR_APP_LINK_HOST must be a bare DNS hostname');
  }
  return host;
}

export function configurePasswordResetDeepLinks(manifest, appLinkHost) {
  const host = normalizeAppLinkHost(appLinkHost);
  const withoutPreviousBlock = manifest.replace(BLOCK_PATTERN, '');
  const activityClose = withoutPreviousBlock.indexOf('</activity>');
  if (activityClose === -1) throw new Error('Android manifest has no activity element');

  const httpsFilter = host ? `
            <intent-filter android:autoVerify="true">
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data
                    android:scheme="https"
                    android:host="${host}"
                    android:path="/reset-password" />
            </intent-filter>
` : '';
  const block = `
            ${BLOCK_START}
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data
                    android:scheme="@string/custom_url_scheme"
                    android:host="reset-password" />
            </intent-filter>
${httpsFilter}            ${BLOCK_END}
`;

  return `${withoutPreviousBlock.slice(0, activityClose)}${block}${withoutPreviousBlock.slice(activityClose)}`;
}

export function setStringResource(xml, name, value) {
  const pattern = new RegExp(`(<string\\s+name=["']${name}["']>)[^<]*(</string>)`);
  if (!pattern.test(xml)) throw new Error(`Android string resource not found: ${name}`);
  return xml.replace(pattern, `$1${value}$2`);
}

export function setAndroidVersion(gradle, version) {
  const parts = version.split('.').map(Number);
  if (parts.length !== 3 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 99)) {
    throw new Error('Mobile version must use numeric major.minor.patch components below 100');
  }
  const versionCode = parts[0] * 10000 + parts[1] * 100 + parts[2];
  if (versionCode < 1) throw new Error('Android versionCode must be positive');
  if (!/versionCode\s+\d+/.test(gradle) || !/versionName\s+"[^"]+"/.test(gradle)) {
    throw new Error('Android Gradle version metadata was not found');
  }
  return gradle
    .replace(/versionCode\s+\d+/, `versionCode ${versionCode}`)
    .replace(/versionName\s+"[^"]+"/, `versionName "${version}"`);
}
