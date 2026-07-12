import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const templatePath = path.join(
  projectDir,
  'node_modules',
  '@capacitor',
  'cli',
  'dist',
  'util',
  'template.js'
);

const incompatibleCall = 'await tar_1.default.extract({ file: src, cwd: dir });';
const compatibleCall = [
  'const tar = tar_1.default ?? tar_1;',
  'await tar.extract({ file: src, cwd: dir });'
].join('\n    ');

const source = await readFile(templatePath, 'utf8');
if (source.includes(compatibleCall)) {
  process.exit(0);
}
if (!source.includes(incompatibleCall)) {
  throw new Error(
    'Unsupported @capacitor/cli template implementation; review the tar compatibility patch.'
  );
}

await writeFile(templatePath, source.replace(incompatibleCall, compatibleCall));
console.log('Applied @capacitor/cli tar 7 compatibility patch.');
