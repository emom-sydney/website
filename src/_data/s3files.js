import { S3Client, ListObjectsV2Command } from "@aws-sdk/client-s3";

import siteConfig from './siteConfig.js';

const s3 = new S3Client({ 
  region: process.env.AWS_REGION || siteConfig.aws.region
});

// Globs to exclude from listings (case-insensitive). Patterns are matched
// against the full S3 key, the filename, and the extension.
// 
export const excludeGlobs = [
  '*.html',
  '.DS_Store'
];

// Convert a simple glob (supports '*' and '?') to a RegExp
function globToRegExp(glob) {
  // Escape regexp special chars except for '*' and '?'
  // Then replace glob wildcards with their regex equivalents
  const escaped = glob.replace(/([.+^=!:${}()|[\]\\\/])/g, "\\$1");
  const withWildcards = escaped.replace(/\*/g, '.*').replace(/\?/g, '.');
  return new RegExp(`^${withWildcards}$`, 'i');
}

const excludeRegexes = excludeGlobs.map(globToRegExp);

// Helper to check whether a given S3 key (or filename) should be excluded
export function isExcluded(key) {
  const parts = key.split('/');
  const filename = parts[parts.length - 1];
  const ext = (filename.includes('.') ? filename.split('.').pop().toLowerCase() : '');

  for (const rx of excludeRegexes) {
    if (rx.test(key)) return true;
    if (rx.test(filename)) return true;
    if (ext && rx.test(ext)) return true;
  }
  return false;
}

// Map file extensions to emoji HTML entities
const typeMapping = {
  mp4: "&#x1F3A5;", // Movie camera emoji
  mov: "&#x1F3A5;",
  mkv: "&#x1F3A5;",
  mp3: "&#x1F508;", // Loudspeaker emoji
  wav: "&#x1F508;",
  flac: "&#x1F508;",
  jpg: "&#x1F5BC;", // Picture emoji
  jpeg: "&#x1F5BC;",
  png: "&#x1F5BC;",
  gif: "&#x1F5BC;",
  pdf: "&#x1F4DA;", // Book emoji
  doc: "&#x1F4DA;",
  txt: "&#x1F4DA;"
};

function formatSize(bytes) {
  if (bytes >= 1073741824) {
    return (bytes / 1073741824).toFixed(2) + ' GB';
  } else {
    return (bytes / 1048576).toFixed(2) + ' MB';
  }
}

export async function getActiveGalleries() {
  const allFiles = await s3filesMain();
  // Log the structure we're working with
  console.log('getActiveGalleries: Got files structure:', 
    Object.entries(allFiles).map(([prefix, files]) => 
      `${prefix}: ${files?.length || 0} files`
    )
  );
  // Filter for non-empty galleries and return just their prefixes
  const activeGalleries = Object.entries(allFiles)
    .filter(([prefix, files]) => files && files.length > 0)
    .map(([prefix]) => prefix);
  console.log('getActiveGalleries: Found active galleries:', activeGalleries);
  return activeGalleries;
}

async function s3filesMain(prefix = null) {
  const prefixes = prefix ? [prefix] : (await import("./galleries.js")).default;
  let allFiles = {};

  // Initialize result with empty arrays for all prefixes
  if (!prefix) {
    for (const p of prefixes) {
      allFiles[p] = [];
    }
  }

  console.log('S3Files: Processing prefixes:', prefixes);
  console.log('S3Files: Called with prefix:', prefix);

  for (const prefix of prefixes) {
    console.log('S3Files: Processing prefix:', prefix);
    const command = new ListObjectsV2Command({
      Bucket: siteConfig.aws.s3.buckets.gallery,
      Prefix: `gallery/${prefix}`,
      MaxKeys: 1000
    });

    try {
      const response = await s3.send(command);
      
      if (!response.Contents) continue;

      console.log('S3Files: Got response:', {
        prefix,
        count: response.Contents?.length || 0
      });
      
      const contents = response.Contents || [];
      console.log('S3Files: Got contents for prefix:', prefix, 'count:', contents.length);

      const processedFiles = contents
        .filter(obj => !isExcluded(obj.Key))
        .map(obj => ({
          key: obj.Key,
          name: obj.Key.split('/').pop(),
          url: `https://${siteConfig.aws.s3.buckets.gallery}/${obj.Key}`,
          size: obj.Size,
          sizeFormatted: formatSize(obj.Size),
          lastModified: obj.LastModified,
          type: obj.Key.split('.').pop().toLowerCase(),
          icon: typeMapping[obj.Key.split('.').pop().toLowerCase()] || '&#x1F4C4;'
        }));
      
      console.log('S3Files: Processed files:', {
        prefix,
        count: processedFiles.length,
        sample: processedFiles[0]
      });
        
      if (prefix) {
        return processedFiles;
      } else {
        // When called without a specific prefix, use the current prefix from the loop
        allFiles[prefix] = processedFiles;
      }
    } catch (error) {
      console.error(`Error fetching S3 objects for prefix ${prefix}:`, error);
      if (prefix) {
        return [];
      } else {
        // Keep the empty array we initialized earlier
        console.log('S3Files: Error handled for prefix:', prefix);
      }
    }
  }

  // For single prefix requests, return empty array if nothing was found
  if (prefix) {
    return [];
  }

  // Return the complete object if no specific prefix was requested
  console.log('S3Files: Final result:', Object.keys(allFiles).map(k => `${k}: ${allFiles[k].length} files`));
  return allFiles;
}

// Export the main function as default and the helper function separately
export default s3filesMain;