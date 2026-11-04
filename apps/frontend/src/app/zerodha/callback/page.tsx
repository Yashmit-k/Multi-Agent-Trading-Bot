"use client";

import { useEffect, useState } from "react";
import { PageFrame } from "@/components/shell/PageFrame";

// Zerodha sends the browser here after its login page (the redirect URL of the Kite Personal app).
export default function ZerodhaCallbackPage() {
  const [message, setMessage] = useState("Finishing the Zerodha login…");
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("request_token");
    // The one-time token should not stay in the address bar or the browser history.
    window.history.replaceState(null, "", "/zerodha/callback");
    if (params.get("status") !== "success" || !token) {
      setMessage("Zerodha did not complete the login. Go back to Settings and try again.");
      return;
    }
    fetch("/api/zerodha/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_token: token }) })
      .then(async (response) => {
        if (response.ok) {
          window.location.replace("/settings?zerodha=connected");
          return;
        }
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        setMessage(
          body.detail === "operator_login_required"
            ? "Sign in to this site as the operator first (Settings), then log in to Zerodha again."
            : `The Zerodha login failed (${(body.detail ?? "unknown").replaceAll("_", " ")}). Try again from Settings.`,
        );
      })
      .catch(() => setMessage("The site could not be reached. Try again from Settings."));
  }, []);
  return (
    <PageFrame title="Zerodha login">
      <p className="text-sm text-[#94A3B8]">{message}</p>
      <a href="/settings" className="mt-3 inline-block text-sm text-[#93C5FD] underline">Back to Settings</a>
    </PageFrame>
  );
}
