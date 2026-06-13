import { router } from "@/server/trpc";
import { portfolioRouter } from "@/server/routers/portfolio";

export const appRouter = router({
  portfolio: portfolioRouter,
});

export type AppRouter = typeof appRouter;
