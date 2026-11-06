"use client";

import { useEffect, useState } from "react";
import { getHouseholdClaimAges, previewClaimAges } from "@/lib/api";
import { ApiError } from "@/lib/apiError";
import type { ClaimPreview } from "@/lib/claimSetup";

type PreviewBody = Parameters<typeof previewClaimAges>[0];
type Source = { body: PreviewBody | null } | { householdId: string | null };

/** The backend's claim-age preview for an unsaved plan (debounced: it reruns
 *  as the user edits ages, salaries or Social Security answers), or for a
 *  saved one by id. `body` null = not enough input yet.
 *
 *  `preview` is the last one received and stays on screen while a refresh is
 *  in flight; `ready` says it matches the CURRENT inputs and its fetch
 *  succeeded. Anything that starts a run must check `ready`, never `preview`:
 *  a preview from before an edit (or a failed refresh) describes other inputs. */
export function useClaimPreview(source: Source): {
  preview: ClaimPreview | null;
  ready: boolean;
  loading: boolean;
  error: string | null;
} {
  const key = JSON.stringify(source);
  const [state, setState] = useState<{
    key: string | null;
    preview: ClaimPreview | null;
    error: string | null;
  }>({ key: null, preview: null, error: null });
  const [loadingKey, setLoadingKey] = useState<string | null>(null);

  useEffect(() => {
    const src = JSON.parse(key) as Source;
    const fetcher =
      "householdId" in src
        ? src.householdId
          ? () => getHouseholdClaimAges(src.householdId as string)
          : null
        : src.body
          ? () => previewClaimAges(src.body as PreviewBody)
          : null;
    if (!fetcher) return;
    let cancelled = false;
    setLoadingKey(key);
    const t = setTimeout(() => {
      fetcher()
        .then((p) => {
          if (!cancelled) setState({ key, preview: p, error: null });
        })
        .catch((e: Error) => {
          // Keep the last preview visible, but it no longer counts as current.
          if (!cancelled)
            setState((s) => ({ ...s, key, error: e instanceof ApiError ? e.detailText : e.message }));
        })
        .finally(() => {
          if (!cancelled) setLoadingKey((k) => (k === key ? null : k));
        });
    }, "householdId" in src ? 0 : 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [key]);

  const loading = loadingKey === key;
  return {
    preview: state.preview,
    ready: state.key === key && state.error == null && state.preview != null && !loading,
    loading,
    error: state.key === key ? state.error : null,
  };
}
