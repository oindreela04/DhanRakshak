/** Shared, mutable scroll state read inside render loops (avoids React re-renders). */
export const scroll = { progress: 0, velocity: 0, _last: 0 }

export function bindScroll(): () => void {
  let raf = 0
  const tick = () => {
    const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
    const p = window.scrollY / max
    scroll.velocity += (Math.abs(p - scroll._last) - scroll.velocity) * 0.12
    scroll._last = p
    scroll.progress += (p - scroll.progress) * 0.12
    document.documentElement.style.setProperty('--scroll', String(p))
    raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
  return () => cancelAnimationFrame(raf)
}
