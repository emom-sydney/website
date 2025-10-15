import { S3Client, ListObjectsV2Command } from "@aws-sdk/client-s3";

const s3 = new S3Client({ region: "ap-southeast-2" });
const BUCKET = "sydney.emom.me";

// Map file extensions to emoji HTML entities
const typeMapping = {
  mp4: "&#x1F3A5;", // Movie camera emoji
  mov: "&#x1F3A5;",
  mkv: "&#x1F3A5;",
  mp3: "&#x1F508;", // Loudspeaker emoji
  wav: "&#x1F508;",
  flac: "&#x1F508;",
  jpg: "&#x1F5BC;", // Picture emoji
  jpeg: "&#x1F5BC;",
  png: "&#x1F5BC;",
  gif: "&#x1F5BC;",
  pdf: "&#x1F4DA;", // Book emoji
  doc: "&#x1F4DA;",
  txt: "&#x1F4DA;"
};

function formatSize(bytes) {
  if (bytes >= 1073741824) {
    return (bytes / 1073741824).toFixed(2) + ' GB';
  } else {
    return (bytes / 1048576).toFixed(2) + ' MB';
  }
}

export default async function(prefix) {
  const params = {
    Bucket: BUCKET,
    Prefix: `gallery/${prefix}`,
  };
  const command = new ListObjectsV2Command(params);
  const data = await s3.send(command);
  return (data.Contents || []).map(obj => {
    const ext = obj.Key.split('.').pop().toLowerCase();
    return {
      key: obj.Key,
      size: obj.Size,
      sizeFormatted: formatSize(obj.Size),
      lastModified: obj.LastModified,
      url: `https://${BUCKET}.s3.amazonaws.com/${obj.Key}`,
      ext,
      icon: typeMapping[ext] || ''
    };
  });
}