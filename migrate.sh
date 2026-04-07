#!/bin/bash
# Одноразовая миграция БД — запустить один раз
SERVER="root@178.253.38.120"

echo "→ Running DB migration..."
ssh "$SERVER" bash <<'EOF'
  psql -U archive -d theatre -c "
    ALTER TABLE cases ADD COLUMN IF NOT EXISTS show_on_site BOOLEAN DEFAULT false;
    ALTER TABLE cases ADD COLUMN IF NOT EXISTS project_group TEXT;
  "
  echo "✓ Migration done"
EOF
