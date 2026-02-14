import "./globals.css";

export const metadata = {
  title: "Personalized Ad Generator",
  description: "Create personalized ad cuts, variants, and highlights from your footage."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
