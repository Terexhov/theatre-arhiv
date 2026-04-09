#!/bin/bash
# Одноразовая миграция БД — запустить один раз
SERVER="root@178.253.38.120"

echo "→ Running DB migration..."
ssh "$SERVER" bash <<'EOF'
  psql -h localhost -U archive -d theatre -c "
    ALTER TABLE cases ADD COLUMN IF NOT EXISTS show_on_site BOOLEAN DEFAULT false;
    ALTER TABLE cases ADD COLUMN IF NOT EXISTS project_group TEXT;
    ALTER TABLE productions ADD COLUMN IF NOT EXISTS show_on_site BOOLEAN DEFAULT false;
    ALTER TABLE documents ADD COLUMN IF NOT EXISTS show_on_site BOOLEAN DEFAULT false;
    CREATE TABLE IF NOT EXISTS site_config (
      key TEXT PRIMARY KEY,
      value TEXT
    );
    INSERT INTO site_config (key, value) VALUES
      ('hero_title', 'Эдуард Бояков'),
      ('hero_tagline', 'Режиссёр · Продюсер · Театральный деятель'),
      ('hero_born', '1964'),
      ('hero_roles', 'Режиссёр, продюсер, театральный менеджер'),
      ('hero_bio', '')
    ON CONFLICT (key) DO NOTHING;
  "
  echo "✓ Migration done"
EOF
