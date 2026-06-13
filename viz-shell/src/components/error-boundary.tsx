"use client";

import { Component, type ReactNode } from "react";

type Props = { viewTitle: string; children: ReactNode };
type State = { error: Error | null };

/**
 * Isolates a broken generated view to its own tab — the shell and the other
 * tabs stay alive (L4). The fallback tells the operator how to recover.
 */
export class ViewErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.warn(`[viz-shell:view] "${this.props.viewTitle}" crashed:`, error.message);
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div
        data-testid="view-error-fallback"
        className="m-6 rounded-lg border border-warn/40 bg-surface-1 p-6"
      >
        <div className="mb-2 font-semibold text-warn">
          ⚠️ 렌더 실패 — {this.props.viewTitle}
        </div>
        <pre className="mb-3 overflow-x-auto whitespace-pre-wrap text-sm text-ink-dim">
          {this.state.error.message}
        </pre>
        <p className="text-sm text-ink-dim">
          채팅으로 수정을 요청하세요. (예: &quot;{this.props.viewTitle} 뷰가 깨졌어 — 고쳐줘&quot;)
        </p>
      </div>
    );
  }
}
