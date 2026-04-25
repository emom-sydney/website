import { renderContactLine, renderProfileIntro } from "../../lib/render/profilePage.js";

function getCrewDisplayName(profile) {
  const publicName = profile.isNamePublic
    ? [profile.firstName, profile.lastName]
        .map((value) => (value ? String(value).trim() : ""))
        .filter(Boolean)
        .join(" ")
    : "";

  return publicName || profile.stageName;
}

function getVolunteerReferenceName(profile) {
  if (!profile.isNamePublic) return profile.stageName;

  const publicFirstName = profile.firstName ? String(profile.firstName).trim() : "";
  return publicFirstName || profile.stageName;
}

export const data = {
  layout: "main.njk",
  pagination: {
    data: "emom.volunteerPages",
    size: 1,
    alias: "volunteerPage"
  },
  eleventyComputed: {
    pageTitle: data => getCrewDisplayName(data.volunteerPage.profile),
    description: data => {
      const profile = data.volunteerPage.profile;
      const name = profile?.isNamePublic && profile?.firstName
        ? `${profile.firstName} ${profile.lastName || ""}`.trim()
        : profile?.stageName || "Volunteer";
      return `${name} - Volunteer crew member at sydney.emom`;
    },
    ogType: () => "profile"
  },
  permalink: data => {
    return `crew/${data.volunteerPage.slug}/index.html`;
  }
};

export default async function render(data) {
  const { volunteerPage } = data;

  let html = await renderProfileIntro(volunteerPage, {
    missingImageThumbnailUrl: data.missingImageThumbnailUrl
  });
  if (volunteerPage.artistProfile) {
    const referenceName = getVolunteerReferenceName(volunteerPage.profile);
    const artistStageName = volunteerPage.artistProfile.stageName;
    const playedAsText = referenceName === artistStageName ? "" : ` as ${artistStageName}`;
    html += `<p>${referenceName} has also played at EMOM${playedAsText}. <a href="/artists/${volunteerPage.artistProfile.slug}/index.html">Click here</a> to see their artist profile.</p>\n`;
  }
  html += renderContactLine(volunteerPage.profile);
  html += `<p><a href="/crew/index.html">&lt;&lt; Back to all crew</a></p>\n`;

  return html;
}
