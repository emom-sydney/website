import { S3Client, ListObjectsV2Command } from "@aws-sdk/client-s3";

const s3 = new S3Client({ region: "ap-southeast-2" });
const BUCKET = "sydney.emom.me";

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

export default async function(prefix) {
  const params = {
    Bucket: BUCKET,
    Prefix: `gallery/${prefix}`,
  };
  const command = new ListObjectsV2Command(params);
  const data = await s3.send(command);
  return (data.Contents || [])
    .filter(obj => {
      const parts = obj.Key.split('/');
      const filename = parts[parts.length - 1];
      const ext = (filename.includes('.') ? filename.split('.').pop().toLowerCase() : '');

      // Exclude if any glob regex matches the full key, the filename, or the extension
      for (const rx of excludeRegexes) {
        if (rx.test(obj.Key)) return false;
        if (rx.test(filename)) return false;
        if (ext && rx.test(ext)) return false;
      }

      return true;
    })
    .map(obj => {
      const ext = obj.Key.split('.').pop().toLowerCase();
      const name = obj.Key.split('/').pop();
      return {
        key: obj.Key,
        name,
        size: obj.Size,
        sizeFormatted: formatSize(obj.Size),
        lastModified: obj.LastModified,
        url: `http://${BUCKET}.s3.amazonaws.com/${obj.Key}`,
        ext,
        icon: typeMapping[ext] || ''
      };
    });
}