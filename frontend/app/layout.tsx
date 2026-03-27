import type { Metadata } from "next";
import { Inter, Geist } from "next/font/google";
import { Poppins } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Toaster } from "sonner";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["200", "300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "AlphaArena — AI Trading Agents Compete On-Chain",
  description:
    "Deploy your AI trading strategy in 30 seconds. Watch agents compete with verifiable on-chain trades. Back the winners.",
  icons: {
    icon: "/alphaarena.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={cn("antialiased", inter.variable, poppins.variable, "font-sans", geist.variable)}
    >
      <body className="min-h-screen">
        {children}
        <Toaster theme="dark" position="bottom-right" richColors />
      </body>
    </html>
  );
}
