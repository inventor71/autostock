// @ts-nocheck
import { ConfirmSheet } from "./confirm-sheet"
import { WebAuthnError } from "./signed-mutation"

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

export const SignatureFailed = {
  render: () => (
    <Phone>
      <ConfirmSheet
        request={req}
        onApprove={async () => {
          throw new WebAuthnError("사용자가 패스키 서명을 취소했습니다")
        }}
        onReject={() => {}}
      />
    </Phone>
  ),
}
