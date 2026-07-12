import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "爸妈求证 · Parent Check",
  description:
    "Paste a suspicious message, link or health ad and get a plain-language scam-risk check.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
