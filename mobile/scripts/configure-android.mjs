import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const mobileRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const manifestPath = path.join(
  mobileRoot,
  'android',
  'app',
  'src',
  'main',
  'AndroidManifest.xml'
);
const allowCleartext = process.env.CAPACITOR_ALLOW_CLEARTEXT === 'true';

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
await writeFile(manifestPath, manifest);

console.log(
  `Android manifest configured: backups disabled, cleartext ${allowCleartext ? 'enabled' : 'disabled'}`
);
