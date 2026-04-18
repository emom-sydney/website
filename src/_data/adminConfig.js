export default {
  apiBase: process.env.ADMIN_API_BASE || "/api",
  presignExpires: Number(process.env.PRESIGN_EXPIRES || 1800)
};
