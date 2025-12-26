import "./globals.css";

export const metadata = {
  title: "EnTrus Arts — House of Alignment",
  description: "Where your frequency becomes your power.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
