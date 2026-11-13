import { useInView, useMotionValueEvent, useReducedMotion, useScroll, useSpring } from 'motion/react'
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useTheme } from '../../theme/useTheme'

// The eight steps of "How it works". Every sentence here describes what the code in this project really does (the same
// facts as the README's "How the RAG pipeline works"). `details` are the sub-steps that appear one by one as you scroll
// through a step; `chips` are the technologies involved.
const STEPS = [
  {
    n: '01',
    title: 'Ingestion',
    lead: 'Upload PDFs, Word, PowerPoint, Excel, CSV, Markdown or HTML.',
    details: [
      { h: 'Check the file', t: 'Only supported types, up to 20 MB. A hash spots a file you already uploaded, so it is never stored twice.' },
      { h: 'Save it', t: 'The bytes go into Postgres and the file is linked to the chat it was added to. Status: pending.' },
      { h: 'Hand it to a worker', t: 'A task is queued through Redis and a Celery worker picks it up, so the upload returns at once.' },
    ],
    chips: ['FastAPI', 'Postgres', 'Redis', 'Celery'],
  },
  {
    n: '02',
    title: 'Processing',
    lead: 'The worker reads the file, cleans the text and cuts it into chunks.',
    details: [
      { h: 'Load', t: 'A loader for each file type extracts the text and remembers where it came from: page, slide, sheet and rows.' },
      { h: 'OCR for scans', t: 'A page with almost no text is treated as a scan: it is rendered at 300 DPI and read with Tesseract, with a retry if confidence is under 60%.' },
      { h: 'Clean', t: 'Control characters, hyphenated line breaks, headers and footers repeated on many pages, and duplicate lines are removed.' },
      { h: 'Chunk', t: 'Pieces of up to 512 tokens with a 64-token overlap. Slides stay whole, spreadsheets go 20 rows at a time, HTML splits at its headings.' },
    ],
    chips: ['PyMuPDF', 'Tesseract', 'LangChain'],
  },
  {
    n: '03',
    title: 'Embedding',
    lead: 'Every chunk becomes two sets of numbers: one for meaning, one for exact words.',
    details: [
      { h: 'Dense vector', t: '1,024 numbers from bge-large-en-v1.5 capture meaning, so "vacation" finds "annual leave".' },
      { h: 'Sparse vector', t: 'A BM25 vector keeps the exact words, so a policy code or a number still matches.' },
      { h: 'All local', t: 'Both run on your own machine: no embedding API and no cost.' },
    ],
    chips: ['FastEmbed', 'bge-large', 'BM25'],
  },
  {
    n: '04',
    title: 'Indexing & storage',
    lead: 'Each piece of data goes where it is fastest to use.',
    details: [
      { h: 'Qdrant', t: 'Both vectors and the chunk\'s owner, document and location are saved as one point. Status: ready.' },
      { h: 'Postgres', t: 'The files, chats, answers with their citations, and your long-term memory facts.' },
      { h: 'Redis', t: 'The task queue, the rate limits (10 questions a minute, 100 a day) and caches.' },
    ],
    chips: ['Qdrant', 'Postgres', 'Redis'],
  },
  {
    n: '05',
    title: 'Query',
    lead: 'You ask in plain language, in a chat that has its own documents.',
    details: [
      { h: 'Shortcuts', t: 'Greetings and introductions are answered by rules, with no search and no model call.' },
      { h: 'Needs documents', t: 'A chat with no files gets a short "add a document first" reply.' },
      { h: 'Fair use', t: 'Rate limits are checked first, so a refused question costs nothing.' },
    ],
    chips: ['FastAPI', 'Clerk', 'Redis'],
  },
  {
    n: '06',
    title: 'Retrieval',
    lead: 'Find the few passages that actually answer the question.',
    details: [
      { h: 'Rewrite', t: 'A follow-up like "and can I carry them over?" becomes a standalone question, using the chat history.' },
      { h: 'Hybrid search', t: 'Dense and BM25 search (15 results each) are fused by reciprocal rank fusion, filtered to your user id and this chat\'s documents. 30 candidates move on.' },
      { h: 'Rerank', t: 'A cross-encoder (bge-reranker-base) reads the question and each candidate together and keeps the top 5.' },
    ],
    chips: ['Qdrant', 'RRF', 'bge-reranker'],
  },
  {
    n: '07',
    title: 'Augmentation',
    lead: 'Build the prompt: the question, the best passages and the rules.',
    details: [
      { h: 'Fit the budget', t: 'Passages are added in rank order until the 3,000-token budget is full.' },
      { h: 'Number the sources', t: 'Each passage becomes [1], [2]… with its file and location; the code remembers which is which.' },
      { h: 'Add context', t: 'The chat summary, the recent messages and your long-term memory, as background only.' },
      { h: 'Set the rules', t: 'Answer only from the context, cite every claim, and treat document text as untrusted data, never as instructions.' },
    ],
    chips: ['LangChain', 'Memory'],
  },
  {
    n: '08',
    title: 'Generation',
    lead: 'The model writes the answer, and every claim points to its source.',
    details: [
      { h: 'Call the model', t: 'Qwen3 8B through Ollama runs locally. If it fails, Gemini takes over, when one is configured.' },
      { h: 'Stream', t: 'Words reach your browser as server-sent events while they are written, and Stop cancels the answer.' },
      { h: 'Map the citations', t: 'The [n] numbers in the answer are matched back to real chunks. Only the sources actually cited come back, each with a 600-character passage.' },
      { h: 'Save and remember', t: 'The turn is saved in Postgres; long chats get a rolling summary and durable facts go to your memory.' },
    ],
    chips: ['Ollama', 'Qwen3 8B', 'Gemini', 'SSE'],
  },
]

