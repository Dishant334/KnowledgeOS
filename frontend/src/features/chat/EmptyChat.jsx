// A new chat: a heading, one line of help and the question box in the MIDDLE of the screen. After the first question the box moves to the bottom (see ChatLayout).
export default function EmptyChat({ composer }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4 text-center">
      <h1 className="font-display text-3xl font-semibold text-ink">Ask your documents</h1>
      <p className="mt-2 max-w-md text-stone-600">
        Every answer points to the exact passage it came from, so you can check it yourself.
      </p>
      <div className="mt-6 w-full">{composer}</div>
    </div>
  )
}
