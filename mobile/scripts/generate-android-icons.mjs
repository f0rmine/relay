import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import sharp from 'sharp';

const mobileRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.resolve(
  process.argv[2] ?? path.join(mobileRoot, 'assets', 'logo.png')
);
const resourcesPath = path.resolve(
  process.argv[3] ?? path.join(mobileRoot, 'android', 'app', 'src', 'main', 'res')
);

const targets = [
  { density: 'mdpi', launcher: 48, foreground: 108 },
  { density: 'hdpi', launcher: 72, foreground: 162 },
  { density: 'xhdpi', launcher: 96, foreground: 216 },
  { density: 'xxhdpi', launcher: 144, foreground: 324 },
  { density: 'xxxhdpi', launcher: 192, foreground: 432 }
];
const SAFE_AREA_RATIO = 0.55;

async function renderInsetIcon(size) {
  const contentSize = Math.floor(size * SAFE_AREA_RATIO);
  const remaining = size - contentSize;
  const startPadding = Math.floor(remaining / 2);
  const endPadding = remaining - startPadding;

  return sharp(sourcePath)
    .resize(contentSize, contentSize, { fit: 'contain' })
    .extend({
      top: startPadding,
      bottom: endPadding,
      left: startPadding,
      right: endPadding,
      background: { r: 0, g: 0, b: 0, alpha: 0 }
    })
    .png()
    .toBuffer();
}

async function writeSquareIcon(outputPath, size) {
  await sharp(sourcePath)
    .resize(size, size, { fit: 'cover' })
    .png()
    .toFile(outputPath);
}

async function writeRoundIcon(outputPath, size) {
  const icon = await renderInsetIcon(size);
  const mask = Buffer.from(
    `<svg width="${size}" height="${size}"><circle cx="${size / 2}" cy="${size / 2}" r="${size / 2}" fill="white"/></svg>`
  );

  await sharp(icon)
    .composite([{ input: mask, blend: 'dest-in' }])
    .png()
    .toFile(outputPath);
}

async function writeAdaptiveForeground(outputPath, size) {
  const icon = await renderInsetIcon(size);
  await sharp(icon).toFile(outputPath);
}

async function generate() {
  const metadata = await sharp(sourcePath).metadata();
  if (metadata.format !== 'png') {
    throw new Error(`Android icon must be a PNG: ${sourcePath}`);
  }
  if (!metadata.width || !metadata.height || metadata.width !== metadata.height) {
    throw new Error('Android icon must be square.');
  }
  if (metadata.width < 1024) {
    throw new Error('Android icon must be at least 1024x1024 pixels.');
  }

  await Promise.all(
    targets.map(async ({ density, launcher, foreground }) => {
      const targetDirectory = path.join(resourcesPath, `mipmap-${density}`);
      await mkdir(targetDirectory, { recursive: true });
      return Promise.all([
        writeSquareIcon(path.join(targetDirectory, 'ic_launcher.png'), launcher),
        writeRoundIcon(path.join(targetDirectory, 'ic_launcher_round.png'), launcher),
        writeAdaptiveForeground(
          path.join(targetDirectory, 'ic_launcher_foreground.png'),
          foreground
        )
      ]);
    })
  );

  console.log(`Android launcher icons generated from ${sourcePath}`);
}

generate().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
