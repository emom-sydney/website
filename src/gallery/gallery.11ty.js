import s3files from "../_data/s3files.js";
import galleries from "../_data/galleries.js";

// Build a nested tree node
const makeNode = () => ({ files: [], children: new Map() });

// Helper: sanitize part for URL path (keep letters, numbers, - and _)
const safePart = (s) => String(s).trim().replace(/[^a-zA-Z0-9-_]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');

export const data = async () => {
  // Build pages array: each page corresponds to one node (root or subfolder)
  const pages = [];

  // summary for top-level index
  const galleriesSummary = [];

  for (const gallery of galleries) {
    const files = await s3files(gallery);

    // create summary entry (safe gallery name used in URLs)
    const safeGallery = gallery.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '');
    const galleryUrl = `/gallery/${safeGallery}/index.html`;
    galleriesSummary.push({ gallery, safeGallery, url: galleryUrl });

    // Escape gallery for prefix regex
    const escGallery = gallery.replace(/[-\\/\\^$*+?.()|[\]{}]/g, "\\$&");
    const prefixRe = new RegExp(`^gallery/${escGallery}/?`);

    // Build tree: place each file in the node that corresponds to its immediate folder
    const root = makeNode();
    for (const file of files) {
      const relPath = file.key.replace(prefixRe, "");
      if (!relPath) continue;
      const parts = relPath.split("/").filter(Boolean);

      if (parts.length === 1) {
        // file is directly in the gallery root
        root.files.push(file);
      } else {
        // put the file into the node representing its immediate parent folder
        let node = root;
        for (let i = 0; i < parts.length - 1; i++) {
          const part = parts[i];
          if (!node.children.has(part)) node.children.set(part, makeNode());
          node = node.children.get(part);
        }
        node.files.push(file);
      }
    }

    // Traverse tree to emit a page entry for every node (root + each subfolder)
    function traverse(node, pathParts = []) {
      const safeParts = pathParts.map(p => safePart(p));
      const folderPath = safeParts.length ? `${safeParts.join('/')}/` : '';
      const permalink = `gallery/${safeGallery}/${folderPath}index.html`.replace(/\/{2,}/g, '/');

      // immediate children names only
      const children = Array.from(node.children.keys());

      pages.push({
        gallery,
        safeGallery,
        pathParts: [...pathParts], // original folder names (human readable)
        files: node.files,         // files directly in this folder only
        children,                  // immediate child folder names
        permalink
      });

      // Emit a separate page for each child folder
      for (const [childName, childNode] of node.children) {
        traverse(childNode, [...pathParts, childName]);
      }
    }

    traverse(root, []);
  }

  // Add top-level gallery index page (lists all galleries)
  pages.unshift({
    topIndex: true,
    galleries: galleriesSummary,
    permalink: "gallery/index.html"
  });

  return {
    layout: "main.njk",
    pagination: {
      data: "pages",
      size: 1,
      alias: "page"
    },
    // ensure each paginated item controls its own output path
    permalink: data => data.page.permalink,
    pages
  };
};

export default function render(data) {
  const page = data.page;

  // Top-level /gallery/index.html -> list of galleries
  if (page.topIndex) {
    const list = (page.galleries || []).map(g => `<li><a href="${g.url}">${g.gallery}</a></li>`).join("");
    return `<h2>Galleries</h2>\n<ul>\n${list}\n</ul>\n`;
  }

  // folder page rendering (gallery or subfolder)
  const { gallery, safeGallery, pathParts = [], files = [], children = [] } = page;

  // human readable heading
  const heading = pathParts.length ? `${gallery} / ${pathParts.join(' / ')}` : gallery;

  // Build breadcrumb trail:
  // - "Galleries" -> /gallery/index.html
  // - gallery -> /gallery/<safeGallery>/index.html
  // - then each subfolder level
  const crumbs = [];
  crumbs.push({ name: "Galleries", url: "/gallery/index.html" });
  crumbs.push({ name: gallery, url: `/gallery/${safeGallery}/index.html` });

  const safeAcc = [];
  for (let i = 0; i < (pathParts || []).length; i++) {
    const part = pathParts[i];
    safeAcc.push(safePart(part));
    const url = `/gallery/${safeGallery}/${safeAcc.join('/')}/index.html`;
    crumbs.push({ name: part, url });
  }

  // Render breadcrumbs: all but the last are links, last is plain text
  const bcHtml = crumbs.map((c, idx) => {
    const isLast = idx === crumbs.length - 1;
    return isLast ? `<span>${c.name}</span>` : `<a href="${c.url}">${c.name}</a>`;
  }).join(' &gt; ');

  let html = `<p class="breadcrumbs">${bcHtml}</p>\n`;
  html += `<h2>Gallery: ${heading}</h2>\n`;

  // First: list files directly in this folder (media files)
  if (files && files.length) {
    html += `<h3>Files</h3>\n<ul class="galleryList">\n`;
    html += files.map(f => `
      <li>
        ${f.icon || ""} <a href="${f.url}">${f.name}</a>${f.sizeFormatted ? ` (${f.sizeFormatted})` : ""}
      </li>
    `).join("");
    html += `\n</ul>\n`;
  } else {
    html += `<p>No files in this folder.</p>\n`;
  }

  // Then: links to immediate child folders (each child has its own index.html page)
  if (children && children.length) {
    html += `<h3>Subfolders</h3>\n<ul>\n`;
    for (const child of children) {
      const parts = [...pathParts, child];
      const safeParts = parts.map(p => safePart(p));
      const childUrl = `/gallery/${safeGallery}/${safeParts.join('/')}/index.html`;
      html += `<li><a href="${childUrl}">${child}</a></li>\n`;
    }
    html += `</ul>\n`;
  }

  return html;
}