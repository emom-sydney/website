import Image from "@11ty/eleventy-img";
import path from "path";
import fs from "fs";
import fsPromises from "fs/promises";

const THUMB_URL_PATH = "/assets/img/th/";
const THUMB_OUTPUT_DIR = path.resolve(process.cwd(), "_site/assets/img/th");

/**
 * Create a filesystem-safe slug from the original image URL starting at the
 * first "/gallery" occurrence. If "/gallery" is not present, fall back to a
 * slugified version of the entire URL.
 *
 * Result will not contain slashes; they are converted to dashes so the
 * thumbnail filename is a single file under assets/img/th/.
 */
function slugifyFromGallery(src) {
  if (!src) return null;
  try {
    const idx = String(src).indexOf("/gallery");
    const part = idx !== -1 ? String(src).slice(idx) : String(src);

    // remove leading slashes, convert path separators to dashes, lowercase
    let s = part.replace(/^[\/]+/, "").replace(/\//g, "-").toLowerCase();

    // replace any characters that are not alnum, dash or underscore with dash
    s = s.replace(/[^a-z0-9\-_]+/g, "-");

    // collapse repeated dashes and trim
    s = s.replace(/-+/g, "-").replace(/^-|-$/g, "");

    // safety: cap length
    if (s.length > 180) s = s.slice(0, 180);

    return s || null;
  } catch (e) {
    return null;
  }
}

export async function getImageThumbnail(imageUrl, context) {
  const result = await getImageThumbnailResult(imageUrl, context);
  return result.ok ? result.url : null;
}

export async function getImageThumbnailResult(imageUrl, context) {
  if (!imageUrl) return { ok: false, url: null, error: "missing-image-url" };

  const slugBase = slugifyFromGallery(imageUrl) || `image-${context}`;
  const thumbFilename = `${slugBase}-250.jpeg`;
  const thumbPath = path.join(THUMB_OUTPUT_DIR, thumbFilename);
  const publicThumbUrl = `${THUMB_URL_PATH}${thumbFilename}`;

  await fsPromises.mkdir(THUMB_OUTPUT_DIR, { recursive: true });

  // Check if thumbnail already exists
  if (fs.existsSync(thumbPath)) {
    return { ok: true, url: publicThumbUrl, error: null };
  }

  const options = {
    widths: [250],
    formats: ["jpeg"],
    outputDir: THUMB_OUTPUT_DIR,
    urlPath: THUMB_URL_PATH,
    // Crop to square using Sharp's fit option via the filename generation step.
    // eleventy-img will still perform resizing; the filenameFormat makes naming deterministic.
    filenameFormat: function (id, src, width, format, options) {
      // include width in name in case you later add multiple sizes
      return `${slugBase}-${width}.${format}`;
    },
    // pass transform options to sharp via `sharpOptions` (fit: cover will crop)
    sharpOptions: {
      // note: eleventy-img uses sharp internally; this instructs sharp how to resize
      // For eleventy-img versions that require `sharpOptions` to contain resize options,
      // we include them here. If your version behaves differently you can adjust.
      fit: "cover",
      position: "centre"
    }
  };

  try {
    const stats = await Image(imageUrl, options);
    // stats.jpeg[0] corresponds to width 250, format jpeg
    if (!stats || !stats.jpeg || !stats.jpeg[0] || !stats.jpeg[0].url) {
      console.warn(`Failed to generate thumbnail for ${imageUrl}: missing image stats`);
      return { ok: false, url: null, error: "missing-stats" };
    }
    return { ok: true, url: stats.jpeg[0].url, error: null };
  } catch (error) {
    console.warn(`Failed to generate thumbnail for ${imageUrl}: ${error.message}`);
    return { ok: false, url: null, error: error.message };
  }
}
