BEGIN;

ALTER TABLE merch_items
ADD COLUMN IF NOT EXISTS suggested_price numeric(10, 2);

UPDATE merch_items
SET suggested_price = CASE slug
  WHEN 'classic-logo-tee' THEN 35.00
  WHEN 'grid-logo-tee' THEN 35.00
  WHEN 'emom-stickers' THEN 8.00
  WHEN 'emom-keyring' THEN 10.00
  WHEN 'black-tote-bag-custom-logo' THEN 22.00
  ELSE suggested_price
END
WHERE suggested_price IS NULL;

ALTER TABLE merch_items
ALTER COLUMN suggested_price SET NOT NULL;

ALTER TABLE merch_items
DROP CONSTRAINT IF EXISTS merch_items_suggested_price_check;

ALTER TABLE merch_items
ADD CONSTRAINT merch_items_suggested_price_check
CHECK (suggested_price >= 0);

ALTER TABLE merch_interest_lines
ADD COLUMN IF NOT EXISTS submitted_price numeric(10, 2);

UPDATE merch_interest_lines mil
SET submitted_price = mi.suggested_price
FROM merch_variants mv
JOIN merch_items mi
  ON mi.id = mv.merch_item_id
WHERE mv.id = mil.merch_variant_id
  AND mil.submitted_price IS NULL;

ALTER TABLE merch_interest_lines
ALTER COLUMN submitted_price SET NOT NULL;

ALTER TABLE merch_interest_lines
DROP CONSTRAINT IF EXISTS merch_interest_lines_submitted_price_check;

ALTER TABLE merch_interest_lines
ADD CONSTRAINT merch_interest_lines_submitted_price_check
CHECK (submitted_price >= 0);

COMMIT;
