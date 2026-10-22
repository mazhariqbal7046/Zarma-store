import type { Metadata } from "next";
import "./globals.css";
import OrderCelebrationBridge from "./order-celebration-bridge";

export const metadata: Metadata = {
  title: "Zarma Meni Mart — Curated menswear, matched for you.",
  description: "A thoughtful Pakistani menswear shop with an AI stylist built in."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}<OrderCelebrationBridge /></body></html>;
}
