import pg from "pg";

const { Client } = pg;

function slugify(value) {
  return String(value)
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function dateValue(dateText) {
  const parsed = new Date(dateText);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function uniqueNonEmpty(values) {
  const seen = new Set();
  const output = [];

  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    output.push(value);
  }

  return output;
}

function normalizeOptionalText(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function formatLegacyEventDate(input) {
  if (!input) return "";

  const date = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(date.getTime())) {
    return String(input);
  }

  const weekday = new Intl.DateTimeFormat("en-AU", { weekday: "short", timeZone: "UTC" }).format(date);
  const day = new Intl.DateTimeFormat("en-AU", { day: "numeric", timeZone: "UTC" }).format(date);
  const month = new Intl.DateTimeFormat("en-AU", { month: "short", timeZone: "UTC" }).format(date);
  const year = new Intl.DateTimeFormat("en-AU", { year: "numeric", timeZone: "UTC" }).format(date);
  return `${weekday}, ${day} ${month} ${year}`;
}

function buildNormalizedData({
  artists,
  artistimages,
  artistsocialprofiles,
  events,
  eventtypes,
  performances,
  socialplatforms,
}) {
  const normalizedEvents = events.map((event) => ({
    ...event,
    Date: normalizeOptionalText(event.Date) || formatLegacyEventDate(event.event_date),
    TypeID: event.TypeID ?? event.type_id,
    EventName: normalizeOptionalText(event.EventName ?? event.event_name),
    GalleryURL: normalizeOptionalText(event.GalleryURL ?? event.gallery_url),
  }));

  const artistsById = Object.fromEntries(artists.map((artist) => [artist.ID, artist]));
  const eventsById = Object.fromEntries(normalizedEvents.map((event) => [event.ID, event]));
  const socialPlatformsById = Object.fromEntries(
    socialplatforms.map((platform) => [platform.ID, platform])
  );
  const artistImagesByArtistId = Object.fromEntries(
    artistimages.map((image) => [image.artistID, image])
  );

  const performancesByArtistId = {};
  const performancesByEventId = {};
  for (const performance of performances) {
    if (!performancesByArtistId[performance.ArtistID]) {
      performancesByArtistId[performance.ArtistID] = [];
    }
    performancesByArtistId[performance.ArtistID].push(performance);

    if (!performancesByEventId[performance.EventID]) {
      performancesByEventId[performance.EventID] = [];
    }
    performancesByEventId[performance.EventID].push(performance);
  }

  const socialProfilesByArtistId = {};
  for (const profile of artistsocialprofiles) {
    if (!socialProfilesByArtistId[profile.artistID]) {
      socialProfilesByArtistId[profile.artistID] = [];
    }
    socialProfilesByArtistId[profile.artistID].push(profile);
  }

  const now = new Date();
  const currentYear = String(now.getFullYear());

  const artistPages = artists.map((artist) => {
    const artistPerformances = (performancesByArtistId[artist.ID] || [])
      .map((performance) => {
        const event = eventsById[performance.EventID];
        if (!event) return null;
        return {
          ...performance,
          event,
        };
      })
      .filter(Boolean)
      .sort((left, right) => {
        const leftDate = dateValue(left.event.Date);
        const rightDate = dateValue(right.event.Date);
        if (!leftDate || !rightDate) return 0;
        return rightDate.getTime() - leftDate.getTime();
      });

    const socialLinks = (socialProfilesByArtistId[artist.ID] || [])
      .map((profile) => {
        const platform = socialPlatformsById[profile.socialPlatformID];
        if (!platform || !profile.profileName) return null;
        return {
          ...profile,
          platform,
          platformName: platform.platformName,
          url: platform.URLFormat.replace("{profileName}", profile.profileName),
        };
      })
      .filter(Boolean);

    const image = artistImagesByArtistId[artist.ID] || null;
    const hasCurrentYearPerformance = artistPerformances.some(
      ({ event }) => event.Date && event.Date.includes(currentYear)
    );
    const hasPastPerformance = artistPerformances.some(({ event }) => {
      const eventDate = dateValue(event.Date);
      return eventDate && eventDate.getTime() <= now.getTime();
    });

    return {
      artist,
      slug: slugify(artist.stageName),
      image,
      socialLinks,
      performances: artistPerformances,
      hasCurrentYearPerformance,
      hasPastPerformance,
    };
  });

  const artistPagesSorted = [...artistPages].sort((left, right) =>
    String(left.artist.stageName).localeCompare(String(right.artist.stageName))
  );

  const eventsWithArtists = normalizedEvents.map((event) => {
    const eventArtists = (performancesByEventId[event.ID] || [])
      .map((performance) => artistsById[performance.ArtistID])
      .filter(Boolean)
      .sort((left, right) => String(left.stageName).localeCompare(String(right.stageName)));

    return {
      ...event,
      artists: eventArtists,
    };
  });

  const eventsByGalleryUrl = Object.fromEntries(
    eventsWithArtists
      .filter((event) => event.GalleryURL)
      .map((event) => [event.GalleryURL, event])
  );

  const galleries = uniqueNonEmpty(normalizedEvents.map((event) => event.GalleryURL));

  return {
    artists,
    artistimages,
    artistsocialprofiles,
    events: normalizedEvents,
    eventtypes,
    performances,
    socialplatforms,
    artistPages,
    artistPagesSorted,
    currentYear,
    galleries,
    eventsByGalleryUrl,
  };
}

function getPostgresConfig() {
  if (process.env.DATABASE_URL) {
    return {
      connectionString: process.env.DATABASE_URL,
    };
  }

  return {
    host: process.env.PGHOST || "127.0.0.1",
    port: Number.parseInt(process.env.PGPORT || "15432", 10),
    database: process.env.PGDATABASE || "emomweb",
    user: process.env.PGUSER,
    password: process.env.PGPASSWORD,
  };
}

async function loadFromPostgres() {
  const client = new Client(getPostgresConfig());
  await client.connect();

  try {
    const artistsResult = await client.query(`
      SELECT
        id AS "ID",
        stage_name AS "stageName"
      FROM artists
      ORDER BY id
    `);
    const artistImagesResult = await client.query(`
      SELECT
        id AS "ID",
        artist_id AS "artistID",
        image_url AS "imageURL"
      FROM artist_images
      ORDER BY id
    `);
    const artistSocialProfilesResult = await client.query(`
      SELECT
        id AS "ID",
        artist_id AS "artistID",
        social_platform_id AS "socialPlatformID",
        profile_name AS "profileName"
      FROM artist_social_profiles
      ORDER BY id
    `);
    const eventsResult = await client.query(`
      SELECT
        id AS "ID",
        legacy_date_text AS "Date",
        type_id AS "TypeID",
        event_name AS "EventName",
        NULLIF(BTRIM(gallery_url), '') AS "GalleryURL",
        event_date
      FROM events
      ORDER BY event_date, id
    `);
    const eventTypesResult = await client.query(`
      SELECT
        id AS "ID",
        description AS "Description"
      FROM event_types
      ORDER BY id
    `);
    const performancesResult = await client.query(`
      SELECT
        id AS "ID",
        event_id AS "EventID",
        artist_id AS "ArtistID"
      FROM performances
      ORDER BY id
    `);
    const socialPlatformsResult = await client.query(`
      SELECT
        id AS "ID",
        platform_name AS "platformName",
        url_format AS "URLFormat"
      FROM social_platforms
      ORDER BY id
    `);

    return buildNormalizedData({
      artists: artistsResult.rows,
      artistimages: artistImagesResult.rows,
      artistsocialprofiles: artistSocialProfilesResult.rows,
      events: eventsResult.rows,
      eventtypes: eventTypesResult.rows,
      performances: performancesResult.rows,
      socialplatforms: socialPlatformsResult.rows,
    });
  } finally {
    await client.end();
  }
}

export async function loadEmomData() {
  return loadFromPostgres();
}
