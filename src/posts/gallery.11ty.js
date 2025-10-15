import s3files from "../_data/s3files.js";
import prefixes from "../_data/prefixes.js";


export const data = {
  layout: "main.njk",
  pagination: {
    data: "prefixes",
    size: 1,
    alias: "prefix"
  },
  // prefix is an array of one item when size: 1
  permalink: data => {
    let prefix = Array.isArray(data.prefix) ? data.prefix[0] : data.prefix;
    prefix = prefix.replace(/\/+$/, '').replace(/\//g, '-').replace(/-+$/, '');
    const path = `gallery/${prefix}/index.html`;
    console.log('Permalink for prefix:', data.prefix, '->', path);
    return path;
  },
  prefixes
};

export default async function render(data) {
  const prefix = Array.isArray(data.prefix) ? data.prefix[0] : data.prefix;
  const files = await s3files(prefix);
  return `
    <h2>Gallery: ${prefix}</h2>
    <ul>
      ${files.map(file => `
        <li>
          ${file.icon} <a href="${file.url}">${file.key}</a> (${file.sizeFormatted})
        </li>
      `).join('')}
    </ul>
  `;
}
