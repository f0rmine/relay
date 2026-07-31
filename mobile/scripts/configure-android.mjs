import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  configurePasswordResetDeepLinks,
  setAndroidVersion,
  setStringResource
} from './android-deep-links.mjs';

const mobileRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const manifestPath = path.join(
  mobileRoot,
  'android',
  'app',
  'src',
  'main',
  'AndroidManifest.xml'
);
const stringsPath = path.join(
  mobileRoot,
  'android',
  'app',
  'src',
  'main',
  'res',
  'values',
  'strings.xml'
);
const gradlePath = path.join(mobileRoot, 'android', 'app', 'build.gradle');
const packagePath = path.join(mobileRoot, 'package.json');
const allowCleartext = process.env.CAPACITOR_ALLOW_CLEARTEXT === 'true';
const appLinkHost = process.env.CAPACITOR_APP_LINK_HOST;

function setApplicationAttribute(manifest, name, value) {
  const attribute = `android:${name}="${value}"`;
  const pattern = new RegExp(`android:${name}="[^"]*"`);
  if (pattern.test(manifest)) return manifest.replace(pattern, attribute);
  return manifest.replace('<application', `<application\n        ${attribute}`);
}

let manifest = await readFile(manifestPath, 'utf8');
manifest = setApplicationAttribute(manifest, 'allowBackup', 'false');
manifest = setApplicationAttribute(manifest, 'fullBackupContent', 'false');
manifest = setApplicationAttribute(
  manifest,
  'usesCleartextTraffic',
  allowCleartext ? 'true' : 'false'
);
manifest = configurePasswordResetDeepLinks(manifest, appLinkHost);
await writeFile(manifestPath, manifest);

let strings = await readFile(stringsPath, 'utf8');
strings = setStringResource(strings, 'custom_url_scheme', 'relay');
await writeFile(stringsPath, strings);

const packageMetadata = JSON.parse(await readFile(packagePath, 'utf8'));
let gradle = await readFile(gradlePath, 'utf8');
gradle = setAndroidVersion(gradle, packageMetadata.version);
await writeFile(gradlePath, gradle);

console.log(
  `Android configured: backups disabled, cleartext ${allowCleartext ? 'enabled' : 'disabled'}, `
  + `password reset links enabled${appLinkHost ? ` for ${appLinkHost}` : ''}`
);
