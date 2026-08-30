import "./globals.css";
import type { Metadata } from "next";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = {
  title: "EmiMind — Context-Aware IDX Financial AI",
  description: "AI research platform for Indonesian Stock Exchange (IDX) issuers",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
