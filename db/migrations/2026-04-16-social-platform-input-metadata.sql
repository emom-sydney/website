BEGIN;

ALTER TABLE social_platforms
  ADD COLUMN IF NOT EXISTS input_label text,
  ADD COLUMN IF NOT EXISTS input_placeholder text,
  ADD COLUMN IF NOT EXISTS input_help text;

UPDATE social_platforms
SET
  input_label = CASE platform_name
    WHEN 'Instagram' THEN 'Instagram handle'
    WHEN 'Facebook' THEN 'Facebook profile name'
    WHEN 'Soundcloud' THEN 'Soundcloud profile name'
    WHEN 'Bandcamp' THEN 'Bandcamp subdomain'
    WHEN 'Youtube' THEN 'YouTube channel handle'
    WHEN 'Linktree' THEN 'Linktree handle'
    WHEN 'Website' THEN 'Website URL'
    WHEN 'Github' THEN 'GitHub username'
    WHEN 'X' THEN 'X handle'
    WHEN 'Tiktok' THEN 'TikTok username'
    WHEN 'Bluesky' THEN 'Bluesky handle'
    WHEN 'Mastodon' THEN 'Mastodon address'
    WHEN 'Spotify' THEN 'Spotify artist ID'
    WHEN 'WeeklyBeats' THEN 'WeeklyBeats username'
    WHEN 'Twitch.tv' THEN 'Twitch username'
    ELSE input_label
  END,
  input_placeholder = CASE platform_name
    WHEN 'Instagram' THEN 'yourname'
    WHEN 'Facebook' THEN 'your.profile'
    WHEN 'Soundcloud' THEN 'yourname'
    WHEN 'Bandcamp' THEN 'yourname'
    WHEN 'Youtube' THEN 'yourhandle'
    WHEN 'Linktree' THEN 'yourname'
    WHEN 'Website' THEN 'https://example.com'
    WHEN 'Github' THEN 'yourname'
    WHEN 'X' THEN 'yourname'
    WHEN 'Tiktok' THEN 'yourname'
    WHEN 'Bluesky' THEN 'you.bsky.social'
    WHEN 'Mastodon' THEN '@you@instance.social'
    WHEN 'Spotify' THEN 'artist_id'
    WHEN 'WeeklyBeats' THEN 'yourname'
    WHEN 'Twitch.tv' THEN 'yourname'
    ELSE input_placeholder
  END,
  input_help = CASE platform_name
    WHEN 'Bandcamp' THEN 'Enter only the subdomain part before .bandcamp.com.'
    WHEN 'Website' THEN 'Enter your full website URL, including https:// where possible.'
    WHEN 'Mastodon' THEN 'Use your full handle, usually in the form @name@server.'
    WHEN 'Spotify' THEN 'Enter the artist ID from your Spotify artist profile URL.'
    ELSE input_help
  END;

COMMIT;
