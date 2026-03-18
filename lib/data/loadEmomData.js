import fs from "fs";
import path from "path";
import { parse } from "csv-parse/sync";

const DATA_DIR = path.resolve(process.cwd(), "src/_data");

function parseCsvTable(filename) {
  const csvPath = path.join(DATA_DIR, filename);
  const contents = fs.readFileSync(csvPath, "utf8");
  const records = parse(contents, {
    columns: true,
    skip_empty_lines: true,
  });

  return records.map((record) => {
    const converted = { ...record };
    for (const key of Object.keys(converted)) {
      if (key === "ID" || key.endsWith("ID")) {
        converted[key] = parseInt(converted[key], 10);
      }
    }
    return converted;
  });
}

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

function loadFromCsv() {
  const artists = parseCsvTable("artists.csv");
  const artistimages = parseCsvTable("artistimages.csv");
  const artistsocialprofiles = parseCsvTable("artistsocialprofiles.csv");
  const events = parseCsvTable("events.csv");
  const eventtypes = parseCsvTable("eventtypes.csv");
  const performances = parseCsvTable("performances.csv");
  const socialplatforms = parseCsvTable("socialplatforms.csv");

  const artistsById = Object.fromEntries(artists.map((artist) => [artist.ID, artist]));
  const eventsById = Object.fromEntries(events.map((event) => [event.ID, event]));
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

  const eventsWithArtists = events.map((event) => {
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

  const galleries = uniqueNonEmpty(events.map((event) => event.GalleryURL));

  return {
    artists,
    artistimages,
    artistsocialprofiles,
    events,
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

export async function loadEmomData() {
  const dataSource = process.env.EMOM_DATA_SOURCE || "csv";

  if (dataSource === "csv") {
    return loadFromCsv();
  }

  if (dataSource === "postgres") {
    throw new Error(
      "EMOM_DATA_SOURCE=postgres is not implemented yet. Add a Postgres adapter in lib/data/loadEmomData.js."
    );
  }

  throw new Error(`Unsupported EMOM_DATA_SOURCE: ${dataSource}`);
}
