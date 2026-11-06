// A placeholder for a page that a later build step adds.
export default function ComingSoonPage({ title, step }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
      <h1 className="text-lg font-semibold">{title}</h1>
      <p className="mt-1 text-sm text-slate-500">This page arrives in build step {step}.</p>
    </div>
  )
}
