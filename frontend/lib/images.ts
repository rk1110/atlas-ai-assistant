/**
 * Images attached to a chat message (Phase 6).
 *
 * The browser reads the file and sends it as base64 inside the JSON body. Simple, and fine for
 * screenshots of a few MB. The backend checks the real type from the bytes and the size limit
 * from config/multimodal.yaml; the checks here only give a quicker, friendlier message.
 */

import { BROWSER_API_URL } from "@/lib/api";

export const ACCEPTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
export const MAX_IMAGES = 3; // mirrors images.max_per_message in config/multimodal.yaml
const MAX_MB = 5; // mirrors images.max_mb

export interface AttachedImage {
  id: string;
  mediaType: string;
  /** What <img> shows: a data URL while composing, the backend URL for saved messages. */
  url: string;
  /** Base64 without the "data:...;base64," prefix. Only set before sending. */
  data?: string;
  /** What the vision model saw (saved messages). */
  description?: string | null;
}

/** Read a picked, pasted or dropped file. Throws an Error with a message for the user. */
export async function readImageFile(file: File): Promise<AttachedImage> {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
    throw new Error("Only PNG, JPEG, WebP and GIF images can be attached.");
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    throw new Error(`Images can be at most ${MAX_MB} MB.`);
  }
  const url = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Couldn't read that image."));
    reader.readAsDataURL(file);
  });
  return { id: crypto.randomUUID(), mediaType: file.type, url, data: url.slice(url.indexOf(",") + 1) };
}

/** A saved image, served by GET /api/images/{id}. */
export function storedImage(image: { id: string; media_type: string; description: string | null }): AttachedImage {
  return {
    id: image.id,
    mediaType: image.media_type,
    url: `${BROWSER_API_URL}/api/images/${image.id}`,
    description: image.description,
  };
}
