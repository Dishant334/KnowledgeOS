// A red message box. `action` is an optional element, for example a "Try again" button. It fades in (page-in).
export default function ErrorBanner({ message, action = null }) {
  return (
    <div className="page-in flex items-start justify-between gap-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
      <p>{message}</p>
      {action}
    </div>
  )
}
