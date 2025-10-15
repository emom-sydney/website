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
  return `
    <h2>Gallery: ${gallery}</h2>
    <ul>
      ${files.map(file => `
        <li>
          ${file.icon} <a href="${file.url}">${file.name}</a> (${file.sizeFormatted})
        </li>
      `).join('')}
    </ul>
  `;
}
