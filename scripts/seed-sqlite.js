import { execSync } from "child_process";
import Database from "better-sqlite3";
import { readFileSync } from "fs";

const dbPath = process.argv[2] || "emom.local.sqlite";

console.log(`Creating database: ${dbPath}`);

const schema = readFileSync("db/schema-sqlite.sql", "utf8");
const seed = readFileSync("db/seed.sql", "utf8");

const db = new Database(dbPath);
db.exec(schema);
db.exec(seed);

const stats = db.prepare(`
  SELECT 'profiles' as table_name, COUNT(*) as count FROM profiles
  UNION ALL SELECT 'events', COUNT(*) FROM events
  UNION ALL SELECT 'performances', COUNT(*) FROM performances
  UNION ALL SELECT 'artists', COUNT(*) FROM profile_roles WHERE role = 'artist'
  UNION ALL SELECT 'crew', COUNT(*) FROM profile_roles WHERE role = 'volunteer'
  UNION ALL SELECT 'merch_items', COUNT(*) FROM merch_items
`).all();

db.close();

console.log("\nDone! Seeded the following:");
for (const row of stats) {
  console.log(`  ${row.table_name}: ${row.count}`);
}
console.log(`\nRun 'npm run start:local' to serve the site.`);
