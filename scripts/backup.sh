#!/bin/sh
# Ежедневный pg_dump в /backups с ротацией. Запускается контейнером backup.
set -eu
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
INTERVAL="${BACKUP_INTERVAL_SEC:-86400}"

while true; do
  file="/backups/barber-$(date +%Y%m%d-%H%M).sql.gz"
  if pg_dump -h db -U barber barber | gzip > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup: $file ($(du -h "$file" | cut -f1))"
  else
    rm -f "$file.tmp"
    echo "backup: pg_dump failed" >&2
  fi
  find /backups -name 'barber-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
  sleep "$INTERVAL"
done
