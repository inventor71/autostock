// @ts-nocheck
import { DashboardView } from "./dashboard-view"

const Phone = (props) => (
  <div style={{ width: "390px", height: "740px", overflow: "auto", border: "1px solid #8884", "border-radius": "24px" }}>
    {props.children}
  </div>
)

const base = {
  equity: 128_430.55,
  dayPnlPct: 1.24,
  positionCount: 4,
  symbols: ["AAPL", "TSLA", "NVDA", "MSFT"],
  healthOk: true,
  pendingApprovals: 0,
  asOf: "2026-06-14T14:02:11Z",
  offline: false,
}

export default {
  title: "Autostock/DashboardView",
  id: "autostock-dashboard-view",
  component: DashboardView,
}

export const Healthy = {
  render: () => (
    <Phone>
      <DashboardView model={base} />
    </Phone>
  ),
}

export const PendingApprovalsDown = {
  render: () => (
    <Phone>
      <DashboardView model={{ ...base, dayPnlPct: -2.07, healthOk: true, pendingApprovals: 2 }} />
    </Phone>
  ),
}

export const HealthCheckEmpty = {
  render: () => (
    <Phone>
      <DashboardView model={{ ...base, healthOk: false, symbols: [], positionCount: 0 }} />
    </Phone>
  ),
}

export const StaleData = {
  render: () => (
    <Phone>
      <DashboardView model={base} stale />
    </Phone>
  ),
}

export const Offline = {
  render: () => (
    <Phone>
      <DashboardView
        model={{ ...base, offline: true, equity: null, dayPnlPct: null, healthOk: null, symbols: [], positionCount: 0 }}
      />
    </Phone>
  ),
}
