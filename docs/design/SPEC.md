# Interface design

The current runtime is the React workbench. `terminal-concept.png` is an earlier design exploration, not a screenshot of the current application. Runtime styles and verified browser behavior take precedence over that illustration.

## Themes

The original Classic light theme remains the default appearance. Financial terminal is an optional black/gray/gold theme. Both use the same layouts, records and calculations. The interface defaults to English and offers Chinese; browser preferences persist independently of research data.

| Financial terminal token | Value |
| --- | --- |
| Background | `#0B0D0F` |
| Surface | `#191D21` |
| Elevated surface | `#252B31` |
| Bullish / rising | `#E34B4B` |
| Bearish / falling | `#31C48D` |
| Accent / equity curve | `#F5C542` |
| Primary text | `#E9EDF2` |
| Secondary text | `#959DA7` |
| Border | `#30363D` |
| Benchmark | `#6C7884` |

Use `themes.css` tokens and component-specific variables for graphs, controls and dialogs. Keep red-up/green-down semantics consistent. Downloaded charts must retain readable colors outside the application; original evidence images remain unchanged.

## Layout and interaction

Use project-centered navigation, result-first pages, and drawers or dialogs for configuration. Keep dates, units, sample counts and data gaps visible; collapse long methodology and identifiers. Show company names with supporting codes, and avoid repeated headings that push results below the fold.

Use tabular numerals, readable body/table text, visible focus states, accessible icon labels and reduced-motion support. On narrow screens, keep language, appearance and current-project controls accessible; allow tables and record strips to scroll within their own containers instead of overflowing the page.

The strategy page links candles, trades and decision evidence. A selected record retains its inputs across project changes. Preserve unsaved fields when switching language or theme; never translate user text, source documents or archived evidence in place.

## Visual validation

Build the production frontend and test a real browser at desktop and phone sizes. Check navigation, selection, project changes, late responses, loading/errors, empty states, blind replay, note-preview invalidation, both languages and both themes as affected. Verify standalone SVG downloads as well as the on-screen chart. Mockups and a passing build alone do not prove interaction behavior.
