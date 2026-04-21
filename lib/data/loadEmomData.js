import pg from "pg";
import Database from "better-sqlite3";

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

function uniqueNonEmpty(values) {
  return [...new Set(values.filter((value) => String(value || "").trim() !== ""))];
}

function buildRolePagesInput(rows, { includePerformances = false } = {}) {
  const pagesByProfileId = new Map();

  for (const row of rows) {
    let page = pagesByProfileId.get(row.profile_id);

    if (!page) {
      page = {
        profile: {
          ID: row.profile_id,
          stageName: row.profile_display_name,
          profileType: row.profile_type,
          firstName: row.first_name,
          lastName: row.last_name,
          bio: row.bio,
          email: row.email,
          isEmailPublic: row.is_email_public,
          isBioPublic: row.is_bio_public,
          isNamePublic: row.is_name_public,
        },
        image: row.image_id ? {
          ID: row.image_id,
          profileID: row.profile_id,
          imageURL: row.image_url,
        } : null,
        socialLinks: [],
        performances: [],
      };
      pagesByProfileId.set(row.profile_id, page);
    }

    if (!page.image && row.image_id) {
      page.image = {
        ID: row.image_id,
        profileID: row.profile_id,
        imageURL: row.image_url,
      };
    }

    if (row.social_profile_id) {
      const socialKey = `${row.social_profile_id}`;
      if (!page.socialLinks.some((socialLink) => `${socialLink.ID}` === socialKey)) {
        page.socialLinks.push({
          ID: row.social_profile_id,
          profileID: row.profile_id,
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

    if (includePerformances && row.performance_id) {
      const performanceKey = `${row.performance_id}`;
      if (!page.performances.some((performance) => `${performance.ID}` === performanceKey)) {
        page.performances.push({
          ID: row.performance_id,
          EventID: row.event_id,
          ProfileID: row.profile_id,
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

  return [...pagesByProfileId.values()];
}

function getRolePagesQuery(role, { includePerformances = false } = {}) {
  const performanceFields = includePerformances
    ? `
        perf.id AS performance_id,
        e.id AS event_id,
        e.type_id,
        e.event_name,
        NULLIF(TRIM(e.gallery_url), '') AS gallery_url,
        e.event_date
`
    : `
        CAST(NULL AS INTEGER) AS performance_id,
        CAST(NULL AS INTEGER) AS event_id,
        CAST(NULL AS INTEGER) AS type_id,
        CAST(NULL AS TEXT) AS event_name,
        CAST(NULL AS TEXT) AS gallery_url,
        CAST(NULL AS TEXT) AS event_date
`;

  const performanceJoins = includePerformances
    ? `
      LEFT JOIN performances perf
        ON perf.profile_id = prof.id
      LEFT JOIN events e
        ON e.id = perf.event_id
`
    : "";

  return `
      SELECT
        prof.id AS profile_id,
        prof.display_name AS profile_display_name,
        prof.profile_type,
        prof.first_name,
        prof.last_name,
        pr.bio,
        prof.email,
        prof.is_email_public,
        pr.is_bio_public,
        prof.is_name_public,
        ai.id AS image_id,
        ai.image_url,
        asp.id AS social_profile_id,
        asp.profile_name,
        sp.id AS social_platform_id,
        sp.platform_name,
        sp.url_format,
${performanceFields}
      FROM profiles prof
      JOIN profile_roles pr
        ON pr.profile_id = prof.id
       AND pr.role = '${role}'
      LEFT JOIN profile_images ai
        ON ai.profile_id = prof.id
      LEFT JOIN profile_social_profiles asp
        ON asp.profile_id = prof.id
      LEFT JOIN social_platforms sp
        ON sp.id = asp.social_platform_id
${performanceJoins}
      ORDER BY prof.id, performance_id, asp.id, ai.id
    `;
}

function buildNormalizedData({
  artists,
  artistimages,
  artistsocialprofiles,
  events,
  eventtypes,
  merchItemsInput,
  performances,
  socialplatforms,
  artistPagesInput,
  volunteerPagesInput,
  galleryEventsInput,
}) {
  const normalizedEvents = events.map((event) => ({
    ...event,
    TypeID: event.TypeID ?? event.type_id,
    EventName: event.EventName ?? event.event_name,
    GalleryURL: event.GalleryURL ?? event.gallery_url ?? null,
    YouTubeEmbedURL: event.YouTubeEmbedURL ?? event.youtube_embed_url ?? null,
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
      profile: artistPage.profile,
      artist: artistPage.profile,
      slug: slugify(artistPage.profile.stageName),
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

  const volunteerPagesByProfileId = new Map(
    volunteerPagesInput.map((volunteerPage) => [volunteerPage.profile.ID, volunteerPage])
  );

  for (const artistPage of artistPages) {
    const matchingVolunteerPage = volunteerPagesByProfileId.get(artistPage.profile.ID);
    artistPage.volunteerProfile = matchingVolunteerPage
      ? {
          slug: slugify(matchingVolunteerPage.profile.stageName),
          stageName: matchingVolunteerPage.profile.stageName,
        }
      : null;
  }

  const artistPagesByProfileId = new Map(
    artistPages.map((artistPage) => [artistPage.profile.ID, artistPage])
  );

  const volunteerPages = volunteerPagesInput.map((volunteerPage) => {
    const matchingArtistPage = artistPagesByProfileId.get(volunteerPage.profile.ID);

    return {
      profile: volunteerPage.profile,
      slug: slugify(volunteerPage.profile.stageName),
      image: volunteerPage.image,
      socialLinks: volunteerPage.socialLinks,
      artistProfile: matchingArtistPage
        ? {
            slug: matchingArtistPage.slug,
            stageName: matchingArtistPage.profile.stageName,
          }
        : null,
    };
  });

  const volunteerPagesSorted = [...volunteerPages].sort((left, right) =>
    String(left.profile.stageName).localeCompare(String(right.profile.stageName))
  );

  const eventsByGalleryUrl = Object.fromEntries(
    galleryEventsInput
      .filter((event) => event.GalleryURL)
      .map((event) => [event.GalleryURL, event])
  );

  const galleries = galleryEventsInput
    .filter((event) => event.GalleryURL)
    .map((event) => event.GalleryURL);

  const merchItems = merchItemsInput.map((item) => ({
    ...item,
    variants: [...item.variants].sort((left, right) => left.id - right.id),
  })).map((item) => {
    const styleOptions = uniqueNonEmpty(item.variants.map((variant) => variant.style));
    const sizeOptions = uniqueNonEmpty(
      item.variants.map((variant) => variant.size || variant.variantLabel)
    );
    const colorOptions = uniqueNonEmpty(item.variants.map((variant) => variant.color));

    return {
      ...item,
      styleOptions,
      sizeOptions,
      colorOptions:
        item.category === "tshirt" && colorOptions.length === 0
          ? ["black", "white"]
          : colorOptions,
    };
  });

  return {
    artists,
    artistimages,
    artistsocialprofiles,
    events: normalizedEvents,
    eventtypes,
    merchItems,
    performances,
    socialplatforms,
    artistPages,
    artistPagesSorted,
    volunteerPages,
    volunteerPagesSorted,
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
        p.id AS "ID",
        p.display_name AS "stageName",
        p.profile_type AS "profileType",
        p.first_name AS "firstName",
        p.last_name AS "lastName",
        pr.bio,
        p.email,
        p.is_email_public AS "isEmailPublic",
        pr.is_bio_public AS "isBioPublic",
        p.is_name_public AS "isNamePublic"
      FROM profiles p
      JOIN profile_roles pr
        ON pr.profile_id = p.id
       AND pr.role = 'artist'
      ORDER BY id
    `);
    const artistImagesResult = await client.query(`
      SELECT
        id AS "ID",
        profile_id AS "profileID",
        image_url AS "imageURL"
      FROM profile_images
      ORDER BY id
    `);
    const artistSocialProfilesResult = await client.query(`
      SELECT
        id AS "ID",
        profile_id AS "profileID",
        social_platform_id AS "socialPlatformID",
        profile_name AS "profileName"
      FROM profile_social_profiles
      ORDER BY id
    `);
    const eventsResult = await client.query(`
      SELECT
        id AS "ID",
        type_id AS "TypeID",
        event_name AS "EventName",
        NULLIF(TRIM(gallery_url), '') AS "GalleryURL",
        NULLIF(TRIM(youtube_embed_url), '') AS "YouTubeEmbedURL",
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
        profile_id AS "ProfileID"
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
    const merchItemsResult = await client.query(`
      SELECT
        mi.id AS merch_item_id,
        mi.slug,
        mi.name,
        mi.category,
        mi.description,
        mi.suggested_price,
        mi.sort_order,
        mv.id AS merch_variant_id,
        mv.variant_label,
        mv.style,
        mv.size,
        mv.color,
        mv.image_url
      FROM merch_items mi
      LEFT JOIN merch_variants mv
        ON mv.merch_item_id = mi.id
       AND mv.is_active = true
      WHERE mi.is_active = true
      ORDER BY mi.sort_order, mi.id, mv.id
    `);
    const artistPagesResult = await client.query(getRolePagesQuery("artist", { includePerformances: true }));
    const volunteerPagesResult = await client.query(getRolePagesQuery("volunteer"));

    const galleryEventsResult = await client.query(`
      SELECT
        e.id AS event_id,
        e.type_id,
        e.event_name,
        NULLIF(TRIM(e.gallery_url), '') AS gallery_url,
        NULLIF(TRIM(e.youtube_embed_url), '') AS youtube_embed_url,
        e.event_date,
        p.id AS profile_id,
        p.display_name
      FROM events e
      LEFT JOIN performances perf
        ON perf.event_id = e.id
      LEFT JOIN profiles p
        ON p.id = perf.profile_id
      WHERE NULLIF(TRIM(e.gallery_url), '') IS NOT NULL
      ORDER BY e.event_date, e.id, p.display_name
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
          YouTubeEmbedURL: row.youtube_embed_url,
          eventDate: parseEventDate(row.event_date),
          artists: [],
        };
        galleryEventsByUrl.set(row.gallery_url, galleryEvent);
      }

      if (row.profile_id && !galleryEvent.artists.some((artist) => artist.ID === row.profile_id)) {
        galleryEvent.artists.push({
          ID: row.profile_id,
          stageName: row.display_name,
        });
      }
    }

    const galleryEventsInput = [...galleryEventsByUrl.values()].map((event) => ({
      ...event,
      artists: [...event.artists].sort((left, right) =>
        String(left.stageName).localeCompare(String(right.stageName))
      ),
    }));

    const merchItemsById = new Map();
    for (const row of merchItemsResult.rows) {
      let merchItem = merchItemsById.get(row.merch_item_id);

      if (!merchItem) {
        merchItem = {
          id: row.merch_item_id,
          slug: row.slug,
          name: row.name,
          category: row.category,
          description: row.description,
          suggestedPrice: row.suggested_price,
          sortOrder: row.sort_order,
          variants: [],
        };
        merchItemsById.set(row.merch_item_id, merchItem);
      }

      if (row.merch_variant_id) {
        merchItem.variants.push({
          id: row.merch_variant_id,
          variantLabel: row.variant_label,
          style: row.style,
          size: row.size,
          color: row.color,
          imageURL: row.image_url,
        });
      }
    }

    return buildNormalizedData({
      artists: artistsResult.rows,
      artistimages: artistImagesResult.rows,
      artistsocialprofiles: artistSocialProfilesResult.rows,
      events: eventsResult.rows,
      eventtypes: eventTypesResult.rows,
      merchItemsInput: [...merchItemsById.values()],
      performances: performancesResult.rows,
      socialplatforms: socialPlatformsResult.rows,
      artistPagesInput: buildRolePagesInput(artistPagesResult.rows, { includePerformances: true }),
      volunteerPagesInput: buildRolePagesInput(volunteerPagesResult.rows),
      galleryEventsInput,
    });
  } finally {
    await client.end();
  }
}

function loadFromSQLite() {
  const dbPath = process.env.SQLITE_PATH || "emom.local.sqlite";
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");

  try {
    const artistsResult = db.prepare(`
      SELECT
        p.id AS ID,
        p.display_name AS stageName,
        p.profile_type AS profileType,
        p.first_name AS firstName,
        p.last_name AS lastName,
        pr.bio,
        p.email,
        p.is_email_public AS isEmailPublic,
        pr.is_bio_public AS isBioPublic,
        p.is_name_public AS isNamePublic
      FROM profiles p
      JOIN profile_roles pr
        ON pr.profile_id = p.id
       AND pr.role = 'artist'
      ORDER BY id
    `).all();

    const artistImagesResult = db.prepare(`
      SELECT
        id AS ID,
        profile_id AS profileID,
        image_url AS imageURL
      FROM profile_images
      ORDER BY id
    `).all();

    const artistSocialProfilesResult = db.prepare(`
      SELECT
        id AS ID,
        profile_id AS profileID,
        social_platform_id AS socialPlatformID,
        profile_name AS profileName
      FROM profile_social_profiles
      ORDER BY id
    `).all();

    const eventsResult = db.prepare(`
      SELECT
        id AS ID,
        type_id AS TypeID,
        event_name AS EventName,
        NULLIF(TRIM(gallery_url), '') AS GalleryURL,
        NULLIF(TRIM(youtube_embed_url), '') AS YouTubeEmbedURL,
        event_date
      FROM events
      ORDER BY event_date, id
    `).all();

    const eventTypesResult = db.prepare(`
      SELECT
        id AS ID,
        description AS Description
      FROM event_types
      ORDER BY id
    `).all();

    const performancesResult = db.prepare(`
      SELECT
        id AS ID,
        event_id AS EventID,
        profile_id AS ProfileID
      FROM performances
      ORDER BY id
    `).all();

    const socialPlatformsResult = db.prepare(`
      SELECT
        id AS ID,
        platform_name AS platformName,
        url_format AS URLFormat
      FROM social_platforms
      ORDER BY id
    `).all();

    const merchItemsResult = db.prepare(`
      SELECT
        mi.id AS merch_item_id,
        mi.slug,
        mi.name,
        mi.category,
        mi.description,
        mi.suggested_price,
        mi.sort_order,
        mv.id AS merch_variant_id,
        mv.variant_label,
        mv.style,
        mv.size,
        mv.color,
        mv.image_url
      FROM merch_items mi
      LEFT JOIN merch_variants mv
        ON mv.merch_item_id = mi.id
       AND mv.is_active = 1
      WHERE mi.is_active = 1
      ORDER BY mi.sort_order, mi.id, mv.id
    `).all();

    const artistPagesResult = db.prepare(getRolePagesQuery("artist", { includePerformances: true })).all();
    const volunteerPagesResult = db.prepare(getRolePagesQuery("volunteer")).all();

    const galleryEventsResult = db.prepare(`
      SELECT
        e.id AS event_id,
        e.type_id,
        e.event_name,
        NULLIF(TRIM(e.gallery_url), '') AS gallery_url,
        NULLIF(TRIM(e.youtube_embed_url), '') AS youtube_embed_url,
        e.event_date,
        p.id AS profile_id,
        p.display_name
      FROM events e
      LEFT JOIN performances perf
        ON perf.event_id = e.id
      LEFT JOIN profiles p
        ON p.id = perf.profile_id
      WHERE NULLIF(TRIM(e.gallery_url), '') IS NOT NULL
      ORDER BY e.event_date, e.id, p.display_name
    `).all();

    const galleryEventsByUrl = new Map();
    for (const row of galleryEventsResult) {
      let galleryEvent = galleryEventsByUrl.get(row.gallery_url);

      if (!galleryEvent) {
        galleryEvent = {
          ID: row.event_id,
          TypeID: row.type_id,
          EventName: row.event_name,
          GalleryURL: row.gallery_url,
          YouTubeEmbedURL: row.youtube_embed_url,
          eventDate: parseEventDate(row.event_date),
          artists: [],
        };
        galleryEventsByUrl.set(row.gallery_url, galleryEvent);
      }

      if (row.profile_id && !galleryEvent.artists.some((artist) => artist.ID === row.profile_id)) {
        galleryEvent.artists.push({
          ID: row.profile_id,
          stageName: row.display_name,
        });
      }
    }

    const galleryEventsInput = [...galleryEventsByUrl.values()].map((event) => ({
      ...event,
      artists: [...event.artists].sort((left, right) =>
        String(left.stageName).localeCompare(String(right.stageName))
      ),
    }));

    const merchItemsById = new Map();
    for (const row of merchItemsResult) {
      let merchItem = merchItemsById.get(row.merch_item_id);

      if (!merchItem) {
        merchItem = {
          id: row.merch_item_id,
          slug: row.slug,
          name: row.name,
          category: row.category,
          description: row.description,
          suggestedPrice: row.suggested_price,
          sortOrder: row.sort_order,
          variants: [],
        };
        merchItemsById.set(row.merch_item_id, merchItem);
      }

      if (row.merch_variant_id) {
        merchItem.variants.push({
          id: row.merch_variant_id,
          variantLabel: row.variant_label,
          style: row.style,
          size: row.size,
          color: row.color,
          imageURL: row.image_url,
        });
      }
    }

    return buildNormalizedData({
      artists: artistsResult,
      artistimages: artistImagesResult,
      artistsocialprofiles: artistSocialProfilesResult,
      events: eventsResult,
      eventtypes: eventTypesResult,
      merchItemsInput: [...merchItemsById.values()],
      performances: performancesResult,
      socialplatforms: socialPlatformsResult,
      artistPagesInput: buildRolePagesInput(artistPagesResult, { includePerformances: true }),
      volunteerPagesInput: buildRolePagesInput(volunteerPagesResult),
      galleryEventsInput,
    });
  } finally {
    db.close();
  }
}

export async function loadEmomData() {
  if (process.env.USE_SQLITE === "true" || process.env.USE_SQLITE === "1") {
    return loadFromSQLite();
  }
  return loadFromPostgres();
}
