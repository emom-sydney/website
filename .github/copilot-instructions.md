# Copilot Instructions for sydney.emom.me Website

## Overview
- This site is built with [11ty (Eleventy)](https://www.11ty.dev), a static site generator. Source files are in `src/`, output is in `_site/`.
- Main layout: `src/_includes/main.njk` (Nunjucks template). Pages use frontmatter to specify layout and metadata.
- Static assets (CSS, images) are in `assets/` and referenced with absolute paths (e.g., `/assets/css/style.css`).
- Data files (e.g., `siteName.json`) are in `src/_data/` and injected into templates.

## Developer Workflows
- **Build locally:** Run `npx @11ty/eleventy` from the project root. Output goes to `_site/`.
- **Deploy:** See `.github/workflows/build-deploy.yml` for CI/CD details of the planned deployment automation process, but this has not yet been set up as we are now in the process of looking at alternative hosting options.
- **Custom Scripts:** Script directory `src/_scripts/` contained some now deprecated scripts for S3 HTML generation and can be ignored for now.

## Project Conventions
- Use Nunjucks (`.njk`) for layouts and includes.
- All site content and posts should be placed in `src/` (e.g., `src/posts/`).
- Use absolute URLs for assets in templates and HTML.
- CSS is customized for a dark theme with black background (`assets/css/style.css`).
- The site name is injected from `src/_data/siteName.json`.

## Integration Points
- AWS S3: Used for static hosting and media file storage. See `src/_scripts/s3_bucket_listing.py` for HTML generation from S3.
- AWS DynamoDB: Example integration in `assets/scripts/querydb-example.html` (requires AWS credentials and Cognito setup).

## Key Files & Directories
- `src/_includes/main.njk`: Main HTML layout
- `src/index.html`: Example page using the layout
- `src/_scripts/s3_bucket_listing.py`: S3 HTML listing generator
- `assets/scripts/querydb-example.html`: DynamoDB browser query example
- `assets/css/style.css`: Main stylesheet
- `.github/workflows/build-deploy.yml`: CI/CD pipeline

## Notes
- No test suite or build script is present by default; all builds are static via 11ty.
- Posts directory (`src/posts/`) is currently empty but intended for future content.
- For new pages, use frontmatter to specify layout and metadata.
