# Copilot Instructions for sydney.emom.me Website

## Overview
- This site is built with 11ty (Eleventy). Source files are in `src/`, output is in `_site/`.
- Main layout: `src/_includes/main.njk`. Pages use frontmatter to specify layout and metadata.
- Static assets (CSS, images) are in `assets/` and referenced with absolute paths (e.g., `/assets/css/style.css`).
- Data files are in `src/_data/` and are injected into templates.

## Developer Workflows
- Build locally: `npx @11ty/eleventy` from the project root. Output goes to `_site/`.
- Deploy: See `.github/workflows/build-deploy.yml` for CI/CD details (not fully set up yet).
- Custom scripts: `src/_scripts/` contains deprecated helper scripts; they can be ignored for routine tasks.

## Project Conventions
- Use Nunjucks (`.njk`) for layouts and includes.
- Place site content in `src/` (e.g., `src/posts/`).
- Use absolute URLs for assets in templates and HTML.
- CSS is customised for a dark theme (`assets/css/style.css`).
- The site name comes from `src/_data/siteName.json`.

## Dynamic background images (updated)
A lightweight client-side implementation is used to randomly select a background image on each page load. This keeps the site build simple while allowing per-load randomness.

- Data files:
  - `src/_data/bgimages.js` — array of image paths (relative to storage root). Keep entries short (relative paths) to reduce template payload.
  - `src/_data/bgBase.js` — string base URL for media storage (CDN, S3 bucket, etc.). This separates the base host from the image paths.

- Template:
  - `src/_includes/main.njk` reads `bgimages` and `bgBase` and sets a CSS variable `--bg-image-url` with a randomly chosen image URL at page load. This allows the stylesheet to reference `var(--bg-image-url)` without embedding large inline styles.

- Styles:
  - `assets/css/style.css` uses `background-image: var(--bg-image-url);` and provides fallback/background-color and sizing.

- Approaches explained:
  - Client-side (current): fast to change (new image each load), no rebuild required, minimal JS added. Use when images are static assets and per-load variation is desired.
  - Build-time: pick one image during the Eleventy build and inject its URL into templates. Use when you want deterministic background until next build and to avoid client-side JS.

- To change the media root:
  - Edit `src/_data/bgBase.js` and set the appropriate base URL for the environment (CDN, S3, or empty for site-relative paths).

## Integration & Notes
- AWS S3: used for static hosting and media file storage in this project. See `src/_scripts/s3_bucket_listing.py` for S3 helpers.
- DynamoDB: example in `assets/scripts/querydb-example.html` (requires credentials/Cognito).
- Keep the white `.page_body` container (or add an overlay) so content remains readable over photos.

## Key Files & Directories
- `src/_includes/main.njk` — Main HTML layout (reads `bgimages` + `bgBase`).
- `src/_data/bgimages.js` — List of relative image paths.
- `src/_data/bgBase.js` — Media base URL string.
- `assets/css/style.css` — Main stylesheet using `--bg-image-url`.
- `src/index.njk` — Example page using the layout.
- `src/_scripts/s3_bucket_listing.py` — S3 HTML listing helper.

## Notes
- No test suite is present by default; builds are static via 11ty.
- For new pages, use frontmatter to specify layout and metadata.
- To preview changes locally after edits, run: `npx @11ty/eleventy` and open `_site/` output in a browser.

## CSV Data & ID Conversion
- The `.eleventy.js` config automatically converts all columns ending in `ID` to integers during CSV import.
- Use `event.GalleryURL` to link to gallery pages: `/gallery/{{ event.GalleryURL }}/index.html`