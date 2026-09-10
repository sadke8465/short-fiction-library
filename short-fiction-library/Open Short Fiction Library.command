#!/bin/zsh -l

set -e

library_dir="${0:A:h}"
cd "$library_dir"

if ! command -v npm >/dev/null 2>&1; then
  echo "This library needs Node.js to open."
  echo "Install Node.js, then double-click this file again."
  read -r "?Press Return to close. "
  exit 1
fi

if [ ! -x "node_modules/.bin/vinext" ]; then
  echo "Preparing the library on this computer for the first time…"
  npm install
fi

if [ ! -f "dist/server/index.js" ]; then
  echo "Building the local library site…"
  npm run build
fi

library_port=4173
while /usr/bin/nc -z 127.0.0.1 "$library_port" >/dev/null 2>&1; do
  library_port=$((library_port + 1))
done

library_log="/tmp/short-fiction-library-${UID}.log"
npm run start -- --hostname 127.0.0.1 --port "$library_port" >"$library_log" 2>&1 &
library_pid=$!

cleanup() {
  kill "$library_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM HUP

echo "Opening your Short Fiction Library…"
for attempt in {1..80}; do
  if /usr/bin/curl --silent --fail "http://127.0.0.1:${library_port}/" >/dev/null; then
    /usr/bin/open "http://127.0.0.1:${library_port}/"
    echo "The library is open in your browser."
    echo "Keep this window open while you read; close it to stop the library."
    wait "$library_pid"
    exit 0
  fi
  if ! kill -0 "$library_pid" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

echo "The library could not start. The last messages were:"
/usr/bin/tail -n 20 "$library_log"
read -r "?Press Return to close. "
exit 1
