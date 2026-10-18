-- DRAFT REFERENCE ONLY. PostgreSQL 15+. No deployment until source rights and data governance approved.
-- Source metadata and raw snapshots are separate from model features.

CREATE TABLE IF NOT EXISTS source_registry (
  source_id text PRIMARY KEY,
  endpoint text NOT NULL,
  permission_state text NOT NULL DEFAULT 'PENDING_AUTH',
  license_reviewed_at timestamptz,
  schema_verified_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_legal_dong (
  region_code_10 char(10) NOT NULL,
  lawd_5 char(5) NOT NULL,
  region_name text NOT NULL,
  valid_from date,
  valid_to date,
  snapshot_id text NOT NULL,
  raw_sha256 char(64) NOT NULL,
  PRIMARY KEY (region_code_10, snapshot_id)
);

-- Multiple snapshots may share the same partition; never overwrite revision history.
CREATE TABLE IF NOT EXISTS collection_run (
  run_id text PRIMARY KEY,
  source_id text NOT NULL,
  lawd_5 char(5),
  contract_ymd char(6),
  official_total_count integer,
  items_received integer,
  planned_pages integer,
  completed_pages integer NOT NULL DEFAULT 0,
  state text NOT NULL CHECK (state IN
    ('PENDING','PENDING_AUTH','FETCH_FAILED','PARTIAL','SCHEMA_CHANGED',
     'API_REJECTED','VERIFY_REQUIRED','CONFIRMED_ZERO','COMPLETE')),
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  admission_state text NOT NULL DEFAULT 'BLOCKED',
  CHECK (items_received IS NULL OR items_received >= 0),
  CHECK (official_total_count IS NULL OR official_total_count >= 0),
  CHECK (state NOT IN ('COMPLETE', 'CONFIRMED_ZERO') OR
         (planned_pages = completed_pages AND
          items_received = official_total_count)),
  CHECK (state != 'CONFIRMED_ZERO' OR official_total_count = 0)
);

CREATE TABLE IF NOT EXISTS raw_page_receipt (
  run_id text NOT NULL REFERENCES collection_run(run_id),
  page_no integer NOT NULL CHECK (page_no > 0),
  object_uri text NOT NULL,
  sha256 char(64) NOT NULL,
  bytes_length bigint NOT NULL CHECK (bytes_length >= 0),
  retrieved_at timestamptz NOT NULL,
  result_code text,
  PRIMARY KEY(run_id, page_no)
);

-- Raw schema is retained; no price inference or fuzzy de-duplication at this gate.
CREATE TABLE IF NOT EXISTS rtms_sale_observation (
  run_id text NOT NULL REFERENCES collection_run(run_id),
  page_no integer NOT NULL,
  row_ordinal integer NOT NULL,
  contract_date date,
  lawd_5 char(5),
  raw_apartment_name text,
  raw_apartment_seq text,
  price_10k_krw numeric(17,0),
  exclusive_area_m2 numeric(12,4),
  floor integer,
  cancellation_marker text,
  raw_row_json jsonb NOT NULL,
  PRIMARY KEY(run_id,page_no,row_ordinal)
);
