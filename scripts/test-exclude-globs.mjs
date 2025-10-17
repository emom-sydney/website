import { excludeGlobs, isExcluded } from '../src/_data/s3files.js';

console.log('excludeGlobs:', excludeGlobs);

const tests = [
  { key: 'gallery/foo/index.html', expect: true },
  { key: 'gallery/foo/track.mp3', expect: false },
  { key: 'gallery/foo/.DS_Store', expect: true },
  { key: 'gallery/foo/readme.TXT', expect: false }
];

let failed = 0;
for (const t of tests) {
  const got = isExcluded(t.key);
  if (got !== t.expect) {
    console.error(`FAIL for ${t.key}: expected ${t.expect} got ${got}`);
    failed++;
  } else {
    console.log(`OK ${t.key} => ${got}`);
  }
}

if (failed) {
  console.error(`${failed} tests failed`);
  process.exit(1);
} else {
  console.log('All tests passed');
}
