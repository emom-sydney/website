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

function parseEventDate(value) {
  if (!value) return null;

  if (value instanceof Date) {
    return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()));
  }

  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match) {
    const [, year, month, day] = match;
    return new Date(Date.UTC(Number.parseInt(year, 10), Number.parseInt(month, 10) - 1, Number.parseInt(day, 10)));
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function compareEventDates(leftEvent, rightEvent) {
  const leftDate = leftEvent?.eventDate;
  const rightDate = rightEvent?.eventDate;

  if (!leftDate && !rightDate) return 0;
  if (!leftDate) return 1;
  if (!rightDate) return -1;

  const byDate = leftDate.getTime() - rightDate.getTime();
  if (byDate !== 0) return byDate;

  return String(leftEvent?.EventName ?? "").localeCompare(String(rightEvent?.EventName ?? ""));
}

function buildNormalizedData({
  artists,
  artistimages,
  artistsocialprofiles,
  events,
  eventtypes,
  performances,
  socialplatforms,
  artistPagesInput,
  galleryEventsInput,
}) {
  const normalizedEvents = events.map((event) => ({
    ...event,
    TypeID: event.TypeID ?? event.type_id,
    EventName: event.EventName ?? event.event_name,
    GalleryURL: event.GalleryURL ?? event.gallery_url ?? null,
    eventDate: parseEventDate(event.event_date),
  }));

  const now = new Date();
  const currentYear = String(now.getFullYear());

  const artistPages = artistPagesInput.map((artistPage) => {
    const artistPerformances = [...artistPage.performances].sort((left, right) =>
      compareEventDates(left.event, right.event)
    );

    const hasCurrentYearPerformance = artistPerformances.some(
      ({ event }) => event.eventDate && String(event.eventDate.getUTCFullYear()) === currentYear
    );
    const hasPastPerformance = artistPerformances.some(({ event }) => {
      const eventDate = event.eventDate;
      return eventDate && eventDate.getTime() <= now.getTime();
    });

    return {
      artist: artistPage.artist,
      slug: slugify(artistPage.artist.stageName),
      image: artistPage.image,
      socialLinks: artistPage.socialLinks,
      performances: artistPerformances,
      hasCurrentYearPerformance,
      hasPastPerformance,
    };
  });

  const artistPagesSorted = [...artistPages].sort((left, right) =>
    String(left.artist.stageName).localeCompare(String(right.artist.stageName))
  );

  const eventsByGalleryUrl = Object.fromEntries(
    galleryEventsInput
      .filter((event) => event.GalleryURL)
      .map((event) => [event.GalleryURL, event])
  );

  const galleries = galleryEventsInput
    .filter((event) => event.GalleryURL)
    .map((event) => event.GalleryURL);

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
    const artistPagesResult = await client.query(`
      SELECT
        a.id AS artist_id,
        a.stage_name AS artist_stage_name,
        ai.id AS image_id,
        ai.image_url,
        asp.id AS social_profile_id,
        asp.profile_name,
        sp.id AS social_platform_id,
        sp.platform_name,
        sp.url_format,
        p.id AS performance_id,
        e.id AS event_id,
        e.type_id,
        e.event_name,
        NULLIF(BTRIM(e.gallery_url), '') AS gallery_url,
        e.event_date
      FROM artists a
      LEFT JOIN artist_images ai
        ON ai.artist_id = a.id
      LEFT JOIN artist_social_profiles asp
        ON asp.artist_id = a.id
      LEFT JOIN social_platforms sp
        ON sp.id = asp.social_platform_id
      LEFT JOIN performances p
        ON p.artist_id = a.id
      LEFT JOIN events e
        ON e.id = p.event_id
      ORDER BY a.id, p.id, asp.id, ai.id
    `);

    const artistPagesByArtistId = new Map();
    for (const row of artistPagesResult.rows) {
      let artistPage = artistPagesByArtistId.get(row.artist_id);

      if (!artistPage) {
        artistPage = {
          artist: {
            ID: row.artist_id,
            stageName: row.artist_stage_name,
          },
          image: row.image_id ? {
            ID: row.image_id,
            artistID: row.artist_id,
            imageURL: row.image_url,
          } : null,
          socialLinks: [],
          performances: [],
        };
        artistPagesByArtistId.set(row.artist_id, artistPage);
      }

      if (!artistPage.image && row.image_id) {
        artistPage.image = {
          ID: row.image_id,
          artistID: row.artist_id,
          imageURL: row.image_url,
        };
      }

      if (row.social_profile_id) {
        const socialKey = `${row.social_profile_id}`;
        if (!artistPage.socialLinks.some((socialLink) => `${socialLink.ID}` === socialKey)) {
          artistPage.socialLinks.push({
            ID: row.social_profile_id,
            artistID: row.artist_id,
            socialPlatformID: row.social_platform_id,
            profileName: row.profile_name,
            platform: {
              ID: row.social_platform_id,
              platformName: row.platform_name,
              URLFormat: row.url_format,
            },
            platformName: row.platform_name,
            url: row.url_format.replace("{profileName}", row.profile_name),
          });
        }
      }

      if (row.performance_id) {
        const performanceKey = `${row.performance_id}`;
        if (!artistPage.performances.some((performance) => `${performance.ID}` === performanceKey)) {
          artistPage.performances.push({
            ID: row.performance_id,
            EventID: row.event_id,
            ArtistID: row.artist_id,
            event: {
              ID: row.event_id,
              TypeID: row.type_id,
              EventName: row.event_name,
              GalleryURL: row.gallery_url,
              eventDate: parseEventDate(row.event_date),
            },
          });
        }
      }
    }

    const galleryEventsResult = await client.query(`
      SELECT
        e.id AS event_id,
        e.type_id,
        e.event_name,
        NULLIF(BTRIM(e.gallery_url), '') AS gallery_url,
        e.event_date,
        a.id AS artist_id,
        a.stage_name
      FROM events e
      LEFT JOIN performances p
        ON p.event_id = e.id
      LEFT JOIN artists a
        ON a.id = p.artist_id
      WHERE NULLIF(BTRIM(e.gallery_url), '') IS NOT NULL
      ORDER BY e.event_date, e.id, a.stage_name
    `);

    const galleryEventsByUrl = new Map();
    for (const row of galleryEventsResult.rows) {
      let galleryEvent = galleryEventsByUrl.get(row.gallery_url);

      if (!galleryEvent) {
        galleryEvent = {
          ID: row.event_id,
          TypeID: row.type_id,
          EventName: row.event_name,
          GalleryURL: row.gallery_url,
          eventDate: parseEventDate(row.event_date),
          artists: [],
        };
        galleryEventsByUrl.set(row.gallery_url, galleryEvent);
      }

      if (row.artist_id && !galleryEvent.artists.some((artist) => artist.ID === row.artist_id)) {
        galleryEvent.artists.push({
          ID: row.artist_id,
          stageName: row.stage_name,
        });
      }
    }

    const galleryEventsInput = [...galleryEventsByUrl.values()].map((event) => ({
      ...event,
      artists: [...event.artists].sort((left, right) =>
        String(left.stageName).localeCompare(String(right.stageName))
      ),
    }));

    return buildNormalizedData({
      artists: artistsResult.rows,
      artistimages: artistImagesResult.rows,
      artistsocialprofiles: artistSocialProfilesResult.rows,
      events: eventsResult.rows,
      eventtypes: eventTypesResult.rows,
      performances: performancesResult.rows,
      socialplatforms: socialPlatformsResult.rows,
      artistPagesInput: artistsResult.rows.map((artist) =>
        artistPagesByArtistId.get(artist.ID) || {
          artist,
          image: null,
          socialLinks: [],
          performances: [],
        }
      ),
      galleryEventsInput,
    });
  } finally {
    await client.end();
  }
}

export async function loadEmomData() {
  return loadFromPostgres();
}
