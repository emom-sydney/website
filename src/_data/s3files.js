import mediaBaseUrl from "./media_baseurl.js";
import fs from "fs/promises";

const manifestUrl = process.env.MEDIA_MANIFEST_URL || `${mediaBaseUrl}/.well-known/gallery-manifest.json`;
const manifestPath = process.env.MEDIA_MANIFEST_PATH || "";

// Globs to exclude from listings (case-insensitive). Patterns are matched
// against the full key, the filename, and the extension.
export const excludeGlobs = [
  "*.html",
  ".DS_Store",
];

// Convert a simple glob (supports '*' and '?') to a RegExp
function globToRegExp(glob) {
  const escaped = glob.replace(/([.+^=!:${}()|[\]\\\/])/g, "\\$1");
  const withWildcards = escaped.replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${withWildcards}$`, "i");
}

const excludeRegexes = excludeGlobs.map(globToRegExp);

export function isExcluded(key) {
  const parts = key.split("/");
  const filename = parts[parts.length - 1];
  const ext = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";

  for (const rx of excludeRegexes) {
    if (rx.test(key)) return true;
    if (rx.test(filename)) return true;
    if (ext && rx.test(ext)) return true;
  }

  return false;
}

const typeMapping = {
  mp4: "&#x1F3A5;", // Movie camera emoji
  mov: "&#x1F3A5;",
  mkv: "&#x1F3A5;",
  lrf: "&#x1F3A5;",
  mp3: "&#x1F508;", // Loudspeaker emoji
  wav: "&#x1F508;",
  flac: "&#x1F508;",
  jpg: "&#x1F5BC;", // Picture emoji
  jpeg: "&#x1F5BC;",
  png: "&#x1F5BC;",
  gif: "&#x1F5BC;",
  pdf: "&#x1F4DA;", // Book emoji
  doc: "&#x1F4DA;",
  txt: "&#x1F4DA;",
};

function formatSize(bytes) {
  if (bytes >= 1073741824) {
    return (bytes / 1073741824).toFixed(2) + " GB";
  }

  return (bytes / 1048576).toFixed(2) + " MB";
}

function encodePathPreservingSlashes(pathname) {
  return pathname
    .split("/")
    .map((part) => encodeURIComponent(decodeURIComponent(part || "")))
    .join("/");
}

function normalizeMediaUrl(key) {
  const cleanKey = String(key || "").replace(/^\/+/, "");
  const rawUrl = `${mediaBaseUrl}/${cleanKey}`;

  try {
    const parsed = new URL(rawUrl);
    if (cleanKey) {
      parsed.pathname = `/${encodePathPreservingSlashes(cleanKey)}`;
      parsed.hash = "";
    } else {
      parsed.pathname = encodePathPreservingSlashes(parsed.pathname);
    }
    return parsed.toString();
  } catch {
    return encodeURI(rawUrl);
  }
}

function normalizeManifestFile(file) {
  const key = String(file.key || "");
  const name = String(file.name || key.split("/").pop() || "");
  const ext = String(file.ext || key.split(".").pop() || "").toLowerCase();
  const size = Number(file.size || 0);
  const normalizedUrl = normalizeMediaUrl(key);

  return {
    key,
    name,
    size,
    sizeFormatted: formatSize(size),
    lastModified: file.lastModified || null,
    url: normalizedUrl,
    ext,
    icon: typeMapping[ext] || "",
    storageClass: file.storageClass || "STANDARD",
  };
}

let manifestPromise;

async function parseManifestDocument(document) {
  if (Array.isArray(document)) {
    return document;
  }

  if (Array.isArray(document?.files)) {
    return document.files;
  }

  throw new Error(`Gallery manifest did not contain a files array`);
}

async function loadManifestFromFile() {
  if (!manifestPath) {
    return null;
  }

  const raw = await fs.readFile(manifestPath, "utf8");
  return parseManifestDocument(JSON.parse(raw));
}

async function loadManifest() {
  if (!manifestPromise) {
    manifestPromise = (async () => {
      try {
        const response = await fetch(manifestUrl);
        if (!response.ok) {
          throw new Error(`Failed to load gallery manifest: ${response.status} ${response.statusText}`);
        }

        return parseManifestDocument(await response.json());
      } catch (error) {
        if (manifestPath) {
          try {
            return await loadManifestFromFile();
          } catch (fileError) {
            throw new Error(
              `Failed to load gallery manifest from ${manifestUrl} and fallback file ${manifestPath}: ${fileError.message}`
            );
          }
        }

        const details = error?.cause?.code ? ` (${error.cause.code})` : "";
        throw new Error(
          `Failed to load gallery manifest from ${manifestUrl}${details}. ` +
          `Set MEDIA_BASEURL, MEDIA_MANIFEST_URL, or MEDIA_MANIFEST_PATH for your local environment.`
        );
      }
    })();
  }

  return manifestPromise;
}

export default async function (prefix) {
  const manifestFiles = await loadManifest();
  const cleanPrefix = String(prefix || "").replace(/^\/+|\/+$/g, "");
  const keyPrefix = cleanPrefix ? `gallery/${cleanPrefix}` : "gallery";

  return manifestFiles
    .map(normalizeManifestFile)
    .filter((file) => {
      if (!file.key) return false;
      if (!(file.key === keyPrefix || file.key.startsWith(`${keyPrefix}/`))) return false;
      return !isExcluded(file.key);
    });
}
