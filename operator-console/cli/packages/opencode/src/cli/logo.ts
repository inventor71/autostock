// autostock wordmark (F5 BR-14, Q1=B: 2-line stack "auto" / "stock").
// The renderer (component/logo.tsx) is data-driven on row count: height = left.length, and each
// rendered row = left[i] + gap + right[i]. We stack the whole wordmark in `left` (8 rows: 4 for
// "auto", 4 for "stock") and keep `right` as 8 empty strings so nothing renders beside it.
// Only █ ▀ ▄ and space are used (lit() treats those as glyph cells); the shimmer animation in
// logo.tsx works unchanged. Half-block art is first-pass — tweak visually against `bun dev`.
//
// Each letter is 4 cols wide with 1-space gaps; rows padded to a uniform 24 cols (rectangular).
// "auto"  : a u t o       (4*4 + 3 gaps = 19, padded to 24)
// "stock" : s t o c k      (5*4 + 4 gaps = 24)
export const logo = {
  left: [
    "                        ", // auto: top accent row (blank)
    "█▀▀█ █  █ ▀▀▀▀ █▀▀█      ",
    "█▀▀█ █  █  ██  █  █      ",
    "█  █ ▀▀▀▀  ██  ▀▀▀▀      ",
    "                        ", // stock: top accent row (also the inter-line gap)
    "▄▀▀▀ ▀▀▀▀ █▀▀█ █▀▀▀ █  █ ",
    "▀▀▀▄  ██  █  █ █    ██▀  ",
    "▀▀▀▀  ██  ▀▀▀▀ ▀▀▀▀ █  █ ",
  ],
  right: ["", "", "", "", "", "", "", ""],
}

export const go = {
  left: ["    ", "█▀▀▀", "█_^█", "▀▀▀▀"],
  right: ["    ", "█▀▀█", "█__█", "▀▀▀▀"],
}

export const marks = "_^~,"
