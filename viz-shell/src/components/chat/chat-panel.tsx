"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";

import type { VizUIMessage } from "@/lib/chat-types";

const MAX_INPUT_CHARS = 4_000; // soft limit (BR: forms)

function MessageParts({ message }: { message: VizUIMessage }) {
  return (
    <>
      {message.parts.map((part, i) => {
        if (part.type === "text") {
          return (
            <p key={i} className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {part.text}
            </p>
          );
        }
        if (part.type === "data-tool-activity") {
          return (
            <div
              key={i}
              data-testid="chat-tool-activity"
              className="truncate text-xs text-ink-dim"
              title={`${part.data.tool} ${part.data.target}`}
            >
              ✎ {part.data.tool} {part.data.target}
            </div>
          );
        }
        if (part.type === "data-boundary-denied") {
          return (
            <div
              key={i}
              data-testid="chat-boundary-denied"
              className="rounded border border-warn/40 bg-warn/10 px-2 py-1 text-xs text-warn"
            >
              ⚠️ 거부됨: {part.data.tool} {part.data.target} — {part.data.reason}
            </div>
          );
        }
        return null;
      })}
    </>
  );
}

export function ChatPanel({
  onCollapse,
  presetPrompt,
  onPresetConsumed,
}: {
  onCollapse: () => void;
  /** A preset-chip prompt to send automatically (Explore tab). */
  presetPrompt?: string | null;
  onPresetConsumed?: () => void;
}) {
  const { messages, sendMessage, stop, status, error, setMessages, clearError } =
    useChat<VizUIMessage>({
      transport: new DefaultChatTransport({ api: "/api/chat" }),
    });
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const inFlight = status === "submitted" || status === "streaming";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  // Preset chip → send once. Ignored while a turn is in flight (single-flight).
  useEffect(() => {
    if (presetPrompt && !inFlight) {
      void sendMessage({ text: presetPrompt });
      onPresetConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetPrompt]);

  const submit = () => {
    const text = input.trim();
    if (text === "" || inFlight) return;
    void sendMessage({ text });
    setInput("");
  };

  const newChat = async () => {
    if (inFlight) return;
    if (!window.confirm("새 채팅을 시작할까요? (생성된 뷰 파일은 유지됩니다)")) return;
    const res = await fetch("/api/chat/reset", { method: "POST" });
    if (!res.ok) {
      window.alert("턴 진행 중에는 리셋할 수 없습니다 — 끝난 뒤 다시 시도하세요.");
      return;
    }
    setMessages([]);
    clearError();
  };

  return (
    <aside
      data-testid="chat-panel"
      className="flex w-[360px] shrink-0 flex-col border-l border-edge bg-surface-1"
    >
      <div className="flex items-center justify-between border-b border-edge px-3 py-2">
        <span className="text-sm font-semibold text-ink">뷰 생성 채팅</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="chat-new-button"
            onClick={() => void newChat()}
            disabled={inFlight}
            className="rounded px-2 py-1 text-xs text-ink-dim hover:bg-surface-2 hover:text-ink disabled:opacity-40"
          >
            New chat
          </button>
          <button
            type="button"
            data-testid="chat-collapse-button"
            onClick={onCollapse}
            aria-label="채팅 패널 접기"
            className="rounded px-2 py-1 text-ink-dim hover:bg-surface-2 hover:text-ink"
          >
            ⇥
          </button>
        </div>
      </div>

      <div data-testid="chat-messages" className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && (
          <p className="text-sm text-ink-dim">
            대시보드에 띄울 뷰를 말로 요청하세요.
            <br />
            예: &quot;심볼별 미실현 손익 막대차트 뷰 만들어줘&quot;
            <br />
            기존 뷰 수정/삭제도 채팅으로 요청합니다.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[90%] rounded-lg bg-accent/15 px-3 py-2 text-ink"
                  : "max-w-full space-y-1 text-ink"
              }
            >
              <MessageParts message={m} />
            </div>
          </div>
        ))}
        {inFlight && (
          <div data-testid="chat-working" className="flex items-center gap-2 text-xs text-ink-dim">
            작업 중…
            <button
              type="button"
              data-testid="chat-stop-button"
              onClick={() => void stop()}
              title="턴을 중단합니다 (스톨 시 복구용)"
              className="rounded border border-edge px-1.5 py-0.5 text-ink-dim hover:bg-surface-2 hover:text-ink"
            >
              ■ 중지
            </button>
          </div>
        )}
        {error && (
          <div
            data-testid="chat-error"
            className="rounded border border-down/40 bg-down/10 px-2 py-1 text-xs text-down"
          >
            {error.message.includes("409") || error.message.includes("in progress")
              ? "이미 진행 중인 턴이 있습니다 — 끝난 뒤 다시 보내세요."
              : `오류: ${error.message}`}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-edge p-2">
        <textarea
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT_CHARS))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={inFlight ? "턴 진행 중…" : "뷰 요청 입력 (Enter 전송)"}
          disabled={inFlight}
          rows={3}
          className="w-full resize-none rounded-md border border-edge bg-surface-0 px-2 py-1.5 text-sm text-ink placeholder:text-ink-dim focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <div className="mt-1 flex items-center justify-between">
          <span className="text-xs text-ink-dim">
            {input.length > MAX_INPUT_CHARS - 500 ? `${input.length}/${MAX_INPUT_CHARS}` : ""}
          </span>
          <button
            type="button"
            data-testid="chat-send-button"
            onClick={submit}
            disabled={inFlight || input.trim() === ""}
            className="rounded-md bg-accent/20 px-3 py-1 text-sm text-accent hover:bg-accent/30 disabled:opacity-40"
          >
            전송
          </button>
        </div>
      </div>
    </aside>
  );
}
