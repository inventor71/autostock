// @ts-nocheck
import { DashboardView } from "./dashboard-view"

const Phone = (props) => (
  <div style={{ width: "390px", height: "780px", overflow: "auto", border: "1px solid #8884", "border-radius": "24px" }}>
    {props.children}
  </div>
)

const model = {
  equity: 128_430.55,
  dayPnlPct: 1.24,
  positionCount: 6,
  symbols: ["AAPL", "TSLA", "NVDA", "MSFT", "AMD", "GOOGL"],
  healthOk: true,
  pendingApprovals: 0,
  asOf: "2026-06-14T14:02:11Z",
  offline: false,
}

const positions = [
  { symbol: "NVDA", marketValue: 41_220, dayPct: 3.8, weightPct: 32 },
  { symbol: "AAPL", marketValue: 31_140, dayPct: 1.1, weightPct: 24 },
  { symbol: "MSFT", marketValue: 22_010, dayPct: 0.4, weightPct: 17 },
  { symbol: "TSLA", marketValue: 16_980, dayPct: -2.3, weightPct: 13 },
  { symbol: "AMD", marketValue: 9_640, dayPct: -0.7, weightPct: 8 },
  { symbol: "GOOGL", marketValue: 7_440, dayPct: 0.9, weightPct: 6 },
]

const agent = {
  current: "research 진행 중",
  recent: [
    { ts: "14:01", action: "매수", symbol: "NVDA", summary: "AI 모멘텀 + 6/14 catalyst, $190 진입" },
    { ts: "11:32", action: "관망", symbol: "TSLA", summary: "지지선 재시험 대기" },
    { ts: "10:05", action: "매도", symbol: "INTC", summary: "실적 가이던스 하향, 손절" },
  ],
}

const market = { phase: "regular", label: "정규장", nextLabel: "마감까지 1시간 58분" }

export default {
  title: "Autostock/DashboardView",
  id: "autostock-dashboard-view",
  component: DashboardView,
}

export const Rich = {
  render: () => (
    <Phone>
      <DashboardView model={model} positions={positions} cash={18_240} buyingPower={36_480} market={market} agent={agent} />
    </Phone>
  ),
}

export const PendingApprovalsDown = {
  render: () => (
    <Phone>
      <DashboardView
        model={{ ...model, dayPnlPct: -2.07, pendingApprovals: 2 }}
        positions={positions}
        cash={18_240}
        buyingPower={36_480}
        market={{ phase: "pre", label: "프리마켓", nextLabel: "정규장까지 47분" }}
        agent={agent}
      />
    </Phone>
  ),
}

export const Minimal = {
  render: () => (
    <Phone>
      <DashboardView model={{ ...model, positionCount: 4, symbols: ["AAPL", "TSLA", "NVDA", "MSFT"] }} />
    </Phone>
  ),
}

export const HealthCheckEmpty = {
  render: () => (
    <Phone>
      <DashboardView
        model={{ ...model, healthOk: false, symbols: [], positionCount: 0 }}
        positions={[]}
        market={{ phase: "closed", label: "장마감", nextLabel: "프리마켓까지 9시간" }}
        agent={{ current: null, recent: agent.recent }}
      />
    </Phone>
  ),
}

export const Offline = {
  render: () => (
    <Phone>
      <DashboardView
        model={{ ...model, offline: true, equity: null, dayPnlPct: null, healthOk: null, symbols: [], positionCount: 0 }}
      />
    </Phone>
  ),
}
