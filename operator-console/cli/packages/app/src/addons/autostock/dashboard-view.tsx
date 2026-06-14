// F79 C6 — DashboardView (FR-2/FR-7/FR-8/NFR-7). Presentational binding to the tested
// SnapshotController model (toDashboard), enriched per UAQ: per-position P&L rows, agent
// activity, market session, cash/buying power — with progressive disclosure (tap to expand
// positions / agent detail). Trading-terminal hierarchy on the host opencode tokens, so it
// rides the system light/dark theme. Logic stays in the tested core; this only renders.

import { createSignal, For, Show } from "solid-js"
import type { DashboardModel } from "./dashboard"

export type PositionRow = {
  symbol: string
  marketValue: number | null
  dayPct: number | null
  weightPct?: number | null
}
export type MarketPhase = "pre" | "regular" | "after" | "closed"
export type AgentDecision = { ts?: string; action: string; symbol?: string; summary?: string }

export type DashboardViewProps = {
  model: DashboardModel
  /** Rich rows; when present they replace the basic symbol chips. */
  positions?: PositionRow[]
  cash?: number | null
  buyingPower?: number | null
  market?: { phase: MarketPhase; label?: string; nextLabel?: string }
  agent?: { current?: string | null; recent?: AgentDecision[] }
  /** NFR-7: snapshot older than the freshness threshold. */
  stale?: boolean
  onRefresh?: () => void
  onOpenHealth?: () => void
  onOpenPosition?: (symbol: string) => void
  onOpenAgent?: () => void
}

function fmtMoney(v: number | null | undefined, opts?: { compact?: boolean }): string {
  if (v === null || v === undefined) return "—"
  return v.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    notation: opts?.compact ? "compact" : "standard",
    maximumFractionDigits: opts?.compact ? 1 : 2,
  })
}
function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—"
  return `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(2)}%`
}
const pnlClass = (v: number | null | undefined) =>
  ({ "text-icon-success-base": (v ?? 0) >= 0, "text-icon-critical-base": (v ?? 0) < 0 })

const MARKET_LABEL: Record<MarketPhase, string> = { pre: "프리마켓", regular: "정규장", after: "애프터", closed: "장마감" }

function Card(props: { children: unknown; class?: string }) {
  return (
    <section class={`rounded-xl border border-border-weak-base bg-surface-raised-base shadow-xs-border-base ${props.class ?? ""}`}>
      {props.children as never}
    </section>
  )
}
function Label(props: { children: unknown }) {
  return <span class="text-[0.6875rem] font-medium uppercase tracking-wider text-text-faint">{props.children as never}</span>
}

