CREATE TABLE schema_migration (
    version     text        PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source (
    id    smallint PRIMARY KEY,
    code  text NOT NULL UNIQUE,
    name  text NOT NULL,
    url   text
);

CREATE TABLE indicator (
    id           smallint PRIMARY KEY,
    code         text     NOT NULL UNIQUE,
    source_id    smallint NOT NULL REFERENCES source (id) ON DELETE RESTRICT,
    source_code  text     NOT NULL,
    zone         text     NOT NULL,
    unit         text     NOT NULL,
    resolution   interval NOT NULL,
    UNIQUE (source_id, source_code, zone, resolution)
);

CREATE TABLE observation (
    indicator_id  smallint    NOT NULL REFERENCES indicator (id) ON DELETE RESTRICT,
    period_start  timestamptz NOT NULL,
    published_at  timestamptz NOT NULL,
    value         numeric     NOT NULL,
    estimated     boolean     NOT NULL DEFAULT false,
    PRIMARY KEY (indicator_id, period_start, published_at)
);

INSERT INTO schema_migration (version) VALUES ('0001');
