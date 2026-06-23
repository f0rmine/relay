#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/mobile"

npm install
npm run build
npm test
npx cap sync android

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
