import { getThumbnailUrl } from "../media/thumbnailUrls.js";

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

export function renderTribuoLink(profile, baseUrl) {
  const tag = profile?.tribuoTag;
  const normalizedBaseUrl = String(baseUrl || "").trim();
  if (!tag || !normalizedBaseUrl) return "";

  const href = `${normalizedBaseUrl}?${encodeURIComponent(String(tag))}`;
  return `<h3>Support</h3>\n<p><a href="${escapeHtml(href)}" target="_blank" rel="noopener">Tip ${escapeHtml(profile.stageName)} via Tribuo</a></p>\n`;
}

export async function renderProfileIntro(profilePage, options = {}) {
  const { profile, socialLinks, image } = profilePage;
  const missingImageThumbnailUrl = options.missingImageThumbnailUrl || null;

  let html = "";
  let originalUrl = null;
  let thmUrl = null;

  if (image && image.imageURL) {
    originalUrl = String(image.imageURL).trim();
    thmUrl = getThumbnailUrl("sm", image.imageURL) || missingImageThumbnailUrl;
  }

  if (thmUrl) {
    html += `<a href="${originalUrl}"><img src="${thmUrl}" alt="${profile.stageName} thumbnail" class="artist-thumb" /></a>\n`;
  }

  html += renderPublicBio(profile);
  html += renderSocialLinks(socialLinks);

  return html;
}
