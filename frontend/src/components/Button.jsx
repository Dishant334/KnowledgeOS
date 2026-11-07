import { ripple } from '../lib/ripple'

const VARIANTS = {
  primary: 'bg-brand-700 text-white shadow-sm shadow-brand-900/20 hover:bg-brand-800 hover:shadow-md focus-visible:outline-brand-700',
  secondary: 'bg-surface text-stone-700 ring-1 ring-stone-300 hover:bg-stone-50 hover:ring-brand-300 focus-visible:outline-brand-700',
  danger: 'bg-red-700 text-white shadow-sm hover:bg-red-600 hover:shadow-md focus-visible:outline-red-700',
}

// A button in one of three looks. It lifts a little on hover, presses down on click and sends a ripple from the point
// you clicked (all of that is skipped for people who asked their system for less motion). Everything else you pass
// (onClick, disabled, type...) goes straight to <button>.
export default function Button({ variant = 'primary', className = '', type = 'button', onPointerDown, ...props }) {
  return (
    <button
      type={type}
      onPointerDown={(event) => {
        ripple(event.currentTarget, event.clientX, event.clientY)
        onPointerDown?.(event)
      }}
      className={`relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-md px-3.5 py-2 text-sm font-medium transition duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 motion-safe:enabled:hover:-translate-y-px motion-safe:enabled:active:translate-y-0 motion-safe:enabled:active:scale-[0.97] ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}
