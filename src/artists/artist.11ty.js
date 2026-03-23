import { renderContactLine, renderProfileIntro } from "../../lib/render/profilePage.js";

function getArtistReferenceName(profile) {
  if (!profile.isNamePublic) return profile.stageName;

  const publicFirstName = profile.firstName ? String(profile.firstName).trim() : "";
  return publicFirstName || profile.stageName;
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
  const profilePage = {
    profile: artist,
    socialLinks,
    image,
  };
  let html = await renderProfileIntro(profilePage);

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

  if (artistPage.volunteerProfile) {
    const referenceName = getArtistReferenceName(artist);
    html += `<p>${referenceName} also volunteers at EMOM. <a href="/crew/${artistPage.volunteerProfile.slug}/index.html">Click here</a> to see their crew profile.</p>\n`;
  }

  html += renderContactLine(artist);
  html += `<p><a href="/artists/index.html">&lt;&lt; Back to all artists</a></p>\n`;

  return html;
}
