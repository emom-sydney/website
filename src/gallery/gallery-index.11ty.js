import galleries from "../_data/galleries.js";

export const data = {
  layout: "main.njk",
  permalink: "gallery/index.html"
};

export default function render() {
  return `
    <h2>All Galleries</h2>
    <ul>
      ${galleries.map(gallery => `
        <li>
          <a href="/gallery/${gallery.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '')}/index.html">${gallery}</a>
        </li>
      `).join('')}
    </ul>
  `;
}