// ── The 3D scene ──
// three.js is big (about 140 KB gzipped), so it is loaded by a dynamic import, only when this section is close to the screen.
// It becomes its own chunk, and the rest of the home page never waits for it.
let THREE
let RoundedBoxGeometry
async function loadThree() {
  if (THREE) return
  const [core, rounded] = await Promise.all([import('three'), import('three/examples/jsm/geometries/RoundedBoxGeometry.js')])
  THREE = core
  RoundedBoxGeometry = rounded.RoundedBoxGeometry
}

// ── The 3D stack for "How it works": eight slabs, one per step, joined by a glowing thread ─────────────────────────────
// It is only drawn here; the scroll position comes in through `stateRef` ({ active: which step is open, local: how far
// through that step, 0 to 1 }), written by HowItWorks.jsx. Nothing here uses React state, so scrolling never re-renders.
//
//  - The slabs above the open step are lifted away, which uncovers the open slab's top, where its parts hop in turn
//    (the part that is "in focus" follows `local`, the same way the text panel reveals its sub-steps).
//  - A pulse of light runs down the thread to the open slab; the thread is lit down to there and dim below.
//  - Mouse: hover lifts a slab, a click calls `onPick(index)` (the page scrolls to that step), a drag turns the stack a
//    little and it swings back when you let go.

const N = STEPS.length
const SLAB_W = 11 // wide: the stage has plenty of room sideways, and the keyboard on slab 3 uses all of it
const WS = SLAB_W / 8.4 // the parts below were laid out for an 8.4-wide slab; their x and width are scaled by this
const SLAB_D = 4.2
const SLAB_H = 0.4
const PITCH = 0.95 // distance between two slabs when the stack is closed
const OPEN = 2.9 // how far the slabs above the open one are lifted
const THREAD_Z = -1.55 // the thread runs near the back, so it never crosses the parts on the slabs
const FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'

const SLAB_COLORS = ['#1f6f55', '#efe3cf', '#17594c', '#f2ecdd', '#0f3b34', '#cdeee5', '#f7e2ad', '#f3ead6']
const INK = '#1a2321'

const damp = (current, target, lambda, dt) => current + (target - current) * (1 - Math.exp(-lambda * dt))
const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
const restY = (i) => ((N - 1) / 2 - i) * PITCH // slab 0 is on top

