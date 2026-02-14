import "./globals.css";

export const metadata = {
  title: "Video Speedup",
  description: "Minimal UI for video speedup and action timeline"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
