import "@opentui/core"

// `selectable` lives on the runtime Renderable base (Renderable.selectable) and is
// declared on TextBufferOptions, but @opentui/core 0.2.16 omits it from BoxOptions.
// F6 drag handles set selectable={false} on a <box> so a mousedown doesn't start a
// text selection that swallows onMouseDrag. Type-only shim — zero runtime effect.
declare module "@opentui/core" {
  interface BoxOptions<TRenderable extends Renderable = BoxRenderable> {
    selectable?: boolean
  }
}
