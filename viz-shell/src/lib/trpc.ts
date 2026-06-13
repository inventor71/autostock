import { createTRPCReact } from "@trpc/react-query";

import type { AppRouter } from "@/server/routers/_app";

/** Typed client hooks — the ONLY data access path for seed and generated views (BR-11). */
export const trpc = createTRPCReact<AppRouter>();
