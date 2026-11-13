// The hero is as tall as the screen, like most hero sections. `100svh` = the visible height of the screen (unlike `100vh`
// it ignores a phone browser's address bar that slides away). The content (headline, pitch, buttons, the 3D piece) comes
// later; for now this only keeps the space, so the sections below start one full screen down.
export default function Hero() {
  return (
    <section className="relative flex min-h-[100svh] items-center justify-center">
      <p className="text-sm text-stone-600">Hero</p>
    </section>
  )
}
