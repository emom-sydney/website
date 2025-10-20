import { getActiveGalleries } from "../_data/s3files.js";

export const data = {
  layout: "main.njk",
  permalink: "gallery/index.html"
};

export default async function render() {
  const galleries = await getActiveGalleries();
  console.log('Gallery Index: Found active galleries:', galleries);

  let html = `<h2>Photo Galleries</h2>`;
  
  if (galleries.length === 0) {
    html += `<p>No galleries available at this time.</p>`;
  } else {
    html += `<ul class="gallery-list">`;
    html += galleries.map(gallery => {
      const safeGallery = gallery.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '');
      return `
        <li>
          <a href="/gallery/${safeGallery}/index.html">${gallery}</a>
        </li>
      `;
    }).join('');
    html += `</ul>`;
  }

  return html;
}