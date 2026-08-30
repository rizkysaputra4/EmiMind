"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { sendMagicLink, verifyMagicLink } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [debugToken, setDebugToken] = useState("");
  const [isSent, setIsSent] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSendMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;

    setIsLoading(true);
    setError(null);
    try {
      const res = await sendMagicLink(email.trim());
      setIsSent(true);
      if (res.debug_token) {
        setDebugToken(res.debug_token);
      }
    } catch (err: any) {
      setError(err.message || "Failed to send magic link");
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (tokenToUse: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await verifyMagicLink(tokenToUse);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Verification failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-slate-900/90 border border-slate-800 rounded-2xl shadow-2xl p-8 backdrop-blur space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-lg shadow-blue-500/20 text-white font-bold text-xl mb-2">
            E
          </div>
          <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">
            EmiMind Research
          </h1>
          <p className="text-xs text-slate-400">
            AI Equity Research Platform for the Indonesian Stock Exchange (IDX)
          </p>
        </div>

        {error && (
          <div className="p-3 bg-red-950/40 border border-red-800/80 rounded-xl text-xs text-red-300">
            {error}
          </div>
        )}

        {!isSent ? (
          <form onSubmit={handleSendMagicLink} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Work Email Address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="analyst@fund.co.id"
                className="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 transition"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-sm font-semibold py-2.5 px-4 rounded-xl shadow-lg shadow-blue-600/20 transition-all duration-150 disabled:opacity-50"
            >
              {isLoading ? "Sending Magic Link..." : "Sign In with Magic Link"}
            </button>
          </form>
        ) : (
          <div className="space-y-4 text-center">
            <div className="p-4 bg-emerald-950/40 border border-emerald-800/80 rounded-xl text-xs text-emerald-300">
              Magic link sent to <span className="font-semibold text-emerald-200">{email}</span>.
              Please check your inbox.
            </div>

            {debugToken && (
              <div className="p-4 bg-slate-950 border border-blue-900/50 rounded-xl space-y-2 text-left">
                <div className="text-[11px] font-semibold text-blue-400">Dev / Test Auto-Login</div>
                <div className="text-[10px] text-slate-500 font-mono break-all">{debugToken}</div>
                <button
                  onClick={() => handleVerify(debugToken)}
                  disabled={isLoading}
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold py-2 px-3 rounded-lg transition"
                >
                  Verify & Enter Workspace
                </button>
              </div>
            )}

            <button
              onClick={() => setIsSent(false)}
              className="text-xs text-slate-400 hover:text-slate-200 transition"
            >
              ← Use a different email
            </button>
          </div>
        )}

        <div className="pt-4 border-t border-slate-800/80 text-center text-[11px] text-slate-500">
          Compliant with OJK & UU PDP regulations for financial disclosure analysis.
        </div>
      </div>
    </div>
  );
}
