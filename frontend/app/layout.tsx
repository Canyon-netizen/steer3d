import "./globals.css";

export const metadata = {
  title: "Steering3D",
  description: "Vector intervention × 3-D reasoning visualization",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}