import fs from "fs";
import path from "path";
import { spawn } from "child_process";
import { fileURLToPath } from "url";
import { parse } from "csv-parse/sync";

const scriptPath = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(scriptPath), "..");
const dataDir = path.join(projectRoot, "src", "_data");
const schemaPath = path.join(projectRoot, "db", "schema.sql");

const monthLookup = {
  Jan: "01",
  Feb: "02",
  Mar: "03",
  Apr: "04",
  May: "05",
  Jun: "06",
  Jul: "07",
  Aug: "08",
  Sep: "09",
  Oct: "10",
  Nov: "11",
  Dec: "12",
};

function parseArgs(argv) {
  const args = {
    execute: false,
    stdout: false,
    skipSchema: false,
    output: null,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--execute") {
      args.execute = true;
    } else if (arg === "--stdout") {
      args.stdout = true;
    } else if (arg === "--skip-schema") {
      args.skipSchema = true;
    } else if (arg === "--output") {
      args.output = argv[i + 1];
      i += 1;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (args.stdout && args.output) {
    throw new Error("Use either --stdout or --output, not both.");
  }

  return args;
}

function readCsv(filename) {
  const csvPath = path.join(dataDir, filename);
  const contents = fs.readFileSync(csvPath, "utf8");

  return parse(contents, {
    columns: true,
    skip_empty_lines: true,
  });
}

function sqlText(value) {
  if (value === null || value === undefined || value === "") {
    return "NULL";
  }

  return `'${String(value).replace(/'/g, "''")}'`;
}

function sqlInt(value) {
  if (value === null || value === undefined || value === "") {
    return "NULL";
  }

  const parsed = Number.parseInt(String(value), 10);
  if (Number.isNaN(parsed)) {
    throw new Error(`Expected integer, received "${value}"`);
  }

  return String(parsed);
}

function parseLegacyEventDate(input) {
  const match = String(input).trim().match(/^[A-Za-z]{3},\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$/);
  if (!match) {
    throw new Error(`Unsupported event date format: "${input}"`);
  }

  const [, dayText, monthText, yearText] = match;
  const month = monthLookup[monthText];
  if (!month) {
    throw new Error(`Unsupported event month: "${monthText}"`);
  }

  const day = dayText.padStart(2, "0");
  return `${yearText}-${month}-${day}`;
}

function buildInsert(tableName, columns, rows) {
  if (!rows.length) {
    return "";
  }

  const valuesSql = rows
    .map((row) => `  (${columns.map((column) => row[column]).join(", ")})`)
    .join(",\n");

  return `INSERT INTO ${tableName} (${columns.join(", ")})\nVALUES\n${valuesSql}\nON CONFLICT (id) DO UPDATE SET\n${columns
    .filter((column) => column !== "id")
    .map((column) => `  ${column} = EXCLUDED.${column}`)
    .join(",\n")};\n`;
}

function buildImportSql() {
  const artists = readCsv("artists.csv").map((row) => ({
    id: sqlInt(row.ID),
    stage_name: sqlText(row.stageName),
  }));

  const eventTypes = readCsv("eventtypes.csv").map((row) => ({
    id: sqlInt(row.ID),
    description: sqlText(row.Description),
  }));

  const socialPlatforms = readCsv("socialplatforms.csv").map((row) => ({
    id: sqlInt(row.ID),
    platform_name: sqlText(row.platformName),
    url_format: sqlText(row.URLFormat),
  }));

  const events = readCsv("events.csv").map((row) => ({
    id: sqlInt(row.ID),
    event_date: sqlText(parseLegacyEventDate(row.Date)),
    legacy_date_text: sqlText(row.Date),
    type_id: sqlInt(row.TypeID),
    event_name: sqlText(row.EventName),
    gallery_url: sqlText(row.GalleryURL),
  }));

  const performances = readCsv("performances.csv").map((row) => ({
    id: sqlInt(row.ID),
    event_id: sqlInt(row.EventID),
    artist_id: sqlInt(row.ArtistID),
  }));

  const artistImages = readCsv("artistimages.csv").map((row) => ({
    id: sqlInt(row.ID),
    artist_id: sqlInt(row.artistID),
    image_url: sqlText(row.imageURL),
  }));

  const artistSocialProfiles = readCsv("artistsocialprofiles.csv").map((row) => ({
    id: sqlInt(row.ID),
    artist_id: sqlInt(row.artistID),
    social_platform_id: sqlInt(row.socialPlatformID),
    profile_name: sqlText(row.profileName),
  }));

  return [
    "BEGIN;",
    "TRUNCATE TABLE artist_social_profiles, artist_images, performances, events, social_platforms, event_types, artists RESTART IDENTITY CASCADE;",
    buildInsert("artists", ["id", "stage_name"], artists),
    buildInsert("event_types", ["id", "description"], eventTypes),
    buildInsert("social_platforms", ["id", "platform_name", "url_format"], socialPlatforms),
    buildInsert("events", ["id", "event_date", "legacy_date_text", "type_id", "event_name", "gallery_url"], events),
    buildInsert("performances", ["id", "event_id", "artist_id"], performances),
    buildInsert("artist_images", ["id", "artist_id", "image_url"], artistImages),
    buildInsert("artist_social_profiles", ["id", "artist_id", "social_platform_id", "profile_name"], artistSocialProfiles),
    "COMMIT;",
    "",
  ].join("\n");
}

function loadSchemaSql(skipSchema) {
  if (skipSchema) {
    return "";
  }

  return `${fs.readFileSync(schemaPath, "utf8").trim()}\n\n`;
}

async function runPsql(sql) {
  return new Promise((resolve, reject) => {
    const child = spawn("psql", ["-v", "ON_ERROR_STOP=1"], {
      cwd: projectRoot,
      env: process.env,
      stdio: ["pipe", "inherit", "inherit"],
    });

    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`psql exited with status ${code}`));
      }
    });

    child.stdin.write(sql);
    child.stdin.end();
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sql = `${loadSchemaSql(args.skipSchema)}${buildImportSql()}`;

  if (args.stdout) {
    process.stdout.write(sql);
    return;
  }

  if (args.output) {
    fs.writeFileSync(path.resolve(projectRoot, args.output), sql);
    console.log(`Wrote SQL to ${args.output}`);
    return;
  }

  if (!args.execute) {
    console.log("Dry run complete. Use --stdout, --output <file>, or --execute.");
    return;
  }

  await runPsql(sql);
  console.log("Import complete.");
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
