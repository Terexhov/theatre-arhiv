CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TEXT SEARCH CONFIGURATION russian_arch (COPY = russian);
ALTER TEXT SEARCH CONFIGURATION russian_arch
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, russian_stem;

CREATE OR REPLACE FUNCTION persons_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('russian_arch',
        coalesce(NEW.last_name,'') || ' ' ||
        coalesce(NEW.first_name,'') || ' ' ||
        coalesce(NEW.patronymic,'') || ' ' ||
        coalesce(NEW.bio,'')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION productions_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('russian_arch',
        coalesce(NEW.title,'') || ' ' ||
        coalesce(NEW.subtitle,'') || ' ' ||
        coalesce(NEW.playwright,'') || ' ' ||
        coalesce(NEW.description,'')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION documents_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('russian_arch',
        coalesce(NEW.title,'') || ' ' ||
        coalesce(NEW.doc_type,'') || ' ' ||
        coalesce(NEW.author,'') || ' ' ||
        coalesce(NEW.description,'')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER persons_search_trig
    BEFORE INSERT OR UPDATE ON persons
    FOR EACH ROW EXECUTE FUNCTION persons_search_update();

CREATE TRIGGER productions_search_trig
    BEFORE INSERT OR UPDATE ON productions
    FOR EACH ROW EXECUTE FUNCTION productions_search_update();

CREATE TRIGGER documents_search_trig
    BEFORE INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_search_update();

CREATE INDEX idx_persons_search     ON persons     USING GIN(search_vector);
CREATE INDEX idx_productions_search ON productions USING GIN(search_vector);
CREATE INDEX idx_documents_search   ON documents   USING GIN(search_vector);
CREATE INDEX idx_persons_trgm       ON persons     USING GIN(last_name gin_trgm_ops);
CREATE INDEX idx_productions_trgm   ON productions USING GIN(title gin_trgm_ops);

CREATE VIEW universal_search AS
    SELECT 'person'     AS entity_type, id, last_name || ' ' || coalesce(first_name,'') AS title, search_vector FROM persons
    UNION ALL
    SELECT 'production', id, title, search_vector FROM productions
    UNION ALL
    SELECT 'document',   id, title || ' (' || doc_type || ')', search_vector FROM documents;

-- Фонды по периодам
INSERT INTO funds (code, name, date_from, date_to, description) VALUES
('Ф-1', 'Ранний период',      NULL,           '1950-12-31', 'Документы до 1950 года'),
('Ф-2', 'Советский период',   '1951-01-01',   '1991-12-31', 'Документы 1951–1991 годов'),
('Ф-3', 'Современный период', '1992-01-01',   NULL,         'Документы с 1992 года');

-- Описи по типам для каждого фонда
INSERT INTO inventories (fund_id, number, title)
SELECT f.id, '1', 'Фотографии'          FROM funds f UNION ALL
SELECT f.id, '2', 'Видеозаписи'         FROM funds f UNION ALL
SELECT f.id, '3', 'Афиши и программки'  FROM funds f UNION ALL
SELECT f.id, '4', 'Тексты и рецензии'   FROM funds f UNION ALL
SELECT f.id, '5', 'Прочее'              FROM funds f;

-- Функции автоархивирования
CREATE OR REPLACE FUNCTION get_fund_id(doc_date DATE) RETURNS INT AS $$
DECLARE fid INT;
BEGIN
  SELECT id INTO fid FROM funds
  WHERE (date_from IS NULL OR doc_date >= date_from)
    AND (date_to   IS NULL OR doc_date <= date_to)
  LIMIT 1;
  IF fid IS NULL THEN SELECT id INTO fid FROM funds ORDER BY id DESC LIMIT 1; END IF;
  RETURN fid;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_inventory_id(fund_id INT, doc_type TEXT) RETURNS INT AS $$
DECLARE inv_id INT; inv_title TEXT;
BEGIN
  inv_title := CASE doc_type
    WHEN 'фотография'  THEN 'Фотографии'
    WHEN 'афиша'       THEN 'Афиши и программки'
    WHEN 'программка'  THEN 'Афиши и программки'
    WHEN 'видеозапись' THEN 'Видеозаписи'
    WHEN 'рецензия'    THEN 'Тексты и рецензии'
    WHEN 'текст пьесы' THEN 'Тексты и рецензии'
    ELSE 'Прочее'
  END;
  SELECT id INTO inv_id FROM inventories
  WHERE inventories.fund_id = get_inventory_id.fund_id AND title = inv_title;
  RETURN inv_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_or_create_case(inv_id INT, doc_year INT) RETURNS INT AS $$
DECLARE case_id INT; case_num TEXT; case_count INT;
BEGIN
  case_num := doc_year::TEXT;
  SELECT id INTO case_id FROM cases WHERE inventory_id = inv_id AND number = case_num;
  IF case_id IS NULL THEN
    SELECT COUNT(*)+1 INTO case_count FROM cases WHERE inventory_id = inv_id;
    INSERT INTO cases (inventory_id, number, title, date_from, date_to)
    VALUES (inv_id, case_num, doc_year::TEXT || ' год',
      (doc_year::TEXT || '-01-01')::DATE,
      (doc_year::TEXT || '-12-31')::DATE)
    RETURNING id INTO case_id;
  END IF;
  RETURN case_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION assign_archive_ref(doc_id INT, doc_type TEXT, doc_date DATE) RETURNS TEXT AS $$
DECLARE
  use_date DATE; fund_id INT; inv_id INT; case_id INT;
  unit_id INT; unit_num TEXT; unit_count INT;
  fund_code TEXT; inv_num TEXT; case_num TEXT; ref TEXT;
BEGIN
  use_date := COALESCE(doc_date, CURRENT_DATE);
  fund_id  := get_fund_id(use_date);
  inv_id   := get_inventory_id(fund_id, doc_type);
  case_id  := get_or_create_case(inv_id, EXTRACT(YEAR FROM use_date)::INT);
  SELECT COUNT(*)+1 INTO unit_count FROM archive_units WHERE case_id = assign_archive_ref.case_id;
  unit_num := unit_count::TEXT;
  INSERT INTO archive_units (case_id, unit_number, title, object_type, object_id)
  VALUES (case_id, unit_num, (SELECT title FROM documents WHERE id = doc_id), 'document', doc_id)
  RETURNING id INTO unit_id;
  SELECT f.code, i.number, c.number
  INTO fund_code, inv_num, case_num
  FROM archive_units au
  JOIN cases c ON c.id = au.case_id
  JOIN inventories i ON i.id = c.inventory_id
  JOIN funds f ON f.id = i.fund_id
  WHERE au.id = unit_id;
  ref := fund_code || ' Оп.' || inv_num || ' Д.' || case_num || ' Ед.хр.' || unit_num;
  UPDATE documents SET archive_unit_id = unit_id, archive_ref = ref WHERE id = doc_id;
  RETURN ref;
END;
$$ LANGUAGE plpgsql;
