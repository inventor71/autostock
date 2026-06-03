import { Prompt, type PromptRef } from "@tui/component/prompt"
import { createEffect, createMemo, createSignal, onMount, Show } from "solid-js"
import { Logo } from "../component/logo"
import { sidebarWidth } from "./session/sidebar"
import { setSidebarWidth } from "./session/sidebar-width"
import { useTheme } from "../context/theme"
import { useSync } from "../context/sync"
import { Toast } from "../ui/toast"
import { useArgs } from "../context/args"
import { useRouteData } from "@tui/context/route"
import { usePromptRef } from "../context/prompt"
import { useLocal } from "../context/local"
import { TuiPluginRuntime } from "@/cli/cmd/tui/plugin/runtime"
import { useEditorContext } from "@tui/context/editor"
import { useTerminalDimensions } from "@opentui/solid"
import { useTuiConfig } from "../context/tui-config"

let once = false
// autostock (F7): localize the home prompt examples — Korean locale shows Korean steering
// examples, everything else English. Detection is best-effort from the shell locale env
// (the fork has no i18n infra); the example shell commands stay as-is (real shell input).
const KO = (
  process.env.LC_ALL ||
  process.env.LC_MESSAGES ||
  process.env.LANG ||
  (typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().locale : "") ||
  ""
)
  .toLowerCase()
  .startsWith("ko")
const placeholder = {
  normal: KO
    ? ["애플 절반 팔아", "신규 진입 중지", "지금 포지션 보여줘"]
    : ["sell half my AAPL", "pause new entries", "what are my open positions?"],
  shell: ["ls -la", "git status", "pwd"],
}

export function Home() {
  const sync = useSync()
  const route = useRouteData("home")
  const promptRef = usePromptRef()
  const [ref, setRef] = createSignal<PromptRef | undefined>()
  const args = useArgs()
  const local = useLocal()
  const editor = useEditorContext()
  const dimensions = useTerminalDimensions()
  const { theme } = useTheme()
  const [dragging, setDragging] = createSignal(false)
  const tuiConfig = useTuiConfig()
  const promptMaxWidth = createMemo(() => {
    const configured = tuiConfig.prompt?.max_width
    if (configured === "auto") return Math.max(75, Math.floor(dimensions().width * 0.7))
    return configured ?? 75
  })
  // F5 option ②: show the autostock trading sidebar on home in wide terminals (mirrors the
  // session route's `wide = width > 120` gate, BR-7.2) so a fresh launch is sidebar-first.
  const wide = createMemo(() => dimensions().width > 120)
  let sent = false

  onMount(() => {
    editor.clearSelection()
  })

  const bind = (r: PromptRef | undefined) => {
    setRef(r)
    promptRef.set(r)
    if (once || !r) return
    if (route.prompt) {
      r.set(route.prompt)
      once = true
      return
    }
    if (!args.prompt) return
    r.set({ input: args.prompt, parts: [] })
    once = true
  }

  // Wait for sync and model store to be ready before auto-submitting --prompt
  createEffect(() => {
    const r = ref()
    if (sent) return
    if (!r) return
    if (!sync.ready || !local.model.ready) return
    if (!args.prompt) return
    if (r.current.input !== args.prompt) return
    sent = true
    r.submit()
  })

  return (
    <>
      <box flexDirection="row" flexGrow={1} minHeight={0}>
        <box flexGrow={1} alignItems="center" paddingLeft={2} paddingRight={2}>
          <box flexGrow={1} minHeight={0} />
          <box height={4} minHeight={0} flexShrink={1} />
          <box flexShrink={0}>
            <TuiPluginRuntime.Slot name="home_logo" mode="replace">
              <Logo />
            </TuiPluginRuntime.Slot>
          </box>
          <box height={1} minHeight={0} flexShrink={1} />
          <box width="100%" maxWidth={promptMaxWidth()} zIndex={1000} paddingTop={1} flexShrink={0}>
            <TuiPluginRuntime.Slot name="home_prompt" mode="replace" ref={bind}>
              <Prompt ref={bind} right={<TuiPluginRuntime.Slot name="home_prompt_right" />} placeholders={placeholder} />
            </TuiPluginRuntime.Slot>
          </box>
          <TuiPluginRuntime.Slot name="home_bottom" />
          <box flexGrow={1} minHeight={0} />
          <Toast />
        </box>
        <Show when={wide()}>
          <box width={sidebarWidth()} flexShrink={0} paddingLeft={2} paddingRight={1} position="relative">
            {/* F6 — drag-resize grab strip = a 1-col OPAQUE bar at the sidebar's left edge,
                exactly like the session Sidebar (the proven-working pattern). It replaces the
                old `border:["left"]` (a transparent box over a parent border doesn't hit-test,
                so the drag never fired on home). selectable=false so text-selection doesn't
                swallow onMouseDrag; width = terminalWidth − cursorColumn (sidebar is on the right). */}
            <box
              position="absolute"
              left={0}
              top={0}
              bottom={0}
              width={1}
              selectable={false}
              backgroundColor={dragging() ? theme.borderActive : theme.border}
              onMouseDown={(e) => {
                setDragging(true)
                e.stopPropagation()
              }}
              onMouseDrag={(e) => setSidebarWidth(dimensions().width - e.x, dimensions().width)}
              onMouseDragEnd={() => setDragging(false)}
            />
            <TuiPluginRuntime.Slot name="home_sidebar" />
          </box>
        </Show>
      </box>
      <box width="100%" flexShrink={0}>
        <TuiPluginRuntime.Slot name="home_footer" mode="single_winner" />
      </box>
    </>
  )
}
