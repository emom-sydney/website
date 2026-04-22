import pg from "pg";
import Database from "better-sqlite3";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const { Client } = pg;

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function getPostgresConfig() {
  if (process.env.DATABASE_URL) {
    return { connectionString: process.env.DATABASE_URL };
  }
  return {
    host: process.env.PGHOST || "127.0.0.1",
    port: Number.parseInt(process.env.PGPORT || "15432", 10),
    database: process.env.PGDATABASE || "emomweb",
    user: process.env.PGUSER,
    password: process.env.PGPASSWORD,
  };
}

function normalizeValue(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (value instanceof Date) return value.toISOString();
  return value;
}

async function exportToSqlite(sqlitePath = "emom.local.sqlite") {
  const sqlite = new Database(sqlitePath);
  sqlite.pragma("journal_mode = WAL");

  const schemaPath = join(__dirname, "..", "db", "schema-sqlite.sql");
  const schema = readFileSync(schemaPath, "utf8");
  sqlite.exec(schema);

  const pgClient = new Client(getPostgresConfig());
  await pgClient.connect();

  try {
    const tables = [
      "profiles",
      "profile_roles",
      "event_types",
      "social_platforms",
      "events",
      "performances",
      "profile_images",
      "profile_social_profiles",
      "merch_items",
      "merch_variants",
    ];

    for (const table of tables) {
      console.log(`Exporting ${table}...`);
      const result = await pgClient.query(`SELECT * FROM ${table}`);
      if (result.rows.length === 0) continue;

      const columns = Object.keys(result.rows[0]);
      const placeholders = columns.map(() => "?").join(", ");
      const insert = sqlite.prepare(
        `INSERT INTO ${table} (${columns.join(", ")}) VALUES (${placeholders})`
      );

      const insertMany = sqlite.transaction((rows) => {
        for (const row of rows) {
          const values = columns.map((col) => normalizeValue(row[col]));
          insert.run(values);
        }
      });

      insertMany(result.rows);
      console.log(`  -> ${result.rows.length} rows`);
    }

    console.log(`\nDone. SQLite database created at: ${sqlitePath}`);
  } finally {
    await pgClient.end();
    sqlite.close();
  }
}

const sqlitePath = process.argv[2] || "emom.local.sqlite";
exportToSqlite(sqlitePath).catch((err) => {
  console.error("Export failed:", err);
  process.exit(1);
});
