import { getImageThumbnail } from "../_data/imageHelpers.js";

export const data = {
  layout: "main.njk",
  pagination: {
    data: "emom.artistPages",
    size: 1,
    alias: "artistPage"
  },
  permalink: data => {
    return `artists/${data.artistPage.slug}/index.html`;
  }
};

export default async function render(data) {
  const { artistPage } = data;
  const { artist, performances, socialLinks, image } = artistPage;

  // Get artist thumbnail image
  let originalUrl = null;
  let thmUrl = null;

  if (image && image.imageURL) {
    originalUrl = String(image.imageURL).trim();
    thmUrl = await getImageThumbnail(image.imageURL, artist.stageName);
  }

  // Build profile page content
  let html = `<h2>${artist.stageName}</h2>\n`;

  // Artist thumbnail
  if (thmUrl) {
    html += `<a href="${originalUrl}"><img src="${thmUrl}" alt="${artist.stageName} thumbnail" class="artist-thumb" /></a>\n`;
  }

  // Social media links
  if (socialLinks.length) {
    html += `<h3>Follow</h3>\n<ul class="social-links">\n`;
    for (const socialLink of socialLinks) {
      html += `<li><a href="${socialLink.url}" target="_blank" rel="noopener">${socialLink.platformName}</a></li>\n`;
    }
    html += `</ul>\n`;
  }

  // Performances
  if (performances.length) {
    html += `<h3>Performances</h3>\n<ul>\n`;
    for (const perf of performances) {
      const { event } = perf;
      if (event) {
        html += `<li>`;
        if (event.GalleryURL) {
          html += `<a href="/gallery/${event.GalleryURL}/index.html">${event.EventName}</a>`;
        } else {
          html += event.EventName;
        }
        html += `</li>\n`;
      }
    }
    html += `</ul>\n<p><a href="/artists/index.html">&lt;&lt; Back to all artists</a></p>\n`;
  } else {
    html += `<p>No performances recorded.</p>\n`;
  }

  return html;
}
