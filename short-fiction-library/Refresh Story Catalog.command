#!/bin/zsh -l

set -e

library_dir="${0:A:h}"
cd "$library_dir"

refresh_log="/tmp/short-fiction-library-refresh-${UID}.log"
echo "Refreshing the story catalog from the EPUB files…"

if python3 -B scripts/build_library.py >"$refresh_log" 2>&1 && npm run build >>"$refresh_log" 2>&1; then
  story_count=$(python3 -B -c 'import json; print(json.load(open("library-report.json"))["records"])')
  echo "Done — ${story_count} stories are ready."
  echo "You can now open the library."
else
  echo "The refresh did not finish. The last messages were:"
  /usr/bin/tail -n 24 "$refresh_log"
fi

read -r "?Press Return to close. "
