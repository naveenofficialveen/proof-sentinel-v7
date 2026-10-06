const RAW = process.env.NEXT_PUBLIC_API_URL;
// "same-origin" = the API is served from the same domain under /api (used when hosted behind Caddy)
function apiBase(): string {
  if (RAW === "same-origin") return "";
  const url = RAW || "http://localhost:8000";
  if (typeof window !== "undefined") {
    const h = window.location.hostname;  // opened as http://192.168.x.x:3000 from a phone: call the API on that same machine
    if (h !== "localhost" && h !== "127.0.0.1" && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(url)) return `${window.location.protocol}//${h}:8000`;
  }
  return url;
}
export const API = apiBase();

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(API + path, {
    credentials: "include", ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!res.ok) {
    let d: any = "Request failed";
    try { d = (await res.json()).detail ?? d; } catch {}
    if (d === "ACCOUNT_LOCKED" && typeof window !== "undefined") window.dispatchEvent(new Event("account-locked"));
    throw new Error(typeof d === "string" ? d : "Please check the values you entered");
  }
  return res.json();
}
export const post = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export function uploadFile(file: File, onProgress: (p: number) => void): Promise<any> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", API + "/api/evidence");
    x.withCredentials = true;
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    x.onload = () => {
      let b: any = {};
      try { b = JSON.parse(x.responseText); } catch {}
      if (x.status < 300) resolve(b);
      else {
        if (b.detail === "ACCOUNT_LOCKED") window.dispatchEvent(new Event("account-locked"));
        reject(new Error(typeof b.detail === "string" ? b.detail : "Upload failed"));
      }
    };
    x.onerror = () => reject(new Error("Network error"));
    const fd = new FormData(); fd.append("file", file); x.send(fd);
  });
}
