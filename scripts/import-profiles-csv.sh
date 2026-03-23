#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/import-profiles-csv.sh path/to/profiles.csv

Imports profile metadata from a CSV into the `profiles` table by matching
`full_name` in the CSV against `display_name` in Postgres, case-insensitively.

Expected CSV headers:
  stage_name,full_name,first_name,last_name,email,bio

Connection is taken from the normal Postgres environment used by this repo,
for example via `.pgenv` or `DATABASE_URL`.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

csv_path="$1"

if [[ ! -f "$csv_path" ]]; then
  echo "CSV file not found: $csv_path" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 -v csv_path="$csv_path" <<'SQL'
BEGIN;

CREATE TEMP TABLE import_profiles_csv (
  stage_name text,
  full_name text,
  first_name text,
  last_name text,
  email text,
  bio text
);

\copy import_profiles_csv (stage_name, full_name, first_name, last_name, email, bio) FROM :'csv_path' WITH (FORMAT csv, HEADER true)

CREATE TEMP TABLE prepared_import AS
SELECT
  NULLIF(BTRIM(stage_name), '') AS stage_name,
  NULLIF(BTRIM(full_name), '') AS full_name,
  NULLIF(BTRIM(first_name), '') AS first_name,
  NULLIF(BTRIM(last_name), '') AS last_name,
  NULLIF(BTRIM(email), '') AS email,
  NULLIF(BTRIM(bio), '') AS bio,
  LOWER(NULLIF(BTRIM(full_name), '')) AS full_name_key,
  LOWER(NULLIF(BTRIM(stage_name), '')) AS stage_name_key
FROM import_profiles_csv
WHERE NULLIF(BTRIM(full_name), '') IS NOT NULL;

DO $$
BEGIN
  IF EXISTS (
    WITH candidate_matches AS (
      SELECT
        i.full_name_key,
        i.stage_name_key,
        COUNT(*) AS profile_match_count
      FROM prepared_import i
      JOIN profiles p
        ON LOWER(p.display_name) = i.full_name_key
        OR (
          i.stage_name_key IS NOT NULL
          AND LOWER(p.display_name) = i.stage_name_key
        )
      GROUP BY i.full_name_key, i.stage_name_key
    )
    SELECT 1
    FROM candidate_matches
    WHERE profile_match_count > 1
  ) THEN
    RAISE EXCEPTION 'Multiple profiles match a CSV row; full_name/stage_name pair is ambiguous';
  END IF;
END $$;

CREATE TEMP TABLE matched_import AS
WITH candidate_matches AS (
  SELECT
    i.stage_name,
    i.full_name,
    i.first_name,
    i.last_name,
    i.email,
    i.bio,
    i.full_name_key,
    i.stage_name_key,
    p.id AS profile_id,
    CASE
      WHEN i.stage_name_key IS NOT NULL AND LOWER(p.display_name) = i.stage_name_key THEN 1
      WHEN LOWER(p.display_name) = i.full_name_key THEN 2
      ELSE 3
    END AS match_rank
  FROM prepared_import i
  JOIN profiles p
    ON LOWER(p.display_name) = i.full_name_key
    OR (
      i.stage_name_key IS NOT NULL
      AND LOWER(p.display_name) = i.stage_name_key
    )
),
ranked_matches AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY full_name_key, COALESCE(stage_name_key, '')
      ORDER BY match_rank, profile_id
    ) AS row_num
  FROM candidate_matches
)
SELECT
  profile_id,
  stage_name,
  full_name,
  first_name,
  last_name,
  email,
  bio,
  full_name_key,
  stage_name_key
FROM ranked_matches
WHERE row_num = 1;

UPDATE profiles p
SET
  display_name = COALESCE(m.stage_name, p.display_name),
  first_name = m.first_name,
  last_name = m.last_name,
  email = m.email
FROM matched_import m
WHERE p.id = m.profile_id;

UPDATE profile_roles pr
SET
  bio = m.bio
FROM matched_import m
WHERE pr.profile_id = m.profile_id
  AND pr.role = 'artist'
  AND m.bio IS NOT NULL;

SELECT
  COUNT(*) AS matched_rows
FROM matched_import;

SELECT
  i.full_name AS unmatched_full_name
FROM prepared_import i
LEFT JOIN matched_import m
  ON m.full_name_key = i.full_name_key
  AND COALESCE(m.stage_name_key, '') = COALESCE(i.stage_name_key, '')
WHERE m.profile_id IS NULL
ORDER BY i.full_name;

COMMIT;
SQL
