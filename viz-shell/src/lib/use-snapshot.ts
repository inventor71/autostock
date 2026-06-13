"use client";

import { trpc } from "@/lib/trpc";
import type { Snapshot } from "@/server/schemas";

/**
 * Shared snapshot query. tRPC's JSON-serialize type mapping flattens the loose
 * zod object — the wire shape is exactly the schema's, so re-assert it here
 * once instead of in every consumer.
 */
export function useSnapshot(): {
  snapshot: Snapshot | null | undefined;
  isLoading: boolean;
} {
  const { data, isLoading } = trpc.portfolio.snapshot.useQuery();
  return { snapshot: data as Snapshot | null | undefined, isLoading };
}
