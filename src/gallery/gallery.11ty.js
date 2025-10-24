import s3files from "../_data/s3files.js";
import galleries from "../_data/galleries.js";


export const data = {
  layout: "main.njk",
  pagination: {
    data: "galleries",
    size: 1,
    alias: "gallery"
  },
  // gallery is an array of one item when size: 1
  permalink: data => {
    let gallery = Array.isArray(data.gallery) ? data.gallery[0] : data.gallery;
    gallery = gallery.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '');
    const path = `gallery/${gallery}/index.html`;
    return path;
  }
};

export default async function render(data) {

  const gallery = Array.isArray(data.gallery) ? data.gallery[0] : data.gallery;
  const files = await s3files(gallery);

  // Group files by subfolder (or root)
  const rootFiles = [];
  const subfolders = {};
  for (const file of files) {
    // Remove the gallery prefix from the key
    const relPath = file.key.replace(/^gallery\/[\w-]+\/?/, "");
    if (!relPath.includes("/")) {
      console
      rootFiles.push(file);
    } else {
      const [sub, ...rest] = relPath.split("/");
      if (!subfolders[sub]) subfolders[sub] = [];
      subfolders[sub].push({ ...file, subPath: rest.join("/") });
    }
  }

  // Render root files
  let html = `<h2>Gallery: ${gallery}</h2>`;
  html += `<p><a href="/gallery/index.html">Back to galleries index</a></p>\n<ul class="galleryList">`;
  html += rootFiles.map(file => `
    <li>
    ${file.icon} <a href="${file.url}">${file.name}</a> (${file.sizeFormatted})
    </li>
    `).join("");
    html += `</ul>`;
    
    // Render subfolder links
    if (Object.keys(subfolders).length > 0) {
      html += `<h3>Subfolders</h3>\n<ul>`;
      html += Object.keys(subfolders).map(sub => `
        <li><a href="/gallery/${gallery}/${sub}/index.html">${sub}</a></li>
      `).join("");
      html += `</ul>`;
    }
  
  return html;
  }