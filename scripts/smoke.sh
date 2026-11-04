#!/usr/bin/env bash
# Смоук-тест поднятого docker compose: сайт, запись, защита от двойной записи.
set -euo pipefail
BASE="${BASE:-http://localhost:${WEB_PORT:-80}}"
api() { curl -fsS "$BASE/api$1"; }

for _ in $(seq 1 60); do curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break; sleep 2; done

curl -fsS -o /dev/null "$BASE/" && curl -fsS -o /dev/null "$BASE/privacy.html" && curl -fsS -o /dev/null "$BASE/admin/"
echo "✓ страницы отдаются"

day=$(api "/dates?master_id=1&service_id=1" | python3 -c "import sys,json; print(json.load(sys.stdin)[-1])")
slot=$(api "/slots?master_id=1&service_id=1&day=$day" | python3 -c "import sys,json; print(json.load(sys.stdin)[0])")
body="{\"service_id\":1,\"master_id\":1,\"start_at\":\"${day}T${slot}:00\",\"name\":\"Smoke\",\"phone\":\"+7900$(date +%s | tail -c 8)\",\"consent\":true}"

codes=$(for _ in 1 2 3 4 5; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "$BASE/api/bookings" -H 'Content-Type: application/json' -d "$body" &
done; wait)
created=$(echo "$codes" | grep -c '^201$' || true)
conflicts=$(echo "$codes" | grep -c '^409$' || true)
echo "параллельные записи на $day $slot: 201×$created, 409×$conflicts"
[ "$created" = 1 ] && [ "$conflicts" = 4 ] || { echo "✗ ожидалась ровно одна успешная запись"; exit 1; }
echo "✓ двойная запись невозможна"
