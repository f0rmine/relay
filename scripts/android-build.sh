#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/mobile"

if [[ ! -d "node_modules" ]]; then
  npm install
fi

npm run build
npx cap sync android

cd "$ROOT_DIR/mobile/android"
./gradlew assembleDebug

APK_SOURCE="$ROOT_DIR/mobile/android/app/build/outputs/apk/debug/app-debug.apk"
APK_TARGET="$ROOT_DIR/mobile/android/app/build/outputs/apk/debug/relay-debug-latest.apk"
cp "$APK_SOURCE" "$APK_TARGET"

echo "APK built:"
echo "$APK_TARGET"
