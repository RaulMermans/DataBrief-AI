import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataBrief AI",
  description: "Workflow-driven analytics copilot for CSV uploads.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
