// @ts-nocheck
import { HealthOverlay, PositionThesisView } from "./detail-views"

const Phone = (props) => (
  <div
    style={{
      position: "relative",
      width: "390px",
      height: "740px",
      overflow: "hidden",
      border: "1px solid #8884",
      "border-radius": "24px",
    }}
  >
    {props.children}
  </div>
)

export default {
  title: "Autostock/DetailViews",
  id: "autostock-detail-views",
}

export const Thesis = {
  render: () => (
    <Phone>
      <PositionThesisView
        symbol="AAPL"
        thesis={
          "엔트리: $188.20 (2026-06-12 PRE)\n근거: 견조한 서비스 매출 + 6/14 catalyst(WWDC 후속).\n리스크: $182 지지 이탈 시 청산.\n타깃: $198 1차, $205 트레일."
        }
        onClose={() => {}}
      />
    </Phone>
  ),
}

export const ThesisEmpty = {
  render: () => (
    <Phone>
      <PositionThesisView symbol="TSLA" thesis={null} onClose={() => {}} />
    </Phone>
  ),
}

export const Health = {
  render: () => (
    <Phone>
      <HealthOverlay
        summary="9개 차원 중 8개 정상 · 1개 경고"
        dimensions={[
          { name: "process", ok: true },
          { name: "logs", ok: true },
          { name: "config_env", ok: true },
          { name: "resources", ok: true },
          { name: "account", ok: true },
          { name: "broker", ok: true },
          { name: "llm", ok: true },
          { name: "data_freshness", ok: false, detail: "마지막 시그널 스윕 42분 전 (임계 30분 초과)" },
          { name: "scheduler", ok: true },
        ]}
        onClose={() => {}}
      />
    </Phone>
  ),
}
