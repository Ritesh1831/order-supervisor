import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Order Supervisor",
  description: "Long-running AI supervisor for orders",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="border-b bg-white">
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
            <Link href="/" className="font-semibold text-slate-900">
              Order Supervisor
            </Link>
            <Link href="/" className="text-sm text-slate-600 hover:text-slate-900">
              Runs
            </Link>
            <Link href="/supervisors" className="text-sm text-slate-600 hover:text-slate-900">
              Supervisors
            </Link>
            <a
              href="http://localhost:8233"
              target="_blank"
              className="ml-auto text-sm text-slate-400 hover:text-slate-700"
            >
              Temporal UI ↗
            </a>
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
