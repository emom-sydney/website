# Project Structure

## Directory Organization

### Core Directories
- **`src/`** - Source files for 11ty static site generator
  - **`_data/`** - Global data files (galleries.js, s3files.js, siteName.json)
  - **`_includes/`** - Template layouts (main.njk)
  - **`posts/`** - Dynamic page generators (gallery.11ty.js, gallery-index.11ty.js)
  - **`index.njk`** - Homepage template

- **`assets/`** - Static assets copied to output
  - **`css/`** - Stylesheets
  - **`img/`** - Images and logos
  - **`media/`** - Media files
  - **`scripts/`** - Client-side scripts

- **`_site/`** - Generated static site output (build artifact)

### Configuration Files
- **`.eleventy.js`** - 11ty configuration and build settings
- **`package.json`** - Node.js dependencies and project metadata
- **`.github/workflows/build-deploy.yml`** - CI/CD pipeline configuration

## Core Components

### Gallery System
- **Data Layer**: `galleries.js` defines available galleries, `s3files.js` fetches S3 content
- **Generation Layer**: `gallery.11ty.js` creates individual gallery pages, `gallery-index.11ty.js` creates gallery listing
- **Template Layer**: `main.njk` provides consistent page layout

### Build Architecture
- **Input**: `src/` directory with templates and data
- **Processing**: 11ty processes templates, copies assets, generates static HTML
- **Output**: `_site/` directory ready for web deployment

## Architectural Patterns
- **JAMstack Architecture**: JavaScript (11ty), APIs (AWS S3), Markup (static HTML)
- **Data-Driven Generation**: Gallery pages generated from external data sources
- **Template Inheritance**: Consistent layout through Nunjucks template system