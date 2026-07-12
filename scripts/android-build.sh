#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/mobile"

npm install
npm run build
npm test

ICON_SOURCE="$ROOT_DIR/mobile/assets/logo.png"
if [[ -f "$ICON_SOURCE" ]]; then
npm run assets:android
else
  echo "Android icon source not found: $ICON_SOURCE"
  echo "Using the currently generated launcher icon resources."
fi

export CAPACITOR_ALLOW_CLEARTEXT="${CAPACITOR_ALLOW_CLEARTEXT:-true}"
npx cap sync android
npm run android:configure

if [[ -d "/usr/lib/jvm/java-21-openjdk-amd64" ]]; then
  export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
fi

cd "$ROOT_DIR/mobile/android"
./gradlew assembleDebug

APK_SOURCE="$ROOT_DIR/mobile/android/app/build/outputs/apk/debug/app-debug.apk"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
APK_TARGET="$ROOT_DIR/mobile/android/app/build/outputs/apk/debug/relay-debug-${TIMESTAMP}.apk"
cp "$APK_SOURCE" "$APK_TARGET"

echo "APK built:"
echo "$APK_TARGET"
