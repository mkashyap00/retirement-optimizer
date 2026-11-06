"use client";

/**
 * Portfolio holdings page (app-level, default profile).
 *
 * One job: keep your holdings current. Upload a CSV/TSV file or paste it;
 * the stored positions are shown below. Sale planning happens in context on
 * the results page ("Plan this sale" on a year), not here.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { uploadPortfolio, getPortfolio } from "@/lib/api";
import type { PortfolioUploadResponse, PortfolioSummary } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function fmtWhole(n: number): string {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function holdingBadge(hp: string): string {
  if (hp === "long_term") return "LT";
  if (hp === "short_term") return "ST";
  return "?";
}

// The documented CSV template (see User Guide → The Portfolio Sale Planner)
const CSV_TEMPLATE =
  "symbol,shares,price,cost_basis,account_type,long_term\n" +
  "VTI,500,285.10,95225,taxable,\n" +
  "AAPL,200,240.00,19040,taxable,\n" +
  "SNOW,100,180.00,21000,taxable,no\n" +
  "VTSAX,1000,132.50,,traditional,\n";

const TEMPLATE_HREF =
  "data:text/csv;charset=utf-8," + encodeURIComponent(CSV_TEMPLATE);

export default function PortfolioPage() {
  const [csvText, setCsvText] = useState("");
  const [uploadResult, setUploadResult] =
    useState<PortfolioUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [holdings, setHoldings] = useState<PortfolioSummary | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshHoldings = useCallback(async () => {
    try {
      setHoldings(await getPortfolio());
    } catch {
      // Non-fatal: the upload panel still works without the summary.
    }
  }, []);

  useEffect(() => {
    refreshHoldings();
  }, [refreshHoldings]);

  async function submitCsv(text: string) {
    if (!text.trim()) {
      setUploadError("Choose a file or paste your positions first");
      return;
    }
    setUploadLoading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const result = await uploadPortfolio(text);
      setUploadResult(result);
      await refreshHoldings();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploadLoading(false);
    }
  }

  async function handleFile(file: File) {
    const text = await file.text();
    setCsvText(text);
    await submitCsv(text);
  }

  const positions = holdings?.positions ?? [];
  const totalMarketValue = positions.reduce((s, p) => s + p.market_value, 0);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            className="mt-1 inline-block w-1 h-11 rounded-full bg-accent flex-shrink-0"
            aria-hidden="true"
          />
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-primary">
              Portfolio
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Your holdings, uploaded once and reused by every plan. To turn a
              plan year&apos;s withdrawal into a sell list, open that
              plan&apos;s results and click <strong>Plan this sale</strong>.
            </p>
          </div>
        </div>
        <Button variant="outline" asChild>
          <Link href="/">Back to Dashboard</Link>
        </Button>
      </div>

      {/* Upload */}
      <Card>
        <CardHeader>
          <CardTitle>Update your holdings</CardTitle>
          <CardDescription>
            One row per position with shares, current price, and total cost
            basis — the same cost-basis figure from the Accounts screen. A CSV
            or a range copied from Excel/Google Sheets (tab-separated) both
            work.{" "}
            <a
              href={TEMPLATE_HREF}
              download="portfolio-template.csv"
              className="font-medium text-primary underline underline-offset-2"
            >
              Download template
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values"
              className="hidden"
              aria-label="Upload positions file"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
                e.target.value = ""; // allow re-selecting the same file
              }}
            />
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadLoading}
            >
              {uploadLoading ? "Uploading…" : "Upload file"}
            </Button>
            <span className="text-xs text-muted-foreground">
              CSV or tab-separated — no pasting required
            </span>
          </div>

          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">
              …or paste instead
            </summary>
            <div className="mt-3 space-y-3">
              <textarea
                aria-label="CSV input"
                className="w-full h-40 font-mono text-xs border rounded-md p-2 resize-y"
                placeholder={
                  "symbol,shares,price,cost_basis,account_type,long_term\nVTI,500,285.10,95225,taxable,"
                }
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
              />
              <Button
                onClick={() => submitCsv(csvText)}
                disabled={uploadLoading || !csvText}
                variant="outline"
              >
                Upload pasted text
              </Button>
            </div>
          </details>

          <p className="text-xs text-muted-foreground">
            Upload the latest prices — they change daily. Your shares and cost
            basis rarely change, so you only refresh this every so often.
          </p>

          {uploadError && (
            <p className="text-sm text-destructive">{uploadError}</p>
          )}
          {uploadResult && (
            <div className="space-y-1" data-testid="upload-result">
              <p className="text-sm font-medium text-green-700">
                <span data-testid="lot-count">
                  {uploadResult.lots} lots
                </span>{" "}
                uploaded.
              </p>
              {uploadResult.warnings.length > 0 && (
                <ul className="text-sm text-amber-700 list-disc pl-4 space-y-1">
                  {uploadResult.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stored holdings */}
      {positions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Stored holdings</CardTitle>
            <CardDescription>
              {positions.length} positions ·{" "}
              {fmtWhole(totalMarketValue)} total market value
              {holdings?.uploaded_at && (
                <>
                  {" "}
                  · uploaded{" "}
                  {new Date(holdings.uploaded_at).toLocaleDateString("en-US")}
                </>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="holdings-table">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Ticker</th>
                    <th className="pb-2 pr-4">Account</th>
                    <th className="pb-2 pr-4">HP</th>
                    <th className="pb-2 pr-4 text-right">Shares</th>
                    <th className="pb-2 pr-4 text-right">Price</th>
                    <th className="pb-2 text-right">Market value</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-1 pr-4 font-medium">{p.ticker}</td>
                      <td className="py-1 pr-4">{p.account_type}</td>
                      <td className="py-1 pr-4">
                        <span className="px-1 rounded text-xs font-mono bg-gray-100 text-gray-600">
                          {holdingBadge(p.holding_period)}
                        </span>
                      </td>
                      <td className="py-1 pr-4 text-right">
                        {p.shares.toLocaleString("en-US")}
                      </td>
                      <td className="py-1 pr-4 text-right">
                        {fmtWhole(p.price)}
                      </td>
                      <td className="py-1 text-right">
                        {fmtWhole(p.market_value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
