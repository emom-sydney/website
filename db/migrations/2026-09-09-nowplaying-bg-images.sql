BEGIN;

INSERT INTO app_settings (key, value_json)
VALUES (
  'nowplaying_bg_images',
  '["https://media.emom.me/assets/nowplaying/bg/image.jpg", "https://media.emom.me/assets/nowplaying/bg/image.mp4"]'::jsonb
)
ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json;

COMMIT;
