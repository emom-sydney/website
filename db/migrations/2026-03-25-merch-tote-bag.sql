BEGIN;

ALTER TABLE merch_items
DROP CONSTRAINT IF EXISTS merch_items_category_check;

ALTER TABLE merch_items
ADD CONSTRAINT merch_items_category_check
CHECK (category IN ('tshirt', 'mug', 'keyring', 'tote_bag'));

INSERT INTO merch_items (slug, name, category, description, sort_order)
VALUES (
  'black-tote-bag-custom-logo',
  'Black Tote Bag with Custom Logo Stamp',
  'tote_bag',
  'Black tote bag with custom logo stamp.',
  50
)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO merch_variants (merch_item_id, variant_label, size, color, image_url)
SELECT
  id,
  'Standard',
  NULL,
  'black',
  '/assets/img/merch/tote.jpg'
FROM merch_items
WHERE slug = 'black-tote-bag-custom-logo'
ON CONFLICT (merch_item_id, variant_label) DO NOTHING;

COMMIT;
