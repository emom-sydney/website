import mediaBaseUrl from "./mediaBaseUrl.js";

const THUMBNAIL_SIZE_SUFFIXES = {
  sm: "sm",
  small: "sm",
  md: "md",
  medium: "md",
  lg: "lg",
  large: "lg",
};

function normalizeThumbnailSize(size) {
  return THUMBNAIL_SIZE_SUFFIXES[String(size || "").toLowerCase()] || null;
}

function addThumbnailSuffix(pathname, sizeSuffix) {
  const lastSlashIndex = pathname.lastIndexOf("/");
  const directory = lastSlashIndex === -1 ? "" : pathname.slice(0, lastSlashIndex + 1);
  const filename = lastSlashIndex === -1 ? pathname : pathname.slice(lastSlashIndex + 1);
  const lastDotIndex = filename.lastIndexOf(".");
  const stem = lastDotIndex > 0 ? filename.slice(0, lastDotIndex) : filename;

  if (!stem) return null;
  return `${directory}${stem}.${sizeSuffix}.jpg`;
}

export function getThumbnailUrl(size, imageUrl) {
  const sizeSuffix = normalizeThumbnailSize(size);
  if (!sizeSuffix || !imageUrl) return null;

  try {
    const rawUrl = String(imageUrl).trim();
    const url = new URL(rawUrl, `${mediaBaseUrl}/`);
    if (!url.pathname.startsWith("/gallery/")) return null;

    const mirroredPath = addThumbnailSuffix(url.pathname.slice("/gallery".length), sizeSuffix);
    if (!mirroredPath) return null;

    url.pathname = `/thumbs${mirroredPath}`;
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return null;
  }
}
