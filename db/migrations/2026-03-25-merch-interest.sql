BEGIN;

CREATE TABLE IF NOT EXISTS merch_items (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  slug text NOT NULL UNIQUE,
  name text NOT NULL,
  category text NOT NULL CHECK (category IN ('tshirt', 'mug', 'keyring', 'tote_bag')),
  description text,
  suggested_price numeric(10, 2) NOT NULL CHECK (suggested_price >= 0),
  is_active boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS merch_variants (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  merch_item_id integer NOT NULL REFERENCES merch_items(id) ON DELETE CASCADE,
  variant_label text NOT NULL,
  size text,
  color text,
  image_url text,
  is_active boolean NOT NULL DEFAULT true,
  UNIQUE (merch_item_id, variant_label)
);

CREATE TABLE IF NOT EXISTS merch_interest_submissions (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email text NOT NULL,
  comments text,
  submitted_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS merch_interest_lines (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  submission_id integer NOT NULL REFERENCES merch_interest_submissions(id) ON DELETE CASCADE,
  merch_variant_id integer NOT NULL REFERENCES merch_variants(id) ON DELETE CASCADE,
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
  submitted_price numeric(10, 2) NOT NULL CHECK (submitted_price >= 0),
  UNIQUE (submission_id, merch_variant_id)
);

CREATE INDEX IF NOT EXISTS idx_merch_variants_item_id ON merch_variants(merch_item_id);
CREATE INDEX IF NOT EXISTS idx_merch_interest_lines_submission_id ON merch_interest_lines(submission_id);
CREATE INDEX IF NOT EXISTS idx_merch_interest_lines_variant_id ON merch_interest_lines(merch_variant_id);
CREATE INDEX IF NOT EXISTS idx_merch_interest_submissions_email ON merch_interest_submissions(email);

INSERT INTO merch_items (slug, name, category, description, suggested_price, sort_order)
VALUES
  ('classic-logo-tee', 'Classic Logo T-Shirt', 'tshirt', 'EMOM logo tee in the classic style.', 35.00, 10),
  ('glitch-logo-tee', 'Glitch Logo T-Shirt', 'tshirt', 'Alternative EMOM logo tee with a glitch treatment.', 35.00, 20),
  ('emom-mug', 'EMOM Mug', 'mug', 'Ceramic mug for your studio or desk.', 18.00, 30),
  ('emom-keyring', 'EMOM Keyring', 'keyring', 'Simple EMOM keyring.', 8.00, 40),
  ('black-tote-bag-custom-logo', 'Black Tote Bag with Custom Logo Stamp', 'tote_bag', 'Black tote bag with custom logo stamp.', 22.00, 50)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO merch_variants (merch_item_id, variant_label, size, color, image_url)
SELECT mi.id, v.variant_label, v.size, v.color, v.image_url
FROM merch_items mi
JOIN (
  VALUES
    ('classic-logo-tee', 'S', 'S', NULL, '/assets/img/merch/classic-logo-tee.jpg'),
    ('classic-logo-tee', 'M', 'M', NULL, '/assets/img/merch/classic-logo-tee.jpg'),
    ('classic-logo-tee', 'L', 'L', NULL, '/assets/img/merch/classic-logo-tee.jpg'),
    ('classic-logo-tee', 'XL', 'XL', NULL, '/assets/img/merch/classic-logo-tee.jpg'),
    ('classic-logo-tee', 'XXL', 'XXL', NULL, '/assets/img/merch/classic-logo-tee.jpg'),
    ('glitch-logo-tee', 'S', 'S', NULL, '/assets/img/merch/glitch-logo-tee.jpg'),
    ('glitch-logo-tee', 'M', 'M', NULL, '/assets/img/merch/glitch-logo-tee.jpg'),
    ('glitch-logo-tee', 'L', 'L', NULL, '/assets/img/merch/glitch-logo-tee.jpg'),
    ('glitch-logo-tee', 'XL', 'XL', NULL, '/assets/img/merch/glitch-logo-tee.jpg'),
    ('glitch-logo-tee', 'XXL', 'XXL', NULL, '/assets/img/merch/glitch-logo-tee.jpg'),
    ('emom-mug', 'Black', NULL, 'black', '/assets/img/merch/emom-mug-black.jpg'),
    ('emom-mug', 'White', NULL, 'white', '/assets/img/merch/emom-mug-white.jpg'),
    ('emom-keyring', 'Standard', NULL, NULL, '/assets/img/merch/emom-keyring.jpg'),
    ('black-tote-bag-custom-logo', 'Standard', NULL, 'black', '/assets/img/merch/black-tote-bag-custom-logo.jpg')
) AS v(item_slug, variant_label, size, color, image_url)
  ON v.item_slug = mi.slug
ON CONFLICT (merch_item_id, variant_label) DO NOTHING;

COMMIT;
