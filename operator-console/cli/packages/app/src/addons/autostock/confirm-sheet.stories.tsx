// @ts-nocheck
import { onMount } from "solid-js"
import { ConfirmSheet } from "./confirm-sheet"
import { WebAuthnError } from "./signed-mutation"

// `transform` = containing block for the sheet's `position: fixed`, so it clips to the
// phone frame in Storybook (on device, fixed = the phone viewport).
const Phone = (props) => (
  <div
    style={{
      position: "relative",
      transform: "translateZ(0)",
      width: "390px",
      height: "740px",
      overflow: "hidden",
      border: "1px solid #8884",
      "border-radius": "24px",
    }}
  >
    <div style={{ padding: "16px", color: "#888" }}>대시보드 (시트 뒤 배경)</div>
    {props.children}
  </div>
)

const req = { id: "perm_1", permission: "autostock_place_stock_order", title: "AAPL 10주 매수 (지정가 $192.50)" }

export default {
  title: "Autostock/ConfirmSheet",
  id: "autostock-confirm-sheet",
  component: ConfirmSheet,
}

export const Default = {
  render: () => (
    <Phone>
      <ConfirmSheet request={req} onApprove={async () => {}} onReject={() => {}} />
    </Phone>
  ),
}

// Auto-taps 승인 on mount so the failure (error) state is visible without interaction —
// the error only renders after an approve attempt rejects.
export const SignatureFailed = {
  render: () => {
    let root
    onMount(() => setTimeout(() => root?.querySelector("button")?.click(), 60))
    return (
      <Phone>
        <div ref={root}>
          <ConfirmSheet
            request={req}
            onApprove={async () => {
              throw new WebAuthnError("사용자가 패스키 서명을 취소했습니다")
            }}
            onReject={() => {}}
          />
        </div>
      </Phone>
    )
  },
}
