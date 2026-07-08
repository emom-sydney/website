// Base URL for gallery media hosted on the dedicated media server.
export default (process.env.MEDIA_BASEURL || "https://media.emom.me:909").replace(/\/+$/, "");
