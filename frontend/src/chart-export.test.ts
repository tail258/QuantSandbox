// @vitest-environment jsdom
import { expect, it } from 'vitest'
import { serializeChart } from './chart-export'

it('exports theme colors with the SVG so it stays readable outside the workbench', () => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.style.setProperty('--chart-grid', '#30363D')
  svg.style.setProperty('--chart-tooltip-bg', '#252B31')
  const line = document.createElementNS(svg.namespaceURI, 'path')
  line.setAttribute('stroke', 'var(--chart-grid)')
  line.setAttribute('d', 'M0 0L10 10')
  svg.append(line)
  document.body.append(svg)
  const original = svg.outerHTML
  const exported = new DOMParser().parseFromString(serializeChart(svg), 'image/svg+xml')
  const root = exported.documentElement as unknown as SVGSVGElement
  expect(root.style.getPropertyValue('--chart-grid')).toBe('#30363D')
  expect(root.style.backgroundColor).toBe('rgb(37, 43, 49)')
  expect(exported.querySelector('path')?.getAttribute('d')).toBe('M0 0L10 10')
  expect(svg.outerHTML).toBe(original)
  svg.remove()
})
