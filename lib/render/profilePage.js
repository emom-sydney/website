import { getImageThumbnail } from "../../src/_data/imageHelpers.js";

export function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function getPublicContactName(profile) {
  if (!profile?.isNamePublic) return "";

  return [profile.firstName, profile.lastName]
    .map((value) => (value ? String(value).trim() : ""))
    .filter(Boolean)
    .join(" ");
}

export function renderPublicBio(profile) {
  if (!profile?.isBioPublic || !profile?.bio) return "";

  const bioHtml = escapeHtml(profile.bio).replaceAll("\n", "<br />\n");
  return `<div class="artist-bio">\n<p>${bioHtml}</p>\n</div>\n`;
}

export function renderSocialLinks(socialLinks) {
  if (!socialLinks?.length) return "";

  let html = `<h3>Follow</h3>\n<ul class="social-links">\n`;
  for (const socialLink of socialLinks) {
    html += `<li><a href="${socialLink.url}" target="_blank" rel="noopener">${socialLink.platformName}</a></li>\n`;
  }
  html += `</ul>\n`;
  return html;
}

export function renderContactLine(profile) {
  if (!profile?.isEmailPublic || !profile?.email) return "";

  const safeEmail = escapeHtml(profile.email);
  const publicContactName = getPublicContactName(profile);
  const contactLabel = profile.profileType === "group"
    ? "Contact us"
    : publicContactName
      ? `Contact ${escapeHtml(publicContactName)}`
      : "Contact me";

  return `<p>${contactLabel} via email: <a href="mailto:${safeEmail}">${safeEmail}</a></p>\n`;
}

export async function renderProfileIntro(profilePage) {
  const { profile, socialLinks, image } = profilePage;

  let html = "";
  let originalUrl = null;
  let thmUrl = null;

  if (image && image.imageURL) {
    originalUrl = String(image.imageURL).trim();
    thmUrl = await getImageThumbnail(image.imageURL, profile.stageName);
  }

  if (thmUrl) {
    html += `<a href="${originalUrl}"><img src="${thmUrl}" alt="${profile.stageName} thumbnail" class="artist-thumb" /></a>\n`;
  }

  html += renderPublicBio(profile);
  html += renderSocialLinks(socialLinks);

  return html;
}
