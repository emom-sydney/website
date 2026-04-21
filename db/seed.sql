-- Seed data for local development
-- This is applied after db/schema-sqlite.sql which creates/drops tables
-- Usage: npm run db:seed

PRAGMA foreign_keys = OFF;

-- Event Types
INSERT INTO event_types (id, description) VALUES
(1, 'Show'),
(2, 'Workshop'),
(3, 'Open Mic');

-- Social Platforms
INSERT INTO social_platforms (id, platform_name, url_format) VALUES
(1, 'Instagram', 'https://instagram.com/{profileName}'),
(2, 'Bandcamp', 'https://{profileName}.bandcamp.com'),
(3, 'SoundCloud', 'https://soundcloud.com/{profileName}'),
(4, 'YouTube', 'https://youtube.com/@{profileName}'),
(5, 'Website', '{profileName}'),
(6, 'Facebook', 'https://facebook.com/{profileName}'),
(7, 'Spotify', 'https://open.spotify.com/artist/{profileName}'),
(8, 'TikTok', 'https://tiktok.com/@{profileName}'),
(9, 'Threads', 'https://threads.net/@{profileName}'),
(10, 'Mastodon', 'https://{profileName}');

-- Profiles (Artists)
INSERT INTO profiles (id, profile_type, display_name, first_name, last_name, email, is_email_public, is_name_public) VALUES
(1, 'person', 'Alex Rivers', 'Alex', 'Rivers', 'alex@example.com', 1, 1),
(2, 'person', 'The Midnight Collective', NULL, NULL, 'midnight@example.com', 0, 0),
(3, 'person', 'Sarah Chen', 'Sarah', 'Chen', NULL, 0, 1),
(4, 'person', 'DJ Pulse', NULL, NULL, 'pulse@example.com', 1, 0),
(5, 'group', 'Neon Drift', NULL, NULL, NULL, 0, 0),
(6, 'person', 'Marcus Webb', 'Marcus', 'Webb', 'marcus@example.com', 1, 1),
(7, 'person', 'Luna Echo', 'Luna', 'Echo', NULL, 0, 1),
(8, 'person', 'Circuit Breaker', NULL, NULL, 'circuit@example.com', 1, 0),
(9, 'person', 'Yuki Tanaka', 'Yuki', 'Tanaka', NULL, 0, 1),
(10, 'person', 'Bass Heavy', NULL, NULL, 'bass@example.com', 0, 0);

-- Profile Roles (Artists)
INSERT INTO profile_roles (profile_id, role, bio, is_bio_public) VALUES
(1, 'artist', 'Singer-songwriter blending folk and electronic textures. Based in Sydney.', 1),
(2, 'artist', 'Ambient drone collective exploring deep listening experiences.', 1),
(3, 'artist', 'Classically trained pianist turned electronic producer.', 1),
(4, 'artist', 'Underground techno DJ with 10+ years experience.', 0),
(5, 'artist', 'Five-piece psychedelic rock band. Formed in 2023.', 1),
(6, 'artist', 'Jazz guitarist and composer. Regular performer at local venues.', 1),
(7, 'artist', 'Dream pop vocalist and synth player.', 1),
(8, 'artist', 'Industrial noise artist and visual performer.', 0),
(9, 'artist', 'Experimental electronic musician from Tokyo, now based in Sydney.', 1),
(10, 'artist', 'Bass music producer and sound system operator.', 1);

-- Profiles (Volunteers/Crew)
INSERT INTO profiles (id, profile_type, display_name, first_name, last_name, email, is_email_public, is_name_public) VALUES
(11, 'person', 'Jordan Smith', 'Jordan', 'Smith', 'jordan@example.com', 1, 1),
(12, 'person', 'Sam Taylor', 'Sam', 'Taylor', NULL, 0, 1),
(13, 'person', 'Casey Lee', 'Casey', 'Lee', 'casey@example.com', 1, 0),
(14, 'person', 'Riley Park', 'Riley', 'Park', NULL, 0, 0),
(15, 'person', 'Avery Johnson', 'Avery', 'Johnson', 'avery@example.com', 1, 1);

