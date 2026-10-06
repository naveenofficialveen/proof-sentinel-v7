import type { Viewport } from "next";
import "./globals.css";
import Bg3D from "../components/Bg3D";
export const metadata = { title: "Digital Proof Verification and Evidence Analysis System" };
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#0f131c" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
      </head>
      <body><Bg3D /><div className="app">{children}</div></body>
    </html>
  );
}