// Text for the top of a part: drawn on a canvas, used as a texture on a flat plane lying on the part.
function labelTexture(label, sub, w, d, color) {
  const PX = 200 // canvas pixels per scene unit
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w * PX)
  canvas.height = Math.round(d * PX)
  const ctx = canvas.getContext('2d')
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const fit = (text, weight, size) => {
    let s = size
    ctx.font = `${weight} ${s}px ${FONT}`
    while (ctx.measureText(text).width > canvas.width * 0.9 && s > 10) {
      s -= 2
      ctx.font = `${weight} ${s}px ${FONT}`
    }
    return s
  }
  ctx.fillStyle = color
  const mainSize = fit(label, 700, canvas.height * (sub ? 0.3 : 0.42))
  ctx.fillText(label, canvas.width / 2, canvas.height * (sub ? 0.4 : 0.52))
  if (sub) {
    ctx.globalAlpha = 0.72
    fit(sub, 500, Math.min(mainSize * 0.62, canvas.height * 0.2))
    ctx.fillText(sub, canvas.width / 2, canvas.height * 0.72)
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

function badgeTexture(text) {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#0f2b27'
  ctx.beginPath()
  ctx.arc(64, 64, 62, 0, Math.PI * 2)
  ctx.fill()
  ctx.strokeStyle = '#f5b82e'
  ctx.lineWidth = 5
  ctx.stroke()
  ctx.fillStyle = '#fbfaf5'
  ctx.font = `700 54px ${FONT}`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 64, 68)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

function glowTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  g.addColorStop(0, 'rgba(0,0,0,0.9)')
  g.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(canvas)
}

