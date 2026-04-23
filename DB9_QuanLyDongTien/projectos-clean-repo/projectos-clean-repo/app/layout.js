export const metadata = { title: 'ProjectOS' };
import './globals.css';

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
