import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Use the bundled Geist fonts that create-next-app shipped — no Google
// runtime fetch (would break offline / static-export end-users).
const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "FaroAI",
  description: "FaroLatino A&R assistant",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="light">
      <body
        className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased`}
      >
        <div className="wordmark">FaroLatino</div>
        {children}
      </body>
    </html>
  );
}
