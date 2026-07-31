import { describe, expect, it } from 'vitest';
import {
  configurePasswordResetDeepLinks,
  normalizeAppLinkHost,
  setAndroidVersion,
  setStringResource
} from './android-deep-links.mjs';

const manifest = `<manifest>
    <application>
        <activity>
        </activity>
    </application>
</manifest>`;

describe('Android password-reset deep-link configuration', () => {
  it('adds an idempotent custom-scheme filter', () => {
    const configured = configurePasswordResetDeepLinks(manifest);
    const configuredAgain = configurePasswordResetDeepLinks(configured);

    expect(configuredAgain).toContain('android:scheme="@string/custom_url_scheme"');
    expect(configuredAgain).toContain('android:host="reset-password"');
    expect(configuredAgain).not.toContain('android:autoVerify="true"');
    expect(configuredAgain.match(/RELAY_PASSWORD_RESET_DEEP_LINK_START/g)).toHaveLength(1);
  });

  it('adds a verified HTTPS filter only for a valid configured host', () => {
    const configured = configurePasswordResetDeepLinks(manifest, 'Relay.Example.com');

    expect(configured).toContain('android:autoVerify="true"');
    expect(configured).toContain('android:host="relay.example.com"');
    expect(configured).toContain('android:path="/reset-password"');
    expect(() => normalizeAppLinkHost('https://relay.example.com/path')).toThrow(
      'bare DNS hostname'
    );
  });

  it('updates the URL scheme and derives monotonic Android version metadata', () => {
    const strings = '<string name="custom_url_scheme">old.scheme</string>';
    const gradle = 'versionCode 1\nversionName "1.0"';

    expect(setStringResource(strings, 'custom_url_scheme', 'relay')).toContain('>relay<');
    expect(setAndroidVersion(gradle, '1.2.1')).toBe(
      'versionCode 10201\nversionName "1.2.1"'
    );
  });
});
