import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Startup Analyzer — CVF",
  description: "Composite VC Framework startup evaluator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
