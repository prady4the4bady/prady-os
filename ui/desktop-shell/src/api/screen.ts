import type { ScreenSnapshot } from "../types";

async function decodeFromActionApi(): Promise<ScreenSnapshot> {
  const res = await fetch("/screen/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "screenshot", format: "png", quality: 85 }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const data = (await res.json()) as { screenshot_base64?: string };
  return {
    imageBase64: data.screenshot_base64 ?? "",
    ocrText: [],
  };
}

export async function getLatestScreenshot(): Promise<ScreenSnapshot> {
  // First attempt a direct latest endpoint; fallback to generic action endpoint.
  const direct = await fetch("/screen/latest");
  if (direct.ok) {
    const payload = (await direct.json()) as {
      image_base64?: string;
      imageBase64?: string;
      ocr?: string[];
      ocrText?: string[];
    };
    return {
      imageBase64: payload.imageBase64 ?? payload.image_base64 ?? "",
      ocrText: payload.ocrText ?? payload.ocr ?? [],
    };
  }
  return decodeFromActionApi();
}
