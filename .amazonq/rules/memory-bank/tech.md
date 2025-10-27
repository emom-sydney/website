# Technology Stack

## Core Technologies
- **Static Site Generator**: 11ty (Eleventy) - Modern static site generator
- **Template Engine**: Nunjucks (.njk files) for HTML templating
- **JavaScript**: ES6 modules with Node.js runtime
- **CSS**: Standard CSS for styling

## Dependencies
- **AWS SDK**: 
  - `@aws-sdk/client-s3` (v3.910.0) - Modern AWS S3 client
  - `aws-sdk` (v2.1692.0) - Legacy AWS SDK for compatibility
- **Node.js**: ES6 module support (`"type": "module"` in package.json)

## Build System
- **11ty Configuration**: `.eleventy.js` defines:
  - Input directory: `src/`
  - Output directory: `_site/`
  - Includes directory: `_includes/`
  - Asset passthrough: `assets/img`, `assets/css`

## Development Commands
```bash
# Install dependencies
npm install

# Build site (11ty default)
npx @11ty/eleventy

# Development server (11ty default)
npx @11ty/eleventy --serve
```

## Deployment
- **CI/CD**: GitHub Actions workflow (`.github/workflows/build-deploy.yml`)
- **Hosting**: Static site deployment (configuration in workflow)
- **Asset Management**: AWS S3 bucket `sydney.emom.me` for gallery images

## File Extensions
- **`.njk`** - Nunjucks templates
- **`.11ty.js`** - 11ty JavaScript templates for dynamic page generation
- **`.js`** - Data files and configuration (ES6 modules)
- **`.css`** - Stylesheets
- **`.json`** - Configuration and data files