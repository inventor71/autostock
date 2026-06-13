import { fetchRequestHandler } from "@trpc/server/adapters/fetch";

import { appRouter } from "@/server/routers/_app";

const handler = (req: Request) =>
  fetchRequestHandler({
    endpoint: "/api/trpc",
    req,
    router: appRouter,
    createContext: () => ({}),
  });

// Read-only API: only GET is exported for queries; tRPC httpBatchLink sends
// queries as GET when methodOverride is unset and we keep POST for batched
// query payloads (still queries — the router has no mutations, BR-6).
export { handler as GET, handler as POST };
