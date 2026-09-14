#!/bin/bash
set -uo pipefail
E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$E2E_DIR/.last_data_dir" ]; then
  DATA_DIR=$(cat "$E2E_DIR/.last_data_dir")
  for name in backend admin-frontend account-frontend; do
    if [ -f "$DATA_DIR/$name.pid" ]; then
      kill "$(cat "$DATA_DIR/$name.pid")" 2>/dev/null || true
    fi
  done
  rm -f "$E2E_DIR/.last_data_dir"
  echo "Stopped. Data dir was: $DATA_DIR"
else
  echo "No recorded data dir - nothing to stop."
fi
