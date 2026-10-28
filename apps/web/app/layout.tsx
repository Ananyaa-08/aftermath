import type { Metadata } from "next";
import "./globals.css";
import localFont from "next/font/local";
const editorial = localFont({ src: "./fonts/Fraunces.ttf", variable: "--editorial", display: "swap", weight: "100 900" });

export const metadata: Metadata = { title: "AFTERMATH · Living knowledge", description: "Selective semantic revalidation — foundation workspace." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={editorial.variable}><body>{children}</body></html>;
}
