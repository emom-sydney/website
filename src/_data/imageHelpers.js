import Image from "@11ty/eleventy-img";
import path from "path";
import fs from "fs";

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
  if (!imageUrl) return null;

  const slugBase = slugifyFromGallery(imageUrl) || `image-${context}`;
  const thumbDir = "./assets/img/th/";
  const thumbFilename = `${slugBase}-250.jpeg`;
  const thumbPath = path.join(thumbDir, thumbFilename);

  // Check if thumbnail already exists
  if (fs.existsSync(thumbPath)) {
    return `/assets/img/th/${thumbFilename}`;
  }

  const options = {
    widths: [250],
    formats: ["jpeg"],
    outputDir: thumbDir,
    urlPath: "/assets/img/th/",
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

  const stats = await Image(imageUrl, options);
  // stats.jpeg[0] corresponds to width 250, format jpeg
  const thumb = stats.jpeg && stats.jpeg[0];
  return thumb ? thumb.url : null;
}