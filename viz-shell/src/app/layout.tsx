import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "autostock viz-shell",
  description: "Read-only generative dashboard sidecar",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="h-screen overflow-hidden antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
