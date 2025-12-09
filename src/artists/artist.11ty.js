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
  const { artist, performances, events } = data;

  // Find all performances for this artist
  const artistPerfs = [];
  for (const perf of performances) {
    if (perf.ArtistID == artist.ID) {
      artistPerfs.push(perf);
    }
  }

  // Build event list with links
  let html = `<p><a href="/artists/index.html">Back to all artists</a></p>\n`;
  html += `<h2>${artist.stageName}</h2>\n`;

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