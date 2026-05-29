import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "World Cup Predictor — 2026",
  description:
    "Dixon-Coles probability model for the 2026 FIFA World Cup. Updated daily from international match results.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
