# Development Guidelines

## Code Quality Standards

### ES6 Module Pattern (5/5 files)
- **Always use ES6 imports/exports**: `import` and `export default` syntax
- **No CommonJS**: Avoid `require()` and `module.exports`
- **Example**: `import galleries from "../_data/galleries.js";`

### File Naming Conventions (5/5 files)
- **11ty Templates**: Use `.11ty.js` suffix for dynamic page generators
- **Data Files**: Use descriptive names in `_data/` directory (galleries.js, s3files.js)
- **Kebab-case**: Use hyphens for multi-word filenames (gallery-index.11ty.js)

### Code Formatting Standards (5/5 files)
- **Double Quotes**: Use double quotes for strings in template literals
- **Template Literals**: Prefer backticks for multi-line HTML generation
- **Semicolons**: Consistently use semicolons to terminate statements
- **Indentation**: Use 2-space indentation consistently

## Semantic Patterns

### 11ty Template Structure (3/3 template files)
```javascript
// Standard 11ty template pattern
export const data = {
  layout: "main.njk",
  permalink: "path/to/output.html"
};

export default function render(data) {
  return `<html content>`;
}
```

### Data Processing Pattern (2/2 data files)
- **Async Functions**: Use `async/await` for external API calls
- **Array Processing**: Use `.map()`, `.filter()` for data transformation
- **Default Exports**: Export single function or array as default

### AWS S3 Integration Pattern (1/1 S3 file)
```javascript
// Standard S3 client setup
import { S3Client, ListObjectsV2Command } from "@aws-sdk/client-s3";
const s3 = new S3Client({ region: "ap-southeast-2" });

// Standard S3 operation
const command = new ListObjectsV2Command(params);
const data = await s3.send(command);
```

### String Manipulation Pattern (3/3 files with path processing)
- **Path Normalization**: Use regex chains for consistent URL generation
- **Pattern**: `.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '')`
- **Purpose**: Convert gallery names to URL-safe paths

### HTML Generation Patterns (3/3 template files)
- **Template Literals**: Use backticks for multi-line HTML
- **Array Mapping**: Use `.map().join('')` for list generation
- **Conditional Rendering**: Use ternary operators for optional content

## Configuration Standards

### 11ty Configuration (1/1 config file)
- **Function Export**: Export default configuration function
- **Directory Settings**: Always set input, output, and includes directories
- **Asset Copying**: Use `addPassthroughCopy` for static assets
- **Commented Code**: Keep commented alternatives for reference

### Package.json Standards (1/1 package file)
- **ES6 Modules**: Include `"type": "module"`
- **AWS Dependencies**: Use both v2 and v3 SDK for compatibility
- **Minimal Dependencies**: Keep dependency list focused and essential

## Error Handling Patterns
- **Defensive Programming**: Check array types before processing
- **Fallback Values**: Use `|| []` for potentially undefined arrays
- **Safe Property Access**: Use optional chaining where appropriate