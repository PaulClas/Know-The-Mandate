import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import { DEFINITION, SITE } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "KYM — Know Your Mandate: governing financial authority delegated to AI agents", template: "%s · KYM" },
  description: `${DEFINITION} Synthetic proof of concept; not certified or production-ready.`,
  keywords: ["AI agents", "agentic banking", "delegated authority", "mandate", "OAuth", "Rich Authorization Requests", "DPoP", "policy enforcement", "evidence ledger", "open banking"],
  applicationName: "KYM",
  authors: [{ name: "Paul Clas" }],
  alternates: { canonical: "/" },
  openGraph: { title: "KYM — Know Your Mandate", description: DEFINITION, type: "website", siteName: "KYM" },
  robots: { index: true, follow: true },
};

const themeScript = `try{var t=localStorage.getItem('kym.theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
