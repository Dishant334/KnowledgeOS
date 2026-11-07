// The expanding circle that spreads from the point you clicked (the "ripple" of a Material button).
// Call it from a pointerdown handler. The button must be `relative overflow-hidden` so the circle stays inside it.
// The circle uses `currentColor`, so it is white on a dark button and dark on a light one, with no extra setup.
// People who asked their system for less motion get no ripple.
export function ripple(button, clientX, clientY) {
  if (!button || button.disabled) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

  const box = button.getBoundingClientRect()
  const size = Math.max(box.width, box.height) * 2.2
  const circle = document.createElement('span')
  circle.className = 'ripple'
  circle.style.width = `${size}px`
  circle.style.height = `${size}px`
  circle.style.left = `${clientX - box.left - size / 2}px`
  circle.style.top = `${clientY - box.top - size / 2}px`
  button.appendChild(circle)
  circle.addEventListener('animationend', () => circle.remove(), { once: true })
  setTimeout(() => circle.remove(), 1000) // safety net if the animation never reports back
}
