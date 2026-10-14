import { useEffect, useRef, type ReactNode } from 'react'

/**
 * Dialog shell shared by every pop-up: closes on Escape and on a click outside,
 * moves keyboard focus into the dialog and gives it back when it closes.
 */
export function Modal({ onClose, wide = false, label, children }: {
  onClose: () => void
  wide?: boolean
  label?: string
  children: ReactNode
}) {
  const box = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose }, [onClose])

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    box.current?.focus()
    // Capture phase + preventDefault: the dialog takes Escape before anything
    // else listening for it (the chat stops a running answer on Escape).
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); close.current() } }
    window.addEventListener('keydown', onKey, true)
    return () => { window.removeEventListener('keydown', onKey, true); previous?.focus?.() }
  }, [])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div ref={box} className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={label}
        tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}
