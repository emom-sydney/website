import s3files from "../_data/s3files.js";
import galleries from "../_data/galleries.js";

export const data = async () => {
  // Build a list of { gallery, safeGallery, sub, files }
  const pages = [];

  for (const gallery of galleries) {
    const files = await s3files(gallery);

    // Group files by subfolder
    const subfolders = {};
    for (const file of files) {
      const relPath = file.key.replace(new RegExp(`^gallery/${gallery.replace(/[-\\/\\^$*+?.()|[\]{}]/g,'\\$&')}/?`), "");
      if (relPath.includes("/")) {
        const [sub, ...rest] = relPath.split("/");
        if (!subfolders[sub]) subfolders[sub] = [];
        subfolders[sub].push({ ...file, subPath: rest.join("/") });
      }
    }

    const safeGallery = gallery.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '');
    for (const sub of Object.keys(subfolders)) {
      pages.push({ gallery, safeGallery, sub, files: subfolders[sub] });
    }
  }

  return {
    layout: "main.njk",
    pagination: {
      data: "pages",
      size: 1,
      alias: "page"
    },
    // Ensure output goes into the gallery folder rather than posts/
    permalink: data => {
      const g = data.page && data.page.safeGallery ? data.page.safeGallery : '';
      const s = data.page && data.page.sub ? data.page.sub : '';
      // sanitize
      const safeG = String(g).replace(/[^a-zA-Z0-9-_]/g, '-');
      const safeS = String(s).replace(/[^a-zA-Z0-9-_]/g, '-');
      return `gallery/${safeG}/${safeS}/index.html`;
    },
    // pages is the array we built above
    pages
  };
};

export default function render(data) {
  const { gallery, safeGallery, sub, files } = data.page;

  let html = `<h2>Gallery: ${gallery} / ${sub}</h2>`;
  html += `<p><a href="/gallery/${safeGallery}/index.html">Back to gallery index</a></p>`;

  html += `<ul>`;
  html += files.map(file => `
    <li class="galleryList">
      ${file.icon || ''} <a href="${file.url}">${file.name}</a> (${file.sizeFormatted})
    </li>
  `).join('');
  html += `</ul>`;

  return html;
}