export function DashboardView(props: DashboardViewProps) {
  const m = () => props.model
  const [posOpen, setPosOpen] = createSignal(false)
  const [agentOpen, setAgentOpen] = createSignal(false)

  const rows = () => props.positions ?? []
  const visibleRows = () => (posOpen() ? rows() : rows().slice(0, 4))

  return (
    <div class="flex min-h-full flex-col gap-3 bg-background-base p-4">
      {/* Top bar — market session + refresh */}
      <div class="flex items-center justify-between">
        <Show when={props.market} fallback={<span />}>
          {(mk) => (
            <span class="flex items-center gap-2">
              <span
                class="size-2 rounded-full"
                classList={{
                  "bg-icon-success-base": mk().phase === "regular",
                  "bg-icon-warning-base": mk().phase === "pre" || mk().phase === "after",
                  "bg-border-weak-base": mk().phase === "closed",
                }}
              />
              <span class="text-sm font-medium text-text-strong">{mk().label ?? MARKET_LABEL[mk().phase]}</span>
              <Show when={mk().nextLabel}>
                <span class="text-xs text-text-faint">· {mk().nextLabel}</span>
              </Show>
            </span>
          )}
        </Show>
        <button
          type="button"
          class="rounded-full border border-border-weak-base px-3 py-1 text-xs font-medium text-text-weak transition active:scale-95 hover:bg-surface-raised-base-hover"
          onClick={() => props.onRefresh?.()}
        >
          ↻ 새로고침
        </button>
      </div>

      <Show when={m().offline}>
        <div class="flex items-center gap-2 rounded-md border border-border-base bg-surface-base px-3 py-2 text-sm text-text-weak">
          <span class="size-2 rounded-full bg-border-weak-base" />
          오프라인 — 서버에 연결되지 않음
        </div>
      </Show>

      {/* Hero — equity + day P&L + cash/buying power */}
      <Card class="p-5">
        <Label>총 자산</Label>
        <p class="mt-1 text-[2rem] font-semibold leading-none tabular-nums text-text-strong">{fmtMoney(m().equity)}</p>
        <p class="mt-2 text-sm font-medium tabular-nums" classList={pnlClass(m().dayPnlPct)}>
          {fmtPct(m().dayPnlPct)}
          <span class="ml-1 text-text-faint">오늘</span>
        </p>
        <Show when={props.cash !== undefined || props.buyingPower !== undefined}>
          <div class="mt-4 grid grid-cols-2 gap-3 border-t border-border-weak-base pt-3">
            <div class="flex flex-col gap-0.5">
              <Label>현금</Label>
              <span class="text-sm font-medium tabular-nums text-text-base">{fmtMoney(props.cash)}</span>
            </div>
            <div class="flex flex-col gap-0.5">
              <Label>매수여력</Label>
              <span class="text-sm font-medium tabular-nums text-text-base">{fmtMoney(props.buyingPower)}</span>
            </div>
          </div>
        </Show>
      </Card>

      {/* Pending approvals — promoted to an action card when present */}
      <Show when={(m().pendingApprovals ?? 0) > 0}>
        <button
          type="button"
          class="flex items-center justify-between rounded-xl border border-icon-interactive-base/40 bg-surface-raised-base p-4 text-left shadow-xs-border-base transition active:scale-[0.99]"
          onClick={() => props.onOpenHealth?.()}
        >
          <span class="flex items-center gap-3">
            <span class="inline-flex size-7 animate-pulse items-center justify-center rounded-full bg-icon-interactive-base text-sm font-semibold tabular-nums text-text-invert-base">
              {m().pendingApprovals}
            </span>
            <span class="flex flex-col">
              <span class="text-sm font-semibold text-text-strong">승인 대기 중</span>
              <span class="text-xs text-text-weak">탭하여 서명·처리</span>
            </span>
          </span>
          <span class="text-text-faint">›</span>
        </button>
      </Show>

      {/* Health — compact tappable */}
      <button
        type="button"
        class="flex items-center justify-between rounded-xl border border-border-weak-base bg-surface-raised-base p-4 text-left shadow-xs-border-base transition active:scale-[0.99]"
        onClick={() => props.onOpenHealth?.()}
      >
        <span class="flex items-center gap-2.5">
          <span
            class="size-2.5 rounded-full"
            classList={{
              "bg-icon-success-base": m().healthOk === true,
              "bg-icon-critical-base": m().healthOk === false,
              "bg-border-weak-base": m().healthOk === null,
            }}
          />
          <span class="text-sm font-medium text-text-strong">시스템 건강</span>
        </span>
        <span class="flex items-center gap-1.5 text-sm text-text-weak">
          {m().healthOk === null ? "—" : m().healthOk ? "정상" : "점검 필요"}
          <span class="text-text-faint">›</span>
        </span>
      </button>

      {/* Positions — rows with P&L, progressive disclosure */}
      <Card class="p-4">
        <div class="flex items-baseline justify-between">
          <Label>포지션</Label>
          <span class="text-sm font-medium tabular-nums text-text-weak">{m().positionCount}</span>
        </div>
        <Show
          when={rows().length > 0}
          fallback={
            <Show
              when={m().symbols.length > 0}
              fallback={<p class="mt-3 text-sm text-text-weak">보유 포지션 없음</p>}
            >
              <div class="mt-3 flex flex-wrap gap-2">
                <For each={m().symbols}>
                  {(sym) => (
                    <button
                      type="button"
                      class="rounded-md border border-border-weak-base bg-surface-base px-3 py-1.5 text-sm font-medium text-text-strong transition active:scale-95"
                      onClick={() => props.onOpenPosition?.(sym)}
                    >
                      {sym}
                    </button>
                  )}
                </For>
              </div>
            </Show>
          }
        >
          <ul class="mt-2 flex flex-col divide-y divide-border-weak-base">
            <For each={visibleRows()}>
              {(p) => (
                <li>
                  <button
                    type="button"
                    class="flex w-full items-center justify-between py-2.5 text-left transition active:opacity-70"
                    onClick={() => props.onOpenPosition?.(p.symbol)}
                  >
                    <span class="flex flex-col">
                      <span class="text-sm font-semibold text-text-strong">{p.symbol}</span>
                      <Show when={p.weightPct != null}>
                        <span class="text-xs tabular-nums text-text-faint">{p.weightPct!.toFixed(0)}% 비중</span>
                      </Show>
                    </span>
                    <span class="flex flex-col items-end">
                      <span class="text-sm font-medium tabular-nums text-text-base">{fmtMoney(p.marketValue)}</span>
                      <span class="text-xs font-medium tabular-nums" classList={pnlClass(p.dayPct)}>
                        {fmtPct(p.dayPct)}
                      </span>
                    </span>
                  </button>
                </li>
              )}
            </For>
          </ul>
          <Show when={rows().length > 4}>
            <button
              type="button"
              class="mt-2 w-full rounded-md py-2 text-xs font-medium text-text-weak transition active:scale-[0.98] hover:bg-surface-raised-base-hover"
              onClick={() => setPosOpen((v) => !v)}
            >
              {posOpen() ? "접기 ▴" : `+${rows().length - 4}개 더 보기 ▾`}
            </button>
          </Show>
        </Show>
      </Card>

      {/* Agent activity — collapsible recent decisions */}
      <Show when={props.agent}>
        {(ag) => (
          <Card class="p-4">
            <button type="button" class="flex w-full items-center justify-between" onClick={() => setAgentOpen((v) => !v)}>
              <span class="flex items-center gap-2">
                <Label>에이전트 활동</Label>
                <Show when={ag().current}>
                  <span class="inline-flex items-center gap-1 rounded-full bg-surface-base px-2 py-0.5 text-[0.6875rem] font-medium text-text-base">
                    <span class="size-1.5 animate-pulse rounded-full bg-icon-interactive-base" />
                    {ag().current}
                  </span>
                </Show>
              </span>
              <span class="text-text-faint">{agentOpen() ? "▴" : "▾"}</span>
            </button>

            <Show when={(ag().recent ?? []).length > 0} fallback={<p class="mt-2 text-sm text-text-weak">최근 결정 없음</p>}>
              <Show
                when={agentOpen()}
                fallback={
                  <p class="mt-2 truncate text-sm text-text-base">
                    최근: {ag().recent![0].action}
                    <Show when={ag().recent![0].symbol}> · {ag().recent![0].symbol}</Show>
                  </p>
                }
              >
                <ul class="mt-2 flex flex-col gap-2">
                  <For each={ag().recent}>
                    {(d) => (
                      <li class="flex items-start gap-2">
                        <span class="mt-1.5 size-1.5 shrink-0 rounded-full bg-border-base" />
                        <span class="flex flex-col">
                          <span class="text-sm text-text-strong">
                            {d.action}
                            <Show when={d.symbol}>
                              <span class="font-semibold"> {d.symbol}</span>
                            </Show>
                          </span>
                          <Show when={d.summary}>
                            <span class="text-xs text-text-weak">{d.summary}</span>
                          </Show>
                          <Show when={d.ts}>
                            <span class="text-[0.6875rem] tabular-nums text-text-faint">{d.ts}</span>
                          </Show>
                        </span>
                      </li>
                    )}
                  </For>
                </ul>
              </Show>
            </Show>
          </Card>
        )}
      </Show>

      {/* Footer — freshness */}
      <div class="mt-auto flex items-center justify-between pt-1 text-xs text-text-faint">
        <Show
          when={props.stale}
          fallback={<span class="tabular-nums">{m().asOf ? `갱신 ${m().asOf}` : ""}</span>}
        >
          <span class="flex items-center gap-1.5 text-icon-critical-base">
            <span class="size-1.5 animate-pulse rounded-full bg-icon-critical-base" />
            오래된 데이터 — 갱신 중
          </span>
        </Show>
      </div>
    </div>
  )
}
