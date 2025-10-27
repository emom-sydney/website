# Copilot Instructions for sydney.emom.me Website

## Overview
- This site is built with [11ty (Eleventy)](https://www.11ty.dev), a static site generator. Source files are in `src/`, output is in `_site/`.
- Main layout: `src/_includes/main.njk` (Nunjucks template). Pages use frontmatter to specify layout and metadata.
- Static assets (CSS, images) are in `assets/` and referenced with absolute paths (e.g., `/assets/css/style.css`).
- Data files (e.g., `siteName.json`) are in `src/_data/` and injected into templates.

## Developer Workflows
- **Build locally:** Run `npx @11ty/eleventy` from the project root. Output goes to `_site/`.
- **Deploy:** See `.github/workflows/build-deploy.yml` for CI/CD details. Deployment is automated via GitHub Actions.
- **Custom scripts:** Python scripts (e.g., `src/_scripts/s3_bucket_listing.py`) are used for generating HTML listings from S3 buckets. These are not part of the 11ty build and must be run manually.
- **DynamoDB Example:** See `assets/scripts/querydb-example.html` for a browser-based AWS DynamoDB query example (requires AWS Cognito setup).

## Project Conventions
- Use Nunjucks (`.njk`) for layouts and includes.
- All site content and posts should be placed in `src/` (e.g., `src/posts/`).
- Use absolute URLs for assets in templates and HTML.
- CSS is customized for a dark theme with orange background (`assets/css/style.css`).
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
