import { getImageThumbnail } from "../_data/imageHelpers.js";

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export const data = {
  layout: "main.njk",
  pagination: {
    data: "emom.artistPages",
    size: 1,
    alias: "artistPage"
  },
  eleventyComputed: {
    pageTitle: data => data.artistPage.artist.stageName
  },
  permalink: data => {
    return `artists/${data.artistPage.slug}/index.html`;
  }
};

export default async function render(data) {
  const { artistPage } = data;
  const { artist, performances, socialLinks, image } = artistPage;
  const publicContactName = artist.isNamePublic
    ? [artist.firstName, artist.lastName]
        .map((value) => (value ? String(value).trim() : ""))
        .filter(Boolean)
        .join(" ")
    : "";

  // Get artist thumbnail image
  let originalUrl = null;
  let thmUrl = null;

  if (image && image.imageURL) {
    originalUrl = String(image.imageURL).trim();
    thmUrl = await getImageThumbnail(image.imageURL, artist.stageName);
  }

  let html = "";

  // Artist thumbnail
  if (thmUrl) {
    html += `<a href="${originalUrl}"><img src="${thmUrl}" alt="${artist.stageName} thumbnail" class="artist-thumb" /></a>\n`;
  }

  // Public bio
  if (artist.isBioPublic && artist.bio) {
    const bioHtml = escapeHtml(artist.bio).replaceAll("\n", "<br />\n");
    html += `<div class="artist-bio">\n<p>${bioHtml}</p>\n</div>\n`;
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
    html += `</ul>\n`;
  } else {
    html += `<p>No performances recorded.</p>\n`;
  }

  if (artist.isEmailPublic && artist.email) {
    const safeEmail = escapeHtml(artist.email);
    const contactLabel = artist.profileType === "group"
      ? "Contact us"
      : publicContactName
        ? `Contact ${escapeHtml(publicContactName)}`
        : "Contact me";
    html += `<p>${contactLabel} via email: <a href="mailto:${safeEmail}">${safeEmail}</a></p>\n`;
  }

  html += `<p><a href="/artists/index.html">&lt;&lt; Back to all artists</a></p>\n`;

  return html;
}
