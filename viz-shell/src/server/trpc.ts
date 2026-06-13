import { initTRPC } from "@trpc/server";

const t = initTRPC.create();

export const router = t.router;
/**
 * viz-shell is read-only: routers expose ONLY `publicProcedure.query(...)`.
 * There is intentionally no mutation helper exported from this module (BR-6).
 */
export const publicProcedure = t.procedure;