// One slab with the parts that sit on it. Returns the group and an `update` that animates the parts.
function makeSlab(i) {
  const group = new THREE.Group()
  group.userData.slab = i
  const mats = [] // every material of this slab with its true colour, so the whole slab can be dimmed together
  const items = [] // the parts that hop one after another
  const track = (mat) => {
    mats.push({ mat, base: mat.color.clone() })
    return mat
  }

  group.add(
    new THREE.Mesh(
      new RoundedBoxGeometry(SLAB_W, SLAB_H, SLAB_D, 4, 0.16),
      track(new THREE.MeshStandardMaterial({ color: SLAB_COLORS[i], roughness: 0.55, metalness: 0.02 })),
    ),
  )
  const deco = new THREE.Group()
  deco.position.y = SLAB_H / 2
  group.add(deco)

  // the step number on the front left corner
  const badge = new THREE.Mesh(
    new THREE.CircleGeometry(0.27, 32),
    track(new THREE.MeshBasicMaterial({ map: badgeTexture(String(i + 1).padStart(2, '0')), transparent: true })),
  )
  badge.rotation.x = -Math.PI / 2
  badge.position.set(-SLAB_W / 2 + 0.6, 0.006, SLAB_D / 2 - 0.5)
  deco.add(badge)

  // a part: a rounded block with a label on top
  const tile = ({ x, z, w, d, h = 0.24, color, label, sub, text = INK, hop = true }) => {
    x *= WS
    w *= WS
    const g = new THREE.Group()
    const block = new THREE.Mesh(
      new RoundedBoxGeometry(w, h, d, 3, Math.min(0.09, h / 2.2, w / 4, d / 4)),
      track(new THREE.MeshStandardMaterial({ color, roughness: 0.5 })),
    )
    block.position.y = h / 2
    g.add(block)
    if (label) {
      const plane = new THREE.Mesh(
        new THREE.PlaneGeometry(w * 0.98, d * 0.98),
        track(new THREE.MeshBasicMaterial({ map: labelTexture(label, sub, w, d, text), transparent: true, toneMapped: false })),
      )
      plane.rotation.x = -Math.PI / 2
      plane.position.y = h + 0.004
      g.add(plane)
    }
    g.position.set(x, 0, z)
    deco.add(g)
    if (hop) items.push({ g, lift: 0 })
    return g
  }

  let cubes = null // slab 3 only: a grid of little cubes, one per number of the vector
  const COLS = 26 // as wide as the slab allows (the slab is 11 across)
  const ROWS = 4
  const dummy = new THREE.Object3D()

  switch (i) {
    case 0: {
      const chips = [
        ['PDF', '#c4472f'],
        ['DOCX', '#1d7f8c'],
        ['PPTX', '#d9822b'],
        ['XLSX', '#2f8f4f'],
        ['CSV', '#7a8f2f'],
        ['MD', '#57534e'],
      ]
      chips.forEach(([name, color], k) => tile({ x: -3.3 + k * 1.32, z: 0.3, w: 1.0, d: 0.9, h: 0.3, color, label: name, text: '#ffffff' }))
      break
    }
    case 1:
      ;[
        ['Load', 'per file type'],
        ['OCR', 'for scans'],
        ['Clean', 'tidy text'],
        ['Chunk', '512 tokens'],
      ].forEach(([label, sub], k) => tile({ x: -3.0 + k * 2.0, z: 0.2, w: 1.65, d: 1.35, color: '#fffaf0', label, sub }))
      break
    case 2: {
      cubes = new THREE.InstancedMesh(
        new RoundedBoxGeometry(0.3, 0.2, 0.3, 2, 0.05),
        track(new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.4 })),
        COLS * ROWS,
      )
      const from = new THREE.Color('#8fd14f')
      const to = new THREE.Color('#36c2b0')
      for (let r = 0; r < ROWS; r++)
        for (let c = 0; c < COLS; c++) cubes.setColorAt(r * COLS + c, from.clone().lerp(to, c / (COLS - 1)))
      deco.add(cubes)
      tile({ x: 0, z: 1.25, w: 7.9, d: 0.62, h: 0.12, color: '#0f3b34', label: 'Dense + BM25 vectors', sub: '1,024 numbers per chunk · exact words too', text: '#d9f3ec', hop: false })
      break
    }
    case 3:
      ;[
        ['PostgreSQL', 'files & chats'],
        ['Qdrant', 'vector search'],
        ['Redis', 'queue & limits'],
      ].forEach(([label, sub], k) => tile({ x: -2.8 + k * 2.8, z: 0.25, w: 2.3, d: 1.9, h: 0.4, color: '#fffaf0', label, sub }))
      break
    case 4:
      tile({ x: -0.65, z: 0.1, w: 6.6, d: 1, h: 0.26, color: '#0b2a26', label: 'Ask anything about your knowledge…', text: '#cfe9e2', hop: false })
      tile({ x: 3.3, z: 0.1, w: 1.0, d: 0.95, h: 0.3, color: '#f5b82e', label: 'Ask' })
      tile({ x: -0.65, z: 1.15, w: 6.6, d: 0.5, h: 0.1, color: '#0f3b34', label: '10 a minute · 100 a day', text: '#cfe9e2', hop: false })
      break
    case 5:
      tile({ x: -2.0, z: 0.2, w: 3.8, d: 2.1, h: 0.36, color: '#f4fbf8', label: 'Hybrid search', sub: 'dense + BM25, fused' })
      tile({ x: 2.35, z: 0.2, w: 3.3, d: 2.1, h: 0.36, color: '#f4fbf8', label: 'Top 5 passages', sub: 'after cross-encoder rerank' })
      break
    case 6:
      ;[
        ['Context', '3,000-token budget'],
        ['Sources', 'numbered [1] [2]'],
        ['Prompt', 'memory + rules'],
      ].forEach(([label, sub], k) => tile({ x: -2.8 + k * 2.8, z: 0.2, w: 2.3, d: 1.9, h: 0.36, color: '#fffaf0', label, sub }))
      break
    default:
      tile({ x: -2.0, z: 0.0, w: 3.6, d: 1.7, h: 0.36, color: '#fffaf0', label: 'Qwen3 8B', sub: 'Ollama · local · primary' })
      tile({ x: 2.1, z: 0.0, w: 3.6, d: 1.7, h: 0.36, color: '#fffaf0', label: 'Gemini', sub: 'cloud · fallback' })
      tile({ x: 0, z: 1.3, w: 7.6, d: 0.5, h: 0.1, color: '#f5b82e', label: 'Streamed answer with citations', hop: false })
  }

  // act: 0 to 1, how much this slab is the open one. focus: the part that is "in focus" (or -1).
  const update = (time, dt, act, focus, local) => {
    items.forEach((item, k) => {
      const target = (focus === k ? 0.22 : 0) + Math.sin(time * 1.6 + k * 0.9) * 0.025 * act
      item.lift = damp(item.lift, target, 10, dt)
      item.g.position.y = item.lift
    })
    if (cubes) {
      const focusCol = local * COLS
      for (let r = 0; r < ROWS; r++)
        for (let c = 0; c < COLS; c++) {
          const idle = Math.max(0, Math.sin(time * 2.6 - c * 0.55 - r * 0.9))
          const near = act > 0.5 ? Math.max(0, 1 - Math.abs(c - focusCol) / 2.5) : 0
          const sy = 1 + (idle * 0.7 + near * 1.4) * act
          dummy.position.set((c - (COLS - 1) / 2) * 0.4, 0.1 * sy, -0.75 + r * 0.42)
          dummy.scale.set(1, sy, 1)
          dummy.updateMatrix()
          cubes.setMatrixAt(r * COLS + c, dummy.matrix)
        }
      cubes.instanceMatrix.needsUpdate = true
    }
  }

  // dim = 1 for the open slab (and the one under the mouse), less for the others
  const setDim = (dim) =>
    mats.forEach(({ mat, base }) => {
      mat.color.copy(base).multiplyScalar(dim)
    })

  return { group, update, setDim, count: items.length }
}

// Builds the whole scene inside `host` and returns the function that tears it down again.
function buildScene(host, stateRef, themeRef, pickRef) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setClearColor(0x000000, 0)
  const canvas = renderer.domElement
  canvas.style.cssText = 'width:100%;height:100%;display:block;touch-action:pan-y;cursor:grab'
  host.appendChild(canvas)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100)
  const hemi = new THREE.HemisphereLight('#ffffff', '#b9c9c2', 1)
  const sun = new THREE.DirectionalLight('#ffffff', 2.1)
  sun.position.set(4, 9, 7)
  scene.add(hemi, sun)

  const root = new THREE.Group() // everything that turns when you drag
  scene.add(root)

  const slabs = Array.from({ length: N }, (_, i) => makeSlab(i))
  const state = slabs.map((s, i) => ({ y: restY(i), act: i === 0 ? 1 : 0, hover: 0 }))
  slabs.forEach((s) => root.add(s.group))

  // the thread: one lit segment in every gap between two slabs, with a wider faint halo around it
  const threadMats = []
  const threads = Array.from({ length: N - 1 }, () => {
    const core = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1, 8), new THREE.MeshBasicMaterial({ color: '#f5b82e', transparent: true }))
    const halo = new THREE.Mesh(
      new THREE.CylinderGeometry(0.11, 0.11, 1, 12),
      new THREE.MeshBasicMaterial({ color: '#f5b82e', transparent: true, opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false }),
    )
    threadMats.push(core.material, halo.material)
    const g = new THREE.Group()
    g.add(core, halo)
    g.position.z = THREAD_Z
    root.add(g)
    return { g, lit: 0 }
  })

  const pulse = new THREE.Group()
  pulse.add(
    new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 16), new THREE.MeshBasicMaterial({ color: '#fff3c4' })),
    new THREE.Mesh(
      new THREE.SphereGeometry(0.26, 16, 16),
      new THREE.MeshBasicMaterial({ color: '#f5b82e', transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending, depthWrite: false }),
    ),
  )
  pulse.position.z = THREAD_Z
  root.add(pulse)

  // a soft shadow on the ground under the stack
  const shadowMat = new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, opacity: 0.3, depthWrite: false })
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(14, 9), shadowMat)
  shadow.rotation.x = -Math.PI / 2
  shadow.position.y = restY(N - 1) - SLAB_H / 2 - 0.65
  root.add(shadow)

  // ── size ──
  let width = 1
  let height = 1
  const resize = () => {
    width = Math.max(1, host.clientWidth)
    height = Math.max(1, host.clientHeight)
    renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
  }
  resize()
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(host)

  // ── mouse: hover, click, drag ──
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  let hover = -1
  let yaw = 0
  let yawTarget = 0
  let drag = null // { x, yaw, moved }
  let pointerX = 0 // -1 to 1, for a slight lean towards the mouse
  let pointerY = 0

  const slabOf = (object) => {
    for (let o = object; o; o = o.parent) if (o.userData.slab !== undefined) return o.userData.slab
    return -1
  }
  const setPointer = (e) => {
    const rect = canvas.getBoundingClientRect()
    pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -(((e.clientY - rect.top) / rect.height) * 2 - 1))
    pointerX = pointer.x
    pointerY = pointer.y
  }
  const pick = () => {
    raycaster.setFromCamera(pointer, camera)
    const hit = raycaster.intersectObjects(slabs.map((s) => s.group), true)[0]
    return hit ? slabOf(hit.object) : -1
  }
  const onMove = (e) => {
    setPointer(e)
    if (drag) {
      const dx = e.clientX - drag.x
      if (Math.abs(dx) > 5) drag.moved = true
      yawTarget = clamp(drag.yaw + dx * 0.006, -0.9, 0.9)
      canvas.style.cursor = 'grabbing'
      return
    }
    hover = pick()
    canvas.style.cursor = hover >= 0 ? 'pointer' : 'grab'
  }
  const onDown = (e) => {
    setPointer(e)
    drag = { x: e.clientX, yaw: yawTarget, moved: false }
    canvas.setPointerCapture(e.pointerId)
  }
  const onUp = (e) => {
    if (drag && !drag.moved) {
      setPointer(e)
      const index = pick()
      if (index >= 0) pickRef.current?.(index)
    }
    drag = null
    yawTarget = 0 // swing back
    canvas.style.cursor = hover >= 0 ? 'pointer' : 'grab'
  }
  const onLeave = () => {
    if (!drag) hover = -1
    pointerX = pointerY = 0
  }
  canvas.addEventListener('pointermove', onMove)
  canvas.addEventListener('pointerdown', onDown)
  canvas.addEventListener('pointerup', onUp)
  canvas.addEventListener('pointercancel', onUp)
  canvas.addEventListener('pointerleave', onLeave)

  // ── the loop (only while the section is on screen) ──
  let raf = 0
  let running = false
  let last = performance.now()
  let camY = restY(0)
  let leanX = 0
  let leanY = 0

  const frame = (now) => {
    if (!running) return
    raf = requestAnimationFrame(frame)
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    const time = now / 1000
    const { active, local } = stateRef.current
    const dark = themeRef.current === 'dark'

    // slabs: lifted above the open one, hovered one rises a little, dim unless open or hovered
    slabs.forEach((slab, i) => {
      const s = state[i]
      s.act = damp(s.act, i === active ? 1 : 0, 6, dt)
      s.hover = damp(s.hover, i === hover ? 1 : 0, 12, dt)
      s.y = damp(s.y, restY(i) + (i < active ? OPEN : 0) + s.hover * 0.14, 5, dt)
      slab.group.position.y = s.y
      slab.setDim(0.84 + 0.16 * Math.max(s.act, s.hover * 0.85))
      const focus = s.act > 0.5 && slab.count > 1 ? clamp(Math.floor(local * slab.count), 0, slab.count - 1) : -1
      slab.update(time, dt, s.act, focus, local)
    })

    // thread: lit down to the open slab, dim below; the pulse runs down to it
    threads.forEach((t, j) => {
      const top = state[j].y - SLAB_H / 2
      const bottom = state[j + 1].y + SLAB_H / 2
      const len = Math.max(0.001, top - bottom)
      t.g.scale.y = len
      t.g.position.y = (top + bottom) / 2
      t.lit = damp(t.lit, j < active ? 1 : 0.22, 6, dt)
      t.g.children[0].material.opacity = t.lit
      t.g.children[1].material.opacity = 0.18 * t.lit
    })
    const yStart = state[0].y - SLAB_H / 2
    const yEnd = state[Math.max(active, 1)].y + SLAB_H / 2
    const cycle = (time * 0.55) % 1
    pulse.visible = active > 0
    pulse.position.y = yStart + (yEnd - yStart) * (cycle * cycle * (3 - 2 * cycle))
    pulse.scale.setScalar(0.85 + 0.25 * Math.sin(time * 6))

    // light and ground follow the theme
    hemi.intensity = dark ? 0.85 : 1.05
    sun.intensity = dark ? 1.7 : 2.1
    shadowMat.opacity = dark ? 0.6 : 0.3

    // turning: drag target, a slow sway, and a slight lean towards the mouse
    yaw = damp(yaw, yawTarget, drag ? 14 : 3, dt)
    leanX = damp(leanX, pointerX, 3, dt)
    leanY = damp(leanY, pointerY, 3, dt)
    root.rotation.y = yaw + Math.sin(time * 0.35) * 0.04 + leanX * 0.06
    root.rotation.x = leanY * -0.02

    // camera: follows the open slab, and sits further back on a narrow stage
    camY = damp(camY, state[active].y * 0.45, 4, dt) // between the open slab and the middle of the stack, so the open slab is never at the edge
    const distance = 23 * Math.max(1, 1.3 / camera.aspect)
    const elevation = 0.5
    camera.position.set(0, camY + Math.sin(elevation) * distance, Math.cos(elevation) * distance)
    camera.lookAt(0, camY, 0)

    renderer.render(scene, camera)
  }
  const start = () => {
    if (running) return
    running = true
    last = performance.now()
    raf = requestAnimationFrame(frame)
  }
  const stop = () => {
    running = false
    cancelAnimationFrame(raf)
  }
  const visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()), { threshold: 0 })
  visibility.observe(host)

  return () => {
    stop()
    visibility.disconnect()
    resizeObserver.disconnect()
    canvas.removeEventListener('pointermove', onMove)
    canvas.removeEventListener('pointerdown', onDown)
    canvas.removeEventListener('pointerup', onUp)
    canvas.removeEventListener('pointercancel', onUp)
    canvas.removeEventListener('pointerleave', onLeave)
    scene.traverse((o) => {
      o.geometry?.dispose()
      const materials = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
      materials.forEach((m) => {
        m.map?.dispose()
        m.dispose()
      })
      o.dispose?.()
    })
    renderer.dispose()
    canvas.remove()
  }
}

function Scene({ stateRef, theme, onPick }) {
  const hostRef = useRef(null)
  const themeRef = useRef(theme)
  const pickRef = useRef(onPick)
  useEffect(() => {
    themeRef.current = theme
    pickRef.current = onPick
  })

  useEffect(() => {
    let gone = false
    let teardown = () => {}
    loadThree().then(() => {
      if (!gone) teardown = buildScene(hostRef.current, stateRef, themeRef, pickRef)
    })
    return () => {
      gone = true
      teardown()
    }
  }, [stateRef])

  return <div
      ref={hostRef}
      className="absolute inset-0"
      aria-hidden="true"
      // the stack is taller than the stage, so its top and bottom fade out instead of being cut off by a hard line
      style={{ maskImage: 'linear-gradient(to bottom, transparent, #000 10%, #000 90%, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, #000 10%, #000 90%, transparent)' }}
    />
}

// ── How it works: a 3D stack of eight layers that opens up, one layer at a time, as you scroll ────────────────────────
// Like the Features section, the section is much taller than the screen and its content is `sticky`: `useScroll` gives the
// progress p (0 → 1), `useSpring` smooths it, and p × 8 says which step is open (`active`) and how far through it we are
// (`local`). The 3D scene (further down in this file) reads { active, local } from a ref, so scrolling never re-renders it; the
// text panel is React state that changes only when the open step, or the number of sub-steps shown, changes.
//
// Without the 3D experience (a phone or a small window, "reduce motion", or no WebGL) the same content is shown as plain
// cards, all open, with no scrolling effect.

