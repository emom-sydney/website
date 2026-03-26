BEGIN;

ALTER TABLE merch_variants
ADD COLUMN IF NOT EXISTS style text;

ALTER TABLE merch_variants
DROP CONSTRAINT IF EXISTS merch_variants_merch_item_id_variant_label_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_merch_variants_unique_option
  ON merch_variants (
    merch_item_id,
    COALESCE(style, ''),
    COALESCE(size, ''),
    COALESCE(color, ''),
    variant_label
  );

COMMIT;
