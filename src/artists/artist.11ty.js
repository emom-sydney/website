import {
  escapeHtml,
  renderContactLine,
  renderProfileIntro,
  renderPublicBio,
  renderSocialLinks,
  renderTribuoLink,
} from "../../lib/render/profilePage.js";

function getArtistReferenceName(profile) {
  if (!profile.isNamePublic) return profile.stageName;

  const publicFirstName = profile.firstName ? String(profile.firstName).trim() : "";
  return publicFirstName || profile.stageName;
}

function renderInlineSocialLinks(socialLinks) {
  if (!socialLinks?.length) return "";
  return ` <span class="artist-member-socials">${socialLinks.map((link) =>
    `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener">${escapeHtml(link.platformName)}</a>`
  ).join(" · ")}</span>`;
}

export const data = {
  layout: "main.njk",
  pagination: {
    data: "emom.artistPages",
    size: 1,
    alias: "artistPage"
  },
  eleventyComputed: {
    pageTitle: data => data.artistPage?.artist?.stageName || "Artist",
    description: data => {
      const artist = data.artistPage?.artist;
      if (!artist) return "Artist profile at sydney.emom";
      const bio = artist.isBioPublic && artist.bio
        ? artist.bio.substring(0, 150).replace(/\n/g, " ") + (artist.bio.length > 150 ? "..." : "")
        : "Electronic music performer at sydney.emom";
      return `${artist.stageName || "Artist"} - ${bio}`;
    },
    ogType: () => "profile"
  },
  permalink: data => {
    return `artists/${data.artistPage?.slug || "unknown"}/index.html`;
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
  let html = `<h2>${escapeHtml(artist.stageName)}</h2>\n`;
  html += await renderProfileIntro(profilePage, {
    missingImageThumbnailUrl: data.missingImageThumbnailUrl
  });
  html += renderPublicBio(artist);

  if (artistPage.currentMembers?.length) {
    html += `<h3>Members</h3>\n<p>${escapeHtml(artist.stageName)} is a group consisting of:</p>\n<ul class="artist-members">\n`;
    for (const member of artistPage.currentMembers) {
      html += `<li><strong>${escapeHtml(member.displayName)}</strong>`;
      if (member.roleLabel) html += ` — ${escapeHtml(member.roleLabel)}`;
      html += renderInlineSocialLinks(member.socialLinks);
      html += `</li>\n`;
    }
    html += `</ul>\n`;
  }
  if (artistPage.formerMembers?.length) {
    html += `<h3>Former members</h3>\n<ul class="artist-former-members">\n`;
    for (const member of artistPage.formerMembers) {
      html += `<li>${escapeHtml(member.displayName)}</li>\n`;
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
        if (perf.billingName && perf.billingName !== artist.stageName) {
          html += ` — performed as <strong>${escapeHtml(perf.billingName)}</strong>`;
        }
        if (perf.guestCredits?.length) {
          html += `<ul class="artist-performance-credits">`;
          for (const credit of perf.guestCredits) {
            html += `<li>${credit.creditLabel ? `${escapeHtml(credit.creditLabel)}: ` : "Featuring "}`;
            html += `<strong>${escapeHtml(credit.displayName)}</strong>`;
            html += renderInlineSocialLinks(credit.socialLinks);
            html += `</li>`;
          }
          html += `</ul>`;
        }
        html += `</li>\n`;
      }
    }
    html += `</ul>\n`;
  } else {
    html += `<p>No performances recorded.</p>\n`;
  }

  html += renderSocialLinks(socialLinks);
  html += renderTribuoLink(artist, data.emom?.tribuoBaseUrl);

  if (artistPage.volunteerProfile) {
    const referenceName = getArtistReferenceName(artist);
    html += `<p>${referenceName} also volunteers at EMOM. <a href="/crew/${artistPage.volunteerProfile.slug}/index.html">Click here</a> to see their crew profile.</p>\n`;
  }

  html += renderContactLine(artist);
  html += `<p class="artist-profile-qr">Download this profile's QR code: <a href="/api/v1/artists/${artist.ID}/qr/download.svg">SVG</a> or <a href="/api/v1/artists/${artist.ID}/qr/download.png">PNG</a>.</p>\n`;
  html += `<p><a href="/artists/index.html">&lt;&lt; Back to all artists</a></p>\n`;

  return html;
}
