import "./globals.css";

export const metadata = {
  title: "AgentFlow Dashboard",
  description: "Adaptive multi-agent workflow orchestration platform for software engineering artifacts.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
