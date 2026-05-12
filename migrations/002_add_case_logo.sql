-- Добавить поле логотипа в дела
ALTER TABLE cases ADD COLUMN IF NOT EXISTS logo_path TEXT;
