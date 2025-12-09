export const data = {
  layout: "main.njk",
  pagination: {
    data: "artists",
    size: 1,
    alias: "artist"
  },
  permalink: data => {
    const slug = String(data.artist.stageName)
      .toLowerCase()
      .trim()
      .replace(/[^\w\s-]/g, '')
      .replace(/[\s_]+/g, '-')
      .replace(/^-+|-+$/g, '');
    return `artists/${slug}/index.html`;
  }
};

export default function render(data) {
  const { artist, performances, events, artistsocialpprofiles, socialplatforms } = data;

  // Find all performances for this artist
  const artistPerfs = [];
  for (const perf of performances) {
    if (perf.ArtistID == artist.ID) {
      artistPerfs.push(perf);
    }
  }

  // Find all social profiles for this artist
  const artistProfiles = [];
  for (const profile of artistsocialpprofiles) {
    if (profile.artistID == artist.ID) {
      artistProfiles.push(profile);
    }
  }

  // Build profile page content
  let html = `<p><a href="/artists/index.html">Back to all artists</a></p>\n`;
  html += `<h2>${artist.stageName}</h2>\n`;

  // Social media links
  if (artistProfiles.length) {
    html += `<h3>Follow</h3>\n<ul class="social-links">\n`;
    for (const profile of artistProfiles) {
      let platform = null;
      for (const p of socialplatforms) {
        if (p.ID == profile.socialPlatformID) {
          platform = p;
          break;
        }
      }
      if (platform && profile.profileName) {
        // Replace {profileName} template with actual profile name
        const url = platform.URLFormat.replace('{profileName}', profile.profileName);
        html += `<li><a href="${url}" target="_blank" rel="noopener">${platform.platformName}</a></li>\n`;
      }
    }
    html += `</ul>\n`;
  }

  // Performances
  if (artistPerfs.length) {
    html += `<h3>Performances</h3>\n<ul>\n`;
    for (const perf of artistPerfs) {
      let event = null;
      for (const e of events) {
        if (e.ID == perf.EventID) {
          event = e;
          break;
        }
      }
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

  return html;
}