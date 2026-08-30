"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Cpu, MessageSquare, Upload as UploadIcon } from "lucide-react";
import React from "react";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/upload", label: "Upload", icon: UploadIcon },
];

export default function AppShellLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-950 text-slate-100">
      <header className="shrink-0 border-b border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="flex items-center justify-between px-6 py-2.5">
          <Link href="/chat" className="flex items-center space-x-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 shadow-md shadow-blue-500/20">
              <Cpu className="h-4 w-4 text-white" />
            </div>
            <span className="text-base font-bold tracking-tight text-white">EmiMind</span>
          </Link>

          <nav className="flex items-center space-x-1 rounded-full border border-slate-800 bg-slate-950/50 p-1">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname?.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center space-x-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                    active
                      ? "bg-blue-600 text-white"
                      : "text-slate-400 hover:text-slate-100"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{label}</span>
                </Link>
              );
            })}
          </nav>

          <a
            href="/login"
            className="rounded-lg border border-slate-700 bg-slate-800/70 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-slate-700"
          >
            Sign In
          </a>
        </div>
      </header>

      <div className="flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
