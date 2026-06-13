"use client";

import { fmtMoney, fmtSignedMoney, pnlClass } from "@/lib/format";
import { useSnapshot } from "@/lib/use-snapshot";

function Card({
  label,
  value,
  valueClass = "text-ink",
  testId,
}: {
  label: string;
  value: string;
  valueClass?: string;
  testId: string;
}) {
  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-edge bg-surface-1 px-4 py-3"
    >
      <div className="text-xs uppercase tracking-wide text-ink-dim">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}

export function AccountCards() {
  const { snapshot, isLoading } = useSnapshot();

  if (!isLoading && snapshot === null) {
    return (
      <div
        data-testid="account-cards-empty"
        className="rounded-lg border border-edge bg-surface-1 p-4 text-sm text-ink-dim"
      >
        snapshot 없음 — 데몬 미가동?
      </div>
    );
  }

  const account = snapshot?.account;
  return (
    <div data-testid="account-cards" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Card label="Equity" value={fmtMoney(account?.equity)} testId="account-card-equity" />
      <Card label="Cash" value={fmtMoney(account?.cash)} testId="account-card-cash" />
      <Card label="Invested" value={fmtMoney(account?.invested)} testId="account-card-invested" />
      <Card
        label="Open P&L"
        value={fmtSignedMoney(account?.open_pnl)}
        valueClass={pnlClass(account?.open_pnl)}
        testId="account-card-open-pnl"
      />
    </div>
  );
}
