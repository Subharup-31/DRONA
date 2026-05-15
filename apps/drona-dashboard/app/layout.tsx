import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "DRONA Incident Memory",
  description: "Persistent context benchmark dashboard for incident recall and precision."
};

export default function RootLayout({
  children
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