const STEP_VH = 85 // screen heights of scrolling for each step

function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

function useMediaQuery(query) {
  const subscribe = useCallback(
    (onChange) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false)
}

export default function HowItWorks() {
  const reduced = useReducedMotion()
  const desktop = useMediaQuery('(min-width: 1024px)')
  const [webgl] = useState(supportsWebGL)
  return !reduced && desktop && webgl ? <ScrollStack /> : <PlainSteps />
}

function Heading() {
  return (
    <div className="text-center">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-ink">How it works</p>
      <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl lg:text-5xl">From your files to a cited answer</h2>
      <p className="mx-auto mt-3 hidden max-w-xl text-stone-600 sm:block">Eight layers, each doing one job. Scroll to open them and see what really happens inside.</p>
    </div>
  )
}

function Chips({ items }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((chip) => (
        <li key={chip} className="rounded-full border border-stone-200 bg-stone-50 px-2.5 py-0.5 text-xs font-medium text-stone-600">
          {chip}
        </li>
      ))}
    </ul>
  )
}

// ── the scroll experience ──
function ScrollStack() {
  const { theme } = useTheme()
  const sectionRef = useRef(null)
  const stateRef = useRef({ active: 0, local: 0 }) // read by the 3D scene on every frame
  const near = useInView(sectionRef, { margin: '700px 0px 700px 0px', once: true })
  const [shown, setShown] = useState({ active: 0, count: 1 }) // which step the panel shows, and how many of its sub-steps

  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start start', 'end end'] })
  const progress = useSpring(scrollYProgress, { stiffness: 140, damping: 30, mass: 0.4 })

  useMotionValueEvent(progress, 'change', (p) => {
    const pos = clamp(p, 0, 0.9999) * N
    const active = Math.floor(pos)
    const local = pos - active
    stateRef.current = { active, local }
    const total = STEPS[active].details.length
    const count = Math.min(total, Math.floor(local * 1.3 * total) + 1) // all of them are there before the next step starts
    setShown((s) => (s.active === active && s.count === count ? s : { active, count }))
  })

  // clicking a slab, or a number, scrolls to the middle of that step's stretch
  const goTo = useCallback((i) => {
    const el = sectionRef.current
    if (!el) return
    const top = el.getBoundingClientRect().top + window.scrollY
    const range = el.offsetHeight - window.innerHeight
    window.scrollTo({ top: top + ((i + 0.15) / N) * range, behavior: 'smooth' })
  }, [])

  const step = STEPS[shown.active]

  return (
    <section id="how-it-works" ref={sectionRef} className="relative scroll-mt-28" style={{ height: `${N * STEP_VH + 100}vh` }}>
      <div className="sticky top-0 flex h-[100svh] flex-col px-4 pb-6 pt-24 sm:px-6">
        <div className="mx-auto flex min-h-0 w-full max-w-[1400px] flex-1 flex-col gap-4">
          <Heading />

          <div className="grid min-h-0 flex-1 grid-cols-[1.2fr_0.8fr] items-center gap-8">
            {/* the 3D stack fills this box; it is only drawn once the section is close to the screen */}
            <div className="relative h-full min-h-0">
              {near && <Scene stateRef={stateRef} theme={theme} onPick={goTo} />}
            </div>

            <div>
              {/* the eight numbers: where you are, and a way to jump */}
              <div role="group" aria-label="Steps" className="mb-4 flex flex-wrap gap-1.5">
                {STEPS.map((s, i) => (
                  <button
                    key={s.n}
                    type="button"
                    onClick={() => goTo(i)}
                    aria-label={`Step ${s.n}: ${s.title}`}
                    aria-current={i === shown.active ? 'step' : undefined}
                    className={`grid size-9 place-items-center rounded-full text-xs font-semibold transition-colors ${
                      i === shown.active ? 'bg-brand-700 text-white' : i < shown.active ? 'bg-brand-100 text-accent-ink' : 'border border-stone-200 text-stone-600 hover:bg-stone-100'
                    }`}
                  >
                    {s.n}
                  </button>
                ))}
              </div>

              <article key={step.n} className="hiw-panel-in rounded-2xl border border-stone-200 bg-surface p-6 shadow-[0_18px_40px_-24px_rgb(15_43_39/0.35)]" aria-live="polite">
                <p className="text-sm font-semibold uppercase tracking-[0.14em] text-accent-ink">
                  Step {step.n} of {String(N).padStart(2, '0')}
                </p>
                <h3 className="mt-1 font-display text-3xl font-semibold text-ink">{step.title}</h3>
                <p className="mt-2 text-stone-600">{step.lead}</p>
                <ol className="mt-5 space-y-3">
                  {step.details.map((d, k) => (
                    <li
                      key={d.h}
                      className="flex gap-3 motion-safe:transition-[opacity,transform] motion-safe:duration-500"
                      style={{ opacity: k < shown.count ? 1 : 0.18, transform: k < shown.count ? 'none' : 'translateY(6px)' }}
                    >
                      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-brand-700 text-[11px] font-semibold text-white">{k + 1}</span>
                      <p className="text-sm leading-relaxed text-stone-600">
                        <strong className="font-semibold text-ink">{d.h}. </strong>
                        {d.t}
                      </p>
                    </li>
                  ))}
                </ol>
                <div className="mt-5">
                  <Chips items={step.chips} />
                </div>
              </article>
            </div>
          </div>
        </div>
      </div>

      {/* the stack is a picture; this is the same information for a screen reader, all eight steps at once */}
      <ol className="sr-only">
        {STEPS.map((s) => (
          <li key={s.n}>
            {s.title}. {s.lead} {s.details.map((d) => `${d.h}: ${d.t}`).join(' ')}
          </li>
        ))}
      </ol>
    </section>
  )
}

// ── the plain version: every step as a card, nothing to scroll through ──
function PlainSteps() {
  return (
    <section id="how-it-works" className="scroll-mt-28 px-4 py-24 sm:px-6">
      <div className="mx-auto max-w-[1100px]">
        <Heading />
        <ol className="mt-10 grid gap-4 md:grid-cols-2">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-2xl border border-stone-200 bg-surface p-5">
              <div className="flex items-center gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-700 text-sm font-semibold text-white">{s.n}</span>
                <h3 className="font-display text-2xl font-semibold text-ink">{s.title}</h3>
              </div>
              <p className="mt-2 text-stone-600">{s.lead}</p>
              <ul className="mt-3 space-y-2">
                {s.details.map((d) => (
                  <li key={d.h} className="text-sm leading-relaxed text-stone-600">
                    <strong className="font-semibold text-ink">{d.h}. </strong>
                    {d.t}
                  </li>
                ))}
              </ul>
              <div className="mt-4">
                <Chips items={s.chips} />
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
