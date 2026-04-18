import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chapter One",
  description: "It all starts with Chapter One — AI-grounded idea analysis for you and your friends.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
