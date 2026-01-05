# Copilot Instructions for sydney.emom.me Website

## Architecture Overview
- **Static Site Generator**: 11ty (Eleventy) with ES modules
- **Input**: Markdown + Nunjucks templates in `src/`, CSV data files, S3 media
- **Output**: Static HTML in `_site/`
- **Core Flow**: Templates + CSV data → pagination/generators (`.11ty.js`) → individual pages

## Data Architecture (Critical)
The site uses **declarative CSV files + dynamic generators**:

1. **CSV Data** (`src/_data/*.csv`):
   - `artists.csv`: artist IDs, stage names (linked by `ArtistID`)
   - `performances.csv`: event/artist relationships (join table via `ArtistID`)
   - `artistimages.csv`: artist photos (keyed by `artistID`)
   - `artistsocialpprofiles.csv`: social media links (keyed by `artistID`, `socialPlatformID`)
   - `socialplatforms.csv`: platform definitions with URL templates (`URLFormat` field)
   - `events.csv`, `eventtypes.csv`: event metadata

2. **ID Conversion**: `.eleventy.js` automatically parses CSV columns ending in `ID` as integers for reliable joins

3. **Generator Pattern** (`.11ty.js` files):
   - **`src/artists/artist.11ty.js`**: Pagination over `artists` array; generates individual artist pages at `/artists/{slug}/index.html`
   - **`src/gallery/gallery.11ty.js`**: Pagination over gallery folders from S3; generates `/gallery/{galleryname}/index.html` with lightbox
   - Data joins happen in render functions (manual loops, not DB queries)

## Dynamic Page Generation
- Use pagination (`.data.pagination`) to generate multiple pages from arrays
- `permalink` function computes final URLs; typically slugify from artist/event name
- Render function receives full data context (all CSV collections), then filters/joins manually
- Example join: Loop `performances` filtering by `perf.ArtistID == artist.ID`

## Media & Images
- **S3 Integration** (`src/_data/s3files.js`): Lists S3 bucket objects; used by `gallery.11ty.js`
- **Image Processing** (`src/_data/imageHelpers.js`): Uses `@11ty/eleventy-img` to generate thumbnails
  - Slugify logic: S3 path → filesystem-safe name → cached thumbnail in `assets/img/th/`
  - URL pattern: `/assets/img/th/{slug}-250.jpeg`
- **Background Images** (`src/_data/bgimages.js`, `src/_data/media_baseurl.js`):
  - Client-side random selection in `src/_includes/main.njk` (sets `--bg-image-url` CSS var)
  - Base URL configurable via `media_baseurl.js` (supports CDN or empty for relative paths)

## Developer Workflows

**Build locally**: `npx @11ty/eleventy` (outputs to `_site/`)

**Serve & watch**: `npx @11ty/eleventy --serve` (localhost:8080)

**Add gallery for event**:
1. Upload files to `s3://sydney.emom.me/gallery/{galleryname}/`
2. Add `{galleryname}` to `src/_data/galleries.js`
3. Rebuild site

**Deploy**: Manual sync via `rsync -rv --delete _site/ root@sydney.emom.me:/var/www/html/sydney.emom.me/` (CI/CD via `.github/workflows/build-deploy.yml` not fully set up)

## Template Conventions
- **Layout**: All pages inherit `src/_includes/main.njk` (reads `bgimages`, `bgBase`, outputs HTML scaffold)
- **Includes**: `page_header.njk`, `page_sidebar.njk`, `page_footer.njk` (reusable components)
- **Engine**: Nunjucks (`.njk` files); filter examples: `sortBy`, `slugify`, `dateFilter`, `getYear`
- **Asset Paths**: Always absolute (e.g., `/assets/css/style.css`)
- **Content**: Use frontmatter to specify `layout` and `pageTitle`

## Key Files
- `.eleventy.js` — Config: CSV parsing, filters, collections, global data
- `src/_includes/main.njk` — Master layout (handles bg images, content wrapper)
- `src/artists/artist.11ty.js` — Dynamic artist page generator
- `src/gallery/gallery.11ty.js` — Dynamic gallery generator with S3 integration
- `src/_data/*.csv` — Artist/event/performance data (no DB)
- `src/_data/imageHelpers.js` — Thumbnail generation wrapper
- `src/_data/s3files.js` — S3 bucket listing (uses AWS SDK)
- `assets/css/style.css` — Dark theme; uses `var(--bg-image-url)`

## Common Tasks
- **Add artist**: Add row to `artists.csv`, optionally add image/socials to related CSVs, rebuild
- **Link gallery**: Add path string to `galleries.js`, upload images to S3, rebuild
- **Style tweaks**: Edit `assets/css/style.css` directly (affects all pages)
- **New static page**: Create `.njk` file in `src/`, use frontmatter with `layout: main.njk`

## Notes
- No database; all data declarative (CSVs) → stored in `11ty.data` at build time
- No test suite; validate by building locally
- Keep `.page_body` readable (white bg, possibly overlay) over photos
- S3 access required for gallery builds; local builds skip S3 if credentials absent