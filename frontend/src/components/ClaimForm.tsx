"use client";

import { useState } from "react";
import { processClaim, ClaimResult } from "@/services/claims";

export default function ClaimForm() {
    const [claimText, setClaimText] = useState("");
    const [result, setResult] = useState<ClaimResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const data = await processClaim(claimText);
            setResult(data);
        } catch (err) {
            setError("Failed to process claim. Is the backend running?");
        } finally {
            setLoading(false);
        }
    };

    const decisionColor: Record<string, string> = {
        approved: "bg-green-100 text-green-800 border-green-300",
        denied: "bg-red-100 text-red-800 border-red-300",
        manual_review: "bg-yellow-100 text-yellow-800 border-yellow-300",
        flagged_for_review: "bg-orange-100 text-orange-800 border-orange-300",
    };

    return (
        <div className="max-w-2xl mx-auto p-6">
            <h1 className="text-2xl font-semibold mb-4">Insurance Claim Intake</h1>

            <form onSubmit={handleSubmit} className="space-y-4">
                <textarea
                    className="w-full border rounded-md p-3 h-32"
                    placeholder="Describe your claim, e.g. 'My car was hit by a truck on 2025-07-15 in Mumbai. Policy XYZ123. Repair cost is 50000 rupees.'"
                    value={claimText}
                    onChange={(e) => setClaimText(e.target.value)}
                    required
                />
                <button
                    type="submit"
                    disabled={loading}
                    className="bg-blue-600 text-white px-4 py-2 rounded-md disabled:opacity-50"
                >
                    {loading ? "Processing..." : "Submit Claim"}
                </button>
            </form>

            {error && <p className="text-red-600 mt-4">{error}</p>}

            {result && (
                <div className="mt-6 space-y-4">
                    <div
                        className={`border rounded-md p-4 ${decisionColor[result.final_decision || ""] || "bg-gray-100"
                            }`}
                    >
                        <p className="font-semibold">
                            Decision: {result.final_decision}
                        </p>
                        <p>{result.response_message}</p>
                        {result.ticket_id && <p className="text-sm mt-1">Ticket: {result.ticket_id}</p>}
                    </div>

                    <details className="border rounded-md p-4 bg-gray-50">
                        <summary className="cursor-pointer font-medium">Extracted Data</summary>
                        <pre className="text-sm mt-2 overflow-x-auto">
                            {JSON.stringify(result.extracted_data, null, 2)}
                        </pre>
                    </details>

                    <details className="border rounded-md p-4 bg-gray-50">
                        <summary className="cursor-pointer font-medium">Full Pipeline Result</summary>
                        <pre className="text-sm mt-2 overflow-x-auto">
                            {JSON.stringify(result, null, 2)}
                        </pre>
                    </details>
                </div>
            )}
        </div>
    );
}