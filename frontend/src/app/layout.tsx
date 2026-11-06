import type { Metadata } from "next";
import localFont from "next/font/local";
import { AppHeader } from "@/components/AppHeader";
import "./globals.css";

// Fonts are SELF-HOSTED, not fetched from Google at build time.
//
// `next/font/google` downloads the woff2 during `next build`. Because
// scripts/start.sh wipes .next (and with it Next's font cache) on every run,
// every single start re-hit fonts.gstatic.com — so one flaky moment on the
// network failed the whole build with ETIMEDOUT and the app would not start.
// A local-first tool should not need the internet to boot.
//
// These are the latin-subset variable files (weight 400-700) pulled from
// Google Fonts once and committed. To refresh, re-download the last (latin)
// woff2 from:
//   https://fonts.googleapis.com/css2?family=Sora:wght@400..700
//   https://fonts.googleapis.com/css2?family=Manrope:wght@400..700
// requested with a browser User-Agent (otherwise Google serves .ttf).

// ── Display face: Sora ───────────────────────────────────────────────────────
const sora = localFont({
  src: "../fonts/sora.woff2",
  weight: "400 700", // variable range
  variable: "--font-display",
  display: "swap",
});

// ── Body face: Manrope ───────────────────────────────────────────────────────
const manrope = localFont({
  src: "../fonts/manrope.woff2",
  weight: "400 700", // variable range
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Retirement Planning Wizard",
  description:
    "Model Roth conversions, Social Security timing, and withdrawal sequencing to maximize after-tax wealth in retirement.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sora.variable} ${manrope.variable}`}>
      <body className="font-sans min-h-screen bg-background text-foreground antialiased">
        <AppHeader />
        <main className="max-w-6xl mx-auto px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