-- Profile Roles (Volunteers)
INSERT INTO profile_roles (profile_id, role, bio, is_bio_public) VALUES
(11, 'volunteer', 'Sound engineer and stage hand. Here to help!', 1),
(12, 'volunteer', 'Photography and social media.', 1),
(13, 'volunteer', 'Front of house and event coordination.', 0),
(14, 'volunteer', 'Lighting designer and visual tech.', 1),
(15, 'volunteer', 'Merch table and artist liaison.', 1);

-- Cross-role: Jordan is both crew and artist
INSERT INTO profile_roles (profile_id, role, bio, is_bio_public) VALUES
(11, 'artist', 'Multi-instrumentalist and sound designer.', 1);

-- Events
INSERT INTO events (id, event_date, type_id, event_name, gallery_url, youtube_embed_url) VALUES
(1, '2024-03-15', 1, 'EMOM March 2024', '2024-03', NULL),
(2, '2024-04-19', 1, 'EMOM April 2024', '2024-04', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
(3, '2024-05-17', 1, 'EMOM May 2024', '2024-05', NULL),
(4, '2024-06-21', 1, 'EMOM June 2024', '2024-06', NULL),
(5, '2024-07-19', 1, 'EMOM July 2024', '2024-07', NULL),
(6, '2024-08-16', 1, 'EMOM August 2024', '2024-08', 'https://youtu.be/abc123def45'),
(7, '2024-09-20', 1, 'EMOM September 2024', '2024-09', NULL),
(8, '2024-10-18', 1, 'EMOM October 2024', '2024-10', NULL),
(9, '2024-11-15', 1, 'EMOM November 2024', '2024-11', NULL),
(10, '2024-12-20', 1, 'EMOM December 2024', '2024-12', NULL),
(11, '2025-01-17', 1, 'EMOM January 2025', '2025-01', NULL),
(12, '2025-02-21', 1, 'EMOM February 2025', '2025-02', NULL),
(13, '2025-03-21', 1, 'EMOM March 2025', '2025-03', NULL),
(14, '2025-04-18', 1, 'EMOM April 2025', '2025-04', NULL),
(15, '2025-05-16', 1, 'EMOM May 2025', '2025-05', NULL),
(16, '2024-06-22', 2, 'Synthesis Workshop', NULL, NULL),
(17, '2024-08-17', 3, 'Summer Open Mic', NULL, NULL);

-- Performances
INSERT INTO performances (id, event_id, profile_id) VALUES
-- March 2024
(1, 1, 1),
(2, 1, 3),
(3, 1, 5),
-- April 2024
(4, 2, 2),
(5, 2, 4),
(6, 2, 6),
-- May 2024
(7, 3, 1),
(8, 3, 7),
(9, 3, 9),
-- June 2024
(10, 4, 3),
(11, 4, 5),
(12, 4, 8),
(13, 4, 10),
-- July 2024
(14, 5, 2),
(15, 5, 4),
(16, 5, 6),
(17, 5, 11),
-- August 2024
(18, 6, 1),
(19, 6, 7),
(20, 6, 9),
-- September 2024
(21, 7, 3),
(22, 7, 5),
(23, 7, 8),
-- October 2024
(24, 8, 2),
(25, 8, 4),
(26, 8, 6),
(27, 8, 10),
-- November 2024
(28, 9, 1),
(29, 9, 7),
(30, 9, 9),
-- December 2024
(31, 10, 3),
(32, 10, 5),
(33, 10, 8),
-- January 2025
(34, 11, 2),
(35, 11, 4),
(36, 11, 6),
(37, 11, 11),
-- February 2025
(38, 12, 1),
(39, 12, 7),
(40, 12, 9),
(41, 12, 10),
-- March 2025
(42, 13, 3),
(43, 13, 5),
(44, 13, 8),
-- April 2025
(45, 14, 2),
(46, 14, 4),
(47, 14, 6),
(48, 14, 11),
-- May 2025
(49, 15, 1),
(50, 15, 7),
(51, 15, 9),
(52, 15, 10),
-- Workshop
(53, 16, 6),
(54, 16, 9),
-- Open Mic
(55, 17, 1),
(56, 17, 3),
(57, 17, 7);

-- Profile Images
INSERT INTO profile_images (id, profile_id, image_url) VALUES
(1, 1, 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400'),
(2, 2, 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400'),
(3, 3, 'https://images.unsplash.com/photo-1525210353037-d7e124d12be6?w=400'),
(4, 5, 'https://images.unsplash.com/photo-1514320291840-2e0a9bf2a9ae?w=400'),
(5, 6, 'https://images.unsplash.com/photo-1510915361894-db8b60106cb1?w=400'),
(6, 7, 'https://images.unsplash.com/photo-1516280440614-6697288d5d38?w=400'),
(7, 9, 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=400'),
(8, 11, 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400'),
(9, 12, 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400'),
(10, 14, 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400');

-- Social Profiles
INSERT INTO profile_social_profiles (id, profile_id, social_platform_id, profile_name) VALUES
(1, 1, 1, 'alexriversmusic'),
(2, 1, 2, 'alexrivers'),
(3, 1, 4, 'AlexRiversMusic'),
(4, 2, 1, 'midnightcollective'),
(5, 2, 2, 'midnightcollective'),
(6, 3, 1, 'sarahchenmusic'),
(7, 3, 3, 'sarah-chen'),
(8, 4, 1, 'djpulseau'),
(9, 4, 3, 'dj-pulse'),
(10, 5, 1, 'neondriftband'),
(11, 5, 2, 'neondrift'),
(12, 6, 1, 'marcuswebbjazz'),
(13, 6, 5, 'https://marcuswebb.com'),
(14, 7, 1, 'lunaechomusic'),
(15, 7, 4, 'LunaEchoOfficial'),
(16, 8, 1, 'circuitbreakernoize'),
(17, 9, 1, 'yukitanakamusic'),
(18, 9, 2, 'yukitanaka'),
(19, 10, 1, 'bassheavyau'),
(20, 10, 3, 'bass-heavy'),
(21, 11, 1, 'jordansmithaudio'),
(22, 12, 1, 'samtaylorphoto'),
(23, 13, 1, 'caseyleeevents'),
(24, 14, 1, 'rileylighting'),
(25, 15, 1, 'averyjohnsonmerch');

-- Merch Items
INSERT INTO merch_items (id, slug, name, category, description, suggested_price, is_active, sort_order) VALUES
(1, 'emom-tshirt-2024', 'EMOM 2024 T-Shirt', 'tshirt', 'Limited edition tee featuring the 2024 lineup artwork.', 35.00, 1, 1),
(2, 'emom-tote', 'EMOM Tote Bag', 'tote_bag', 'Sturdy canvas tote with screen-printed logo.', 20.00, 1, 2),
(3, 'emom-mug', 'EMOM Ceramic Mug', 'mug', 'Ceramic mug with matte black finish.', 15.00, 1, 3),
(4, 'emom-keyring', 'EMOM Keyring', 'keyring', 'Metal keyring with enamel logo.', 8.00, 1, 4),
(5, 'emom-tank', 'EMOM Tank Top', 'tshirt', 'Unisex tank for those hot Sydney nights.', 30.00, 1, 5);

-- Merch Variants
INSERT INTO merch_variants (id, merch_item_id, variant_label, style, size, color, image_url, is_active) VALUES
(1, 1, 'Unisex - S - Black', 'unisex', 'S', 'black', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(2, 1, 'Unisex - M - Black', 'unisex', 'M', 'black', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(3, 1, 'Unisex - L - Black', 'unisex', 'L', 'black', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(4, 1, 'Unisex - XL - Black', 'unisex', 'XL', 'black', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(5, 1, 'Unisex - S - White', 'unisex', 'S', 'white', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(6, 1, 'Unisex - M - White', 'unisex', 'M', 'white', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(7, 1, 'Unisex - L - White', 'unisex', 'L', 'white', 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400', 1),
(8, 2, 'Standard', NULL, NULL, NULL, 'https://images.unsplash.com/photo-1597484662317-c925cc6dba16?w=400', 1),
(9, 3, 'Standard', NULL, NULL, 'black', 'https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=400', 1),
(10, 4, 'Standard', NULL, NULL, NULL, 'https://images.unsplash.com/photo-1586103048517-26782c536672?w=400', 1),
(11, 5, 'Unisex - S', 'unisex', 'S', 'black', 'https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=400', 1),
(12, 5, 'Unisex - M', 'unisex', 'M', 'black', 'https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=400', 1),
(13, 5, 'Unisex - L', 'unisex', 'L', 'black', 'https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=400', 1);

PRAGMA foreign_keys = ON;
