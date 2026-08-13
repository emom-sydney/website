ALTER TABLE performances
ADD COLUMN IF NOT EXISTS checked_in_at timestamptz;
