/** Freeze inherited theme colors into a standalone SVG without changing the on-screen chart. */
export function serializeChart(svg: Element): string {
  const copy = svg.cloneNode(true) as SVGSVGElement
  const styles = getComputedStyle(svg)
  const tokens = new Set([...svg.outerHTML.matchAll(/var\((--[\w-]+)/g)].map(match => match[1]))
  for (const token of tokens) {
    const value = styles.getPropertyValue(token).trim()
    if (value) copy.style.setProperty(token, value)
  }
  const background = styles.getPropertyValue('--chart-tooltip-bg').trim()
  if (background) copy.style.backgroundColor = background
  copy.style.color = styles.color
  if (styles.fontFamily) copy.style.fontFamily = styles.fontFamily
  return new XMLSerializer().serializeToString(copy)
}
