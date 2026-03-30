CREATE TABLE funds (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20) UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    date_from   DATE,
    date_to     DATE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE inventories (
    id          SERIAL PRIMARY KEY,
    fund_id     INT NOT NULL REFERENCES funds(id),
    number      VARCHAR(20) NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    date_from   DATE,
    date_to     DATE,
    UNIQUE (fund_id, number)
);

CREATE TABLE cases (
    id           SERIAL PRIMARY KEY,
    inventory_id INT NOT NULL REFERENCES inventories(id),
    number       VARCHAR(20) NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    date_from    DATE,
    date_to      DATE,
    UNIQUE (inventory_id, number)
);

CREATE TABLE archive_units (
    id               SERIAL PRIMARY KEY,
    case_id          INT NOT NULL REFERENCES cases(id),
    unit_number      VARCHAR(20) NOT NULL,
    title            TEXT NOT NULL,
    object_type      VARCHAR(50),
    object_id        INT,
    storage_location TEXT,
    condition        VARCHAR(50),
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (case_id, unit_number)
);

CREATE TABLE persons (
    id            SERIAL PRIMARY KEY,
    last_name     TEXT NOT NULL,
    first_name    TEXT,
    patronymic    TEXT,
    born          DATE,
    died          DATE,
    roles         TEXT[],
    bio           TEXT,
    search_vector tsvector,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE productions (
    id            SERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    subtitle      TEXT,
    premiere_date DATE,
    last_date     DATE,
    playwright    TEXT,
    director_id   INT REFERENCES persons(id),
    genre         TEXT,
    season        TEXT,
    description   TEXT,
    search_vector tsvector,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE production_persons (
    production_id      INT NOT NULL REFERENCES productions(id),
    person_id          INT NOT NULL REFERENCES persons(id),
    role_in_production TEXT,
    PRIMARY KEY (production_id, person_id, role_in_production)
);

CREATE TABLE object_relations (
    id            SERIAL PRIMARY KEY,
    source_type   VARCHAR(50) NOT NULL,
    source_id     INT NOT NULL,
    target_type   VARCHAR(50) NOT NULL,
    target_id     INT NOT NULL,
    relation_type TEXT
);

CREATE TABLE tags (
    id   SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE tag_assignments (
    tag_id      INT NOT NULL REFERENCES tags(id),
    object_type VARCHAR(50) NOT NULL,
    object_id   INT NOT NULL,
    PRIMARY KEY (tag_id, object_type, object_id)
);

CREATE TABLE photos (
    id            SERIAL PRIMARY KEY,
    title         TEXT,
    date_taken    DATE,
    photographer  TEXT,
    file_path     TEXT,
    format        TEXT,
    description   TEXT,
    search_vector tsvector,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE recordings (
    id            SERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    date_recorded DATE,
    duration      INTERVAL,
    format        TEXT,
    file_path     TEXT,
    description   TEXT,
    search_vector tsvector,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE texts (
    id            SERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    text_type     TEXT,
    author        TEXT,
    content       TEXT,
    file_path     TEXT,
    search_vector tsvector,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE documents (
    id            SERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    description   TEXT,
    date_created  DATE,
    author        TEXT,
    file_path     TEXT,
    file_format   TEXT,
    archive_unit_id INT REFERENCES archive_units(id),
    archive_ref   TEXT,
    search_vector tsvector,
    created_at    TIMESTAMPTZ DEFAULT now()
);
