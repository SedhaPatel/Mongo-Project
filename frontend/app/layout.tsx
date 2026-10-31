import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Metrologic — calibration-aware agent memory",
  description:
    "Lessons carry provenance; calibration events recompute verdicts and demote only what lost its evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
