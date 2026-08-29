BEGIN;

INSERT INTO app_settings (key, value_json)
VALUES
  ('now_playing_banner_text', '"Welcome to EMOM Sydney/Eora"'::jsonb),
  ('now_playing_banner_logo_url', '"/assets/img/site_logo.png"'::jsonb),
  ('global_site_logo_url', '"/assets/img/site_logo.png"'::jsonb),
  ('now_playing_banner_display_time_secs', '30'::jsonb),
  ('now_playing_banner_display_interval_secs', '300'::jsonb),
  ('now_playing_banner_display_delay_secs', '60'::jsonb),
  ('now_playing_jukebox_url', 'null'::jsonb)
ON CONFLICT (key) DO NOTHING;

COMMIT;
