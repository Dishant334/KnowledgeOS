// A placeholder for a page that a later build step adds.
export default function ComingSoonPage({ title, step }) {
  return (
    <div className="rounded-lg border border-dashed border-stone-300 bg-surface p-10 text-center">
      <h1 className="text-lg font-semibold">{title}</h1>
      <p className="mt-1 text-sm text-stone-600">This page arrives in build step {step}.</p>
    </div>
  )
}
