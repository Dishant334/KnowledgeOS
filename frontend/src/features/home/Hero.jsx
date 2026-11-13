import { useAuth } from '@clerk/clerk-react'
import { useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTheme } from '../../theme/useTheme'

// ── Hero: the first screen ──────────────────────────────────────────────────────────────────────────────────────────────
// Text on the left (headline, pitch, buttons, one line of proof), a 3D scene filling the rest of the screen behind it.
//
// THE DESK IS THE CHOSEN SCENE ("/"). The others are kept for now at "/?hero=a | c | prism | ink" and will be deleted later.
//   A. Documents become an answer: hundreds of pages turn in a slow, tilted vortex; a few passages are highlighted in amber
//      and streams of light run from them into a cited answer card at the front. The vortex leans towards the mouse, and
//      while the hero scrolls away the pages fall into a neat stack.
//   C. The living page: one large handbook page ripples like cloth and bulges where the cursor blows on it; a highlighter
//      marks the answering passage, which peels off, flies into the chat card, and the card types out the cited answer.
//
// Performance: the text is plain HTML and appears at once. three.js is loaded by a dynamic import (its own chunk, shared
// with "How it works"), the canvas fades in once the first frame is drawn, the loop runs only while the hero is on screen,
// and phones get fewer pages. With "reduce motion" the scene is drawn once and stands still; without WebGL there is no
// scene, only the text.

let THREE
async function loadThree() {
  if (!THREE) THREE = await import('three')
}

function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
const damp = (current, target, lambda, dt) => current + (target - current) * (1 - Math.exp(-lambda * dt))
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const DISPLAY = '"Fraunces Variable", Georgia, serif'
const SANS = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'

function seeded(seed) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// ── Scene A: textures ──

// A page of a document, drawn on a canvas. kind: 'text' | 'table' | 'slide' | 'highlight'
function pageTexture(kind, seed) {
  const random = seeded(seed)
  const W = 256
  const H = 340
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#fbfaf5'
  ctx.fillRect(0, 0, W, H)
  ctx.strokeStyle = 'rgba(26,35,33,0.08)'
  ctx.lineWidth = 4
  ctx.strokeRect(2, 2, W - 4, H - 4)
  const line = (y, w, color = '#d6d1c6', h = 7) => {
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.roundRect(26, y, w, h, 3.5)
    ctx.fill()
  }
  // a title
  line(30, 120 + random() * 50, '#1a2321', 11)
  if (kind === 'slide') {
    ctx.fillStyle = '#cdeee5'
    ctx.beginPath()
    ctx.roundRect(26, 62, W - 52, 140, 10)
    ctx.fill()
    ctx.fillStyle = '#0f6b5c'
    ctx.beginPath()
    ctx.arc(80, 132, 26, 0, Math.PI * 2)
    ctx.fill()
    for (let k = 0; k < 5; k++) line(222 + k * 20, 110 + random() * 90)
  } else if (kind === 'table') {
    ctx.strokeStyle = '#d6d1c6'
    ctx.lineWidth = 2
    for (let r = 0; r < 9; r++) {
      const y = 64 + r * 28
      ctx.strokeRect(26, y, W - 52, 28)
      ctx.fillStyle = r === 0 ? '#0f6b5c' : '#d6d1c6'
      for (let c = 0; c < 3; c++) ctx.fillRect(34 + c * 66, y + 11, 30 + random() * 22, 6)
    }
  } else {
    const highlightAt = kind === 'highlight' ? 4 + Math.floor(random() * 4) : -1
    for (let k = 0; k < 13; k++) {
      const y = 64 + k * 20
      const w = k % 5 === 4 ? 90 + random() * 60 : 170 + random() * 34
      if (k === highlightAt || k === highlightAt + 1) {
        ctx.fillStyle = 'rgba(245,184,46,0.85)'
        ctx.beginPath()
        ctx.roundRect(20, y - 6, w + 12, 19, 4)
        ctx.fill()
        line(y, w, '#7a5a12')
      } else {
        line(y, w)
      }
    }
    if (kind === 'highlight') {
      // the citation badge in the margin
      ctx.fillStyle = '#0f6b5c'
      ctx.beginPath()
      ctx.arc(W - 22, 64 + highlightAt * 20 + 3, 11, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}

// The answer card: a question, an answer with two citation badges, and its two sources.
function answerTexture() {
  const W = 1200
  const H = 640
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  // card
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.roundRect(8, 8, W - 16, H - 16, 44)
  ctx.fill()
  ctx.strokeStyle = 'rgba(15,107,92,0.25)'
  ctx.lineWidth = 4
  ctx.stroke()
  // question bubble
  ctx.fillStyle = '#e4f4ef'
  ctx.beginPath()
  ctx.roundRect(W - 600, 46, 548, 74, 37)
  ctx.fill()
  ctx.fillStyle = '#1a2321'
  ctx.font = `500 34px ${SANS}`
  ctx.textBaseline = 'middle'
  ctx.fillText('How many leave days do I get?', W - 572, 84)
  // name
  ctx.fillStyle = '#0f6b5c'
  ctx.font = `700 34px ${DISPLAY}`
  ctx.fillText('KnowledgeOS', 60, 176)
  // the answer, with badges
  const lines = [
    ['You get 24 days of paid annual leave'],
    ['per year ', 1, '. Up to 5 unused days carry'],
    ['over to the next year ', 2, '.'],
  ]
  ctx.font = `400 44px ${SANS}`
  lines.forEach((parts, row) => {
    let x = 60
    const y = 250 + row * 64
    for (const part of parts) {
      if (typeof part === 'number') {
        ctx.fillStyle = '#f5b82e'
        ctx.beginPath()
        ctx.arc(x + 22, y, 22, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = '#1a2321'
        ctx.font = `700 28px ${SANS}`
        ctx.textAlign = 'center'
        ctx.fillText(String(part), x + 22, y + 1)
        ctx.textAlign = 'left'
        ctx.font = `400 44px ${SANS}`
        x += 50
      } else {
        ctx.fillStyle = '#1a2321'
        ctx.fillText(part, x, y)
        x += ctx.measureText(part).width
      }
    }
  })
  // sources
  const chip = (x, n, label) => {
    ctx.font = `500 28px ${SANS}`
    const w = ctx.measureText(label).width + 86
    ctx.fillStyle = '#f6f3ec'
    ctx.beginPath()
    ctx.roundRect(x, 486, w, 70, 35)
    ctx.fill()
    ctx.fillStyle = '#0f6b5c'
    ctx.beginPath()
    ctx.arc(x + 36, 521, 18, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#ffffff'
    ctx.font = `700 22px ${SANS}`
    ctx.textAlign = 'center'
    ctx.fillText(String(n), x + 36, 522)
    ctx.textAlign = 'left'
    ctx.fillStyle = '#44403c'
    ctx.font = `500 28px ${SANS}`
    ctx.fillText(label, x + 66, 522)
    return w
  }
  const first = chip(60, 1, 'Handbook_2026.pdf · p.2')
  chip(60 + first + 20, 2, 'Leave_policy.md')
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  return texture
}

// `outer` must be the same colour as `inner` with alpha 0: fading to transparent BLACK leaves a grey fringe
function glowTexture(inner, outer) {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  g.addColorStop(0, inner)
  g.addColorStop(1, outer)
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

// ── Scene A: the vortex ──
// Builds everything inside `host` and returns the function that tears it down.
function buildVortex(host, { section, themeRef, reduced, onFirstFrame }) {
  const narrow = host.clientWidth < 768
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
  renderer.setClearColor(0x000000, 0)
  const canvas = renderer.domElement
  canvas.style.cssText = 'width:100%;height:100%;display:block'
  host.appendChild(canvas)

  const scene = new THREE.Scene()
  const fogColor = new THREE.Color()
  scene.fog = new THREE.Fog(fogColor, 9, 17)
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 60)
  camera.position.set(0, 0.5, 10)
  camera.lookAt(0, 0, 0)
  const hemi = new THREE.HemisphereLight('#ffffff', '#c9d6cf', 1.25)
  const sun = new THREE.DirectionalLight('#fff4e0', 1.6)
  sun.position.set(-4, 6, 8)
  scene.add(hemi, sun)

  const vortex = new THREE.Group() // turns; holds the pages
  // on a phone the scene has its own box under the text, so it is centred there
  const center = new THREE.Vector3(narrow ? 0 : 2.75, narrow ? 0.15 : -0.15, 0)
  vortex.position.copy(center)
  if (narrow) vortex.scale.setScalar(0.8)
  scene.add(vortex)

  // pages: four kinds, one instanced mesh each
  const pageGeometry = new THREE.PlaneGeometry(0.46, 0.61)
  const kinds = ['text', 'text', 'table', 'slide']
  const total = narrow ? 110 : 220
  const random = seeded(11)
  const meshes = kinds.map((kind, k) => {
    const material = new THREE.MeshStandardMaterial({ map: pageTexture(kind, 100 + k), side: THREE.DoubleSide, roughness: 0.85 })
    const mesh = new THREE.InstancedMesh(pageGeometry, material, Math.ceil(total / kinds.length))
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
    vortex.add(mesh)
    return mesh
  })
  const makeOrbit = (front = false) => {
    const r = front ? 1.5 + random() * 0.9 : 0.9 + Math.pow(random(), 0.85) * 2.1
    return {
      r,
      angle: random() * Math.PI * 2,
      speed: 0.22 / Math.sqrt(r), // inner pages turn faster, like a real vortex
      y: (random() - 0.5) * (0.35 + r * 0.28),
      phase: random() * Math.PI * 2,
      tilt: (random() - 0.5) * 0.9,
      turn: random() * Math.PI * 2,
    }
  }
  const pages = meshes.map((mesh) => Array.from({ length: mesh.count }, () => makeOrbit()))

  // the highlighted pages: the passages the answer cites; each sends a stream of light to the card
  const highlighted = Array.from({ length: 4 }, (_, k) => {
    const mesh = new THREE.Mesh(
      pageGeometry,
      new THREE.MeshStandardMaterial({ map: pageTexture('highlight', 200 + k), side: THREE.DoubleSide, roughness: 0.7, emissive: '#f5b82e', emissiveIntensity: 0.12 }),
    )
    mesh.scale.setScalar(1.12)
    vortex.add(mesh)
    const orbit = makeOrbit(true)
    orbit.angle = (k / 4) * Math.PI * 2 + 0.4
    return { mesh, orbit }
  })

  // the answer card, always facing the camera, with a soft glow behind it
  const card = new THREE.Mesh(
    new THREE.PlaneGeometry(2.7, 1.44),
    new THREE.MeshBasicMaterial({ map: answerTexture(), transparent: true, toneMapped: false, fog: false, depthTest: false }),
  )
  card.renderOrder = 10 // the answer is the point: never hidden behind a page
  const cardHome = new THREE.Vector3(center.x + (narrow ? 0 : -0.75), center.y + (narrow ? -0.2 : 0.15), 2.4)
  card.scale.setScalar(narrow ? 0.64 : 0.8)
  scene.add(card)
  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: glowTexture('rgba(127,216,200,0.45)', 'rgba(127,216,200,0)'), transparent: true, depthWrite: false, depthTest: false, fog: false }),
  )
  glow.renderOrder = 9
  glow.scale.set(narrow ? 3.4 : 4.6, narrow ? 2.6 : 3.4, 1)
  scene.add(glow)

  // the streams of light: dots that run along a curve from each highlighted page to the card
  const DOTS = 26
  const dotPositions = new Float32Array(highlighted.length * DOTS * 3)
  const dotColors = new Float32Array(highlighted.length * DOTS * 4) // rgba: each dot fades on its own
  const dotGeometry = new THREE.BufferGeometry()
  dotGeometry.setAttribute('position', new THREE.BufferAttribute(dotPositions, 3))
  dotGeometry.setAttribute('color', new THREE.BufferAttribute(dotColors, 4))
  const dots = new THREE.Points(
    dotGeometry,
    new THREE.PointsMaterial({
      size: narrow ? 0.08 : 0.11,
      map: glowTexture('rgba(255,255,255,1)', 'rgba(255,255,255,0)'),
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      fog: false,
      depthTest: false,
    }),
  )
  dots.renderOrder = 11
  scene.add(dots)
  const amber = new THREE.Color('#e9a514')

  // ── input ──
  const pointer = { x: 0, y: 0 }
  const lean = { x: 0, y: 0 }
  const onPointer = (e) => {
    if (e.pointerType === 'touch') return
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1
    pointer.y = (e.clientY / window.innerHeight) * 2 - 1
  }
  window.addEventListener('pointermove', onPointer)

  const resize = () => {
    const w = Math.max(1, host.clientWidth)
    const h = Math.max(1, host.clientHeight)
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  resize()
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(host)

  // ── the loop ──
  const dummy = new THREE.Object3D()
  const orbitQ = new THREE.Quaternion()
  const stackQ = new THREE.Quaternion()
  const euler = new THREE.Euler()
  const pos = new THREE.Vector3()
  const stackPos = new THREE.Vector3()
  const source = new THREE.Vector3()
  const target = new THREE.Vector3()
  const control = new THREE.Vector3()
  let raf = 0
  let running = false
  let last = performance.now()
  let first = true

  const place = (orbit, t, collapse, index, object) => {
    const angle = orbit.angle + orbit.speed * t
    pos.set(Math.cos(angle) * orbit.r, orbit.y + Math.sin(t * 0.7 + orbit.phase) * 0.12, Math.sin(angle) * orbit.r)
    euler.set(orbit.tilt + Math.sin(t * 0.45 + orbit.phase) * 0.35, -angle + orbit.turn, Math.sin(t * 0.3 + orbit.phase) * 0.25)
    orbitQ.setFromEuler(euler)
    // the stack they fall into while the hero scrolls away
    stackPos.set((index % 3) * 0.04 - 0.04, -1.55 + index * 0.0065, (index % 5) * 0.02)
    euler.set(-Math.PI / 2, 0, (index % 7) * 0.05 - 0.15)
    stackQ.setFromEuler(euler)
    object.position.lerpVectors(pos, stackPos, collapse)
    object.quaternion.slerpQuaternions(orbitQ, stackQ, collapse)
  }

  const render = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    const t = reduced ? 8 : now / 1000
    const dark = themeRef.current === 'dark'
    fogColor.set(dark ? '#1c1c1c' : '#ffffff')
    hemi.intensity = dark ? 0.85 : 1.25

    lean.x = damp(lean.x, pointer.x, 2.2, dt)
    lean.y = damp(lean.y, pointer.y, 2.2, dt)
    const scrolled = reduced || narrow ? 0 : clamp(window.scrollY / (section.offsetHeight * 0.85)) // phones: the scene is under the text, so no collapse
    const collapse = easeInOut(scrolled)
    vortex.rotation.set(-0.36 + lean.y * 0.14 + collapse * 0.3, lean.x * 0.32, lean.x * -0.05)

    let index = 0
    meshes.forEach((mesh, m) => {
      pages[m].forEach((orbit, i) => {
        place(orbit, t, collapse, index++, dummy)
        dummy.updateMatrix()
        mesh.setMatrixAt(i, dummy.matrix)
      })
      mesh.instanceMatrix.needsUpdate = true
    })
    highlighted.forEach(({ mesh, orbit }, k) => place(orbit, t, collapse, total + k, mesh))

    // card: bobs gently, faces the camera, fades as the pages fall into the stack
    card.position.set(cardHome.x + lean.x * 0.15, cardHome.y + Math.sin(t * 1.1) * 0.06 - collapse * 0.6, cardHome.z)
    card.quaternion.copy(camera.quaternion)
    card.material.opacity = 1 - collapse
    glow.position.set(card.position.x, card.position.y, card.position.z - 0.4)
    glow.material.opacity = (0.55 + Math.sin(t * 1.6) * 0.15) * (1 - collapse)

    // streams: from each highlighted page (only while it is in the front half) to the left edge of the card
    vortex.updateMatrixWorld()
    highlighted.forEach(({ mesh }, b) => {
      mesh.getWorldPosition(source)
      const visible = clamp((source.z + 1.2) / 1.6) * (1 - collapse)
      target.set(card.position.x - (narrow ? 0.7 : 1.05), card.position.y + (b - 1.5) * 0.18, card.position.z)
      control.lerpVectors(source, target, 0.5)
      control.y += 0.9
      control.z += 0.6
      for (let k = 0; k < DOTS; k++) {
        const p = (t * 0.32 + k / DOTS + b * 0.17) % 1
        const a = (1 - p) * (1 - p)
        const bb = 2 * (1 - p) * p
        const c = p * p
        const o = (b * DOTS + k) * 3
        dotPositions[o] = a * source.x + bb * control.x + c * target.x
        dotPositions[o + 1] = a * source.y + bb * control.y + c * target.y
        dotPositions[o + 2] = a * source.z + bb * control.z + c * target.z
        const c4 = (b * DOTS + k) * 4
        dotColors[c4] = amber.r
        dotColors[c4 + 1] = amber.g
        dotColors[c4 + 2] = amber.b
        dotColors[c4 + 3] = Math.sin(Math.PI * p) * visible // fades in and out along the stream
      }
    })
    dotGeometry.attributes.position.needsUpdate = true
    dotGeometry.attributes.color.needsUpdate = true

    renderer.render(scene, camera)
    if (first) {
      first = false
      onFirstFrame()
    }
  }

  const frame = (now) => {
    if (!running) return
    raf = requestAnimationFrame(frame)
    render(now)
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
  let visibility = null
  if (reduced) {
    render(performance.now())
  } else {
    visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()))
    visibility.observe(host)
  }

  return () => {
    stop()
    visibility?.disconnect()
    resizeObserver.disconnect()
    window.removeEventListener('pointermove', onPointer)
    scene.traverse((o) => {
      o.geometry?.dispose()
      const materials = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
      materials.forEach((m) => {
        m.map?.dispose()
        m.dispose()
      })
    })
    renderer.dispose()
    canvas.remove()
  }
}

// ── Scene C: the living page ────────────────────────────────────────────────────────────────────────────────────────
// One large page of a handbook floats and ripples like cloth; the cursor is a breeze that makes it bulge. Every 10 seconds:
// an amber highlighter sweeps over the passage that answers the question, the passage peels off the page, curls and
// flies into the chat card, and the card types out the answer with its citation. While the hero scrolls away the page
// tips back and sinks.

const PAGE_W = 3
const PAGE_H = 3.9
const PAGE_PX_W = 900
const PAGE_PX_H = 1170
const PAGE_LINES = [
  'All employees are entitled to paid time off to rest',
  'and recharge. This section explains how leave is',
  'earned, requested and carried over.',
  'Full-time employees receive 24 days of paid annual',
  'leave per calendar year, plus public holidays.',
  'Part-time employees receive leave pro rata, based',
  'on their contracted hours.',
  '',
  '#4.2  Carrying leave over',
  'Up to 5 unused days may be carried over to the next',
  'year. They must be used by the end of March.',
  'Requests are made in the HR portal at least two',
  'weeks in advance.',
]
const CITED = [3, 4] // the lines that answer the question
const LINE_TOP = 300
const LINE_STEP = 54
const MARGIN = 72

// the handbook page; `highlight` 0 → 1 sweeps the amber over the cited lines
function makePage() {
  const canvas = document.createElement('canvas')
  canvas.width = PAGE_PX_W
  canvas.height = PAGE_PX_H
  const ctx = canvas.getContext('2d')
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  let drawn = -1
  const draw = (highlight) => {
    const h = Math.round(highlight * 60) / 60 // only redraw when it visibly changes
    if (h === drawn) return
    drawn = h
    ctx.fillStyle = '#fbfaf5'
    ctx.fillRect(0, 0, PAGE_PX_W, PAGE_PX_H)
    ctx.strokeStyle = 'rgba(26,35,33,0.1)'
    ctx.lineWidth = 3
    ctx.strokeRect(1.5, 1.5, PAGE_PX_W - 3, PAGE_PX_H - 3)
    ctx.textBaseline = 'alphabetic'
    ctx.fillStyle = '#78716c'
    ctx.font = `600 20px ${SANS}`
    ctx.fillText('EMPLOYEE HANDBOOK 2026', MARGIN, 96)
    ctx.textAlign = 'right'
    ctx.fillText('p. 2', PAGE_PX_W - MARGIN, 96)
    ctx.textAlign = 'left'
    ctx.fillStyle = '#e7e2d6'
    ctx.fillRect(MARGIN, 118, PAGE_PX_W - 2 * MARGIN, 2)
    ctx.fillStyle = '#1a2321'
    ctx.font = `600 58px ${DISPLAY}`
    ctx.fillText('4. Annual leave', MARGIN, 214)
    PAGE_LINES.forEach((line, i) => {
      const y = LINE_TOP + i * LINE_STEP
      const heading = line.startsWith('#')
      const text = heading ? line.slice(1) : line
      ctx.font = heading ? `700 30px ${SANS}` : `400 29px ${SANS}`
      const k = CITED.indexOf(i)
      if (k >= 0 && h > 0) {
        const share = clamp(h * CITED.length - k) // the lines fill one after the other
        const width = ctx.measureText(text).width
        ctx.fillStyle = 'rgba(245,184,46,0.75)'
        ctx.beginPath()
        ctx.roundRect(MARGIN - 8, y - 34, (width + 16) * share, 46, 6)
        ctx.fill()
      }
      ctx.fillStyle = heading ? '#1a2321' : '#44403c'
      ctx.fillText(text, MARGIN, y)
    })
    if (h >= 1) {
      // the citation number appears in the margin once the passage is marked
      ctx.fillStyle = '#0f6b5c'
      ctx.beginPath()
      ctx.arc(MARGIN - 36, LINE_TOP + CITED[0] * LINE_STEP + 12, 15, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = '#ffffff'
      ctx.font = `700 18px ${SANS}`
      ctx.textAlign = 'center'
      ctx.fillText('1', MARGIN - 36, LINE_TOP + CITED[0] * LINE_STEP + 18)
      ctx.textAlign = 'left'
    }
    texture.needsUpdate = true
  }
  draw(0)
  return { texture, draw }
}

// the passage that peels off: the two cited lines on amber
function makeStrip() {
  const W = PAGE_PX_W - 2 * MARGIN + 32
  const H = CITED.length * LINE_STEP + 18
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#f7c55a'
  ctx.beginPath()
  ctx.roundRect(0, 0, W, H, 10)
  ctx.fill()
  ctx.fillStyle = '#1a2321'
  ctx.font = `400 29px ${SANS}`
  CITED.forEach((line, k) => ctx.fillText(PAGE_LINES[line], 16, 44 + k * LINE_STEP))
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return { texture, pxW: W, pxH: H }
}

// the chat card; `typed` = how many characters of the answer are shown, `sources` = show the source chip
function makeChat() {
  const W = 1100
  const H = 560
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  const answer = [['Full-time employees get 24 days of paid'], ['annual leave a year ', 1, ', plus public holidays.']]
  const totalChars = answer.flat().reduce((n, part) => n + (typeof part === 'number' ? 1 : part.length), 0)
  let drawn = ''
  const draw = (typed, sources) => {
    const key = `${typed}|${sources}`
    if (key === drawn) return
    drawn = key
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.roundRect(8, 8, W - 16, H - 16, 40)
    ctx.fill()
    ctx.strokeStyle = 'rgba(15,107,92,0.25)'
    ctx.lineWidth = 4
    ctx.stroke()
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#e4f4ef'
    ctx.beginPath()
    ctx.roundRect(W - 560, 40, 512, 70, 35)
    ctx.fill()
    ctx.fillStyle = '#1a2321'
    ctx.font = `500 32px ${SANS}`
    ctx.fillText('How many leave days do I get?', W - 534, 76)
    ctx.fillStyle = '#0f6b5c'
    ctx.font = `700 32px ${DISPLAY}`
    ctx.fillText('KnowledgeOS', 56, 166)
    let left = typed
    answer.forEach((parts, row) => {
      let x = 56
      const y = 236 + row * 62
      for (const part of parts) {
        if (left <= 0) break
        if (typeof part === 'number') {
          ctx.fillStyle = '#f5b82e'
          ctx.beginPath()
          ctx.arc(x + 21, y, 21, 0, Math.PI * 2)
          ctx.fill()
          ctx.fillStyle = '#1a2321'
          ctx.font = `700 26px ${SANS}`
          ctx.textAlign = 'center'
          ctx.fillText(String(part), x + 21, y + 1)
          ctx.textAlign = 'left'
          x += 48
          left -= 1
        } else {
          ctx.font = `400 41px ${SANS}`
          const shown = part.slice(0, left)
          ctx.fillStyle = '#1a2321'
          ctx.fillText(shown, x, y)
          x += ctx.measureText(shown).width
          left -= part.length
        }
      }
      // the blinking caret while typing
      if (typed > 0 && typed < totalChars && left < 0 && left > -60) {
        ctx.fillStyle = '#0f6b5c'
        ctx.fillRect(x + 4, y - 22, 4, 44)
      }
    })
    if (typed === 0) {
      // three waiting dots
      ctx.fillStyle = '#a8a29e'
      for (let k = 0; k < 3; k++) {
        ctx.beginPath()
        ctx.arc(70 + k * 30, 236, 9, 0, Math.PI * 2)
        ctx.fill()
      }
    }
    if (sources) {
      ctx.font = `500 27px ${SANS}`
      const label = 'Handbook_2026.pdf · p.2'
      const w = ctx.measureText(label).width + 84
      ctx.fillStyle = '#f6f3ec'
      ctx.beginPath()
      ctx.roundRect(56, 420, w, 68, 34)
      ctx.fill()
      ctx.fillStyle = '#0f6b5c'
      ctx.beginPath()
      ctx.arc(92, 454, 18, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = '#ffffff'
      ctx.font = `700 22px ${SANS}`
      ctx.textAlign = 'center'
      ctx.fillText('1', 92, 455)
      ctx.textAlign = 'left'
      ctx.fillStyle = '#44403c'
      ctx.font = `500 27px ${SANS}`
      ctx.fillText(label, 122, 455)
    }
    texture.needsUpdate = true
  }
  draw(0, false)
  return { texture, draw, totalChars }
}

function buildLivingPage(host, { section, themeRef, reduced, onFirstFrame }) {
  const narrow = host.clientWidth < 768
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
  renderer.setClearColor(0x000000, 0)
  const canvas = renderer.domElement
  canvas.style.cssText = 'width:100%;height:100%;display:block'
  host.appendChild(canvas)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 60)
  camera.position.set(0, 0.3, 10)
  camera.lookAt(0, 0, 0)
  const hemi = new THREE.HemisphereLight('#ffffff', '#dfe7e2', 1.5)
  const sun = new THREE.DirectionalLight('#fff8ec', 1.5)
  sun.position.set(-5, 5, 7)
  scene.add(hemi, sun)

  // the page: a finely divided plane, so it can ripple like cloth
  const holder = new THREE.Group()
  const home = new THREE.Vector3(narrow ? 0 : 2.6, narrow ? 0.35 : 0.15, 0)
  holder.position.copy(home)
  holder.scale.setScalar(narrow ? 0.62 : 1)
  scene.add(holder)
  const page = makePage()
  const COLS = 48
  const ROWS = 62
  const geometry = new THREE.PlaneGeometry(PAGE_W, PAGE_H, COLS, ROWS)
  const rest = geometry.attributes.position.array.slice() // the flat page
  const sheet = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: page.texture, side: THREE.DoubleSide, roughness: 0.92 }))
  holder.add(sheet)

  // a soft shadow under the page
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(PAGE_W * 1.3, PAGE_H * 1.15),
    new THREE.MeshBasicMaterial({ map: glowTexture('rgba(15,43,39,0.35)', 'rgba(15,43,39,0)'), transparent: true, depthWrite: false }),
  )
  shadow.position.set(0.25, -0.3, -0.9)
  holder.add(shadow)

  // the passage that peels off
  const stripArt = makeStrip()
  const stripW = (stripArt.pxW / PAGE_PX_W) * PAGE_W
  const stripH = (stripArt.pxH / PAGE_PX_H) * PAGE_H
  const stripGeometry = new THREE.PlaneGeometry(stripW, stripH, 24, 2)
  const stripRest = stripGeometry.attributes.position.array.slice()
  const strip = new THREE.Mesh(
    stripGeometry,
    new THREE.MeshStandardMaterial({ map: stripArt.texture, side: THREE.DoubleSide, roughness: 0.6, transparent: true, emissive: '#f5b82e', emissiveIntensity: 0.15, depthTest: false }),
  )
  strip.renderOrder = 12 // above the page and the card until it lands
  scene.add(strip)
  const stripLocal = new THREE.Vector3(
    ((MARGIN - 16 + stripArt.pxW / 2) / PAGE_PX_W - 0.5) * PAGE_W,
    (0.5 - (LINE_TOP + CITED[0] * LINE_STEP - 34 + stripArt.pxH / 2 - 9) / PAGE_PX_H) * PAGE_H,
    0.02,
  )

  // the chat card
  const chat = makeChat()
  const card = new THREE.Mesh(
    new THREE.PlaneGeometry(2.6, 1.32),
    new THREE.MeshBasicMaterial({ map: chat.texture, transparent: true, toneMapped: false, depthTest: false }),
  )
  card.renderOrder = 10
  card.scale.setScalar(narrow ? 0.62 : 0.86)
  const cardHome = new THREE.Vector3(narrow ? 0 : 1.05, narrow ? -1.25 : -0.95, 2.2)
  scene.add(card)
  const halo = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: glowTexture('rgba(127,216,200,0.5)', 'rgba(127,216,200,0)'), transparent: true, depthWrite: false, depthTest: false }),
  )
  halo.renderOrder = 9
  halo.scale.set(narrow ? 3 : 4.2, narrow ? 2 : 2.6, 1)
  scene.add(halo)

  // ── input: the cursor as a breeze, plus a lean ──
  const pointer = { x: 0, y: 0, active: false }
  const lean = { x: 0, y: 0 }
  const ndc = new THREE.Vector2()
  const raycaster = new THREE.Raycaster()
  const breeze = new THREE.Vector3(9, 9, 0) // where on the page the cursor blows (page coordinates); far away = none
  let breezeStrength = 0
  const onPointer = (e) => {
    if (e.pointerType === 'touch') return
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1
    pointer.y = (e.clientY / window.innerHeight) * 2 - 1
    const rect = canvas.getBoundingClientRect()
    ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -(((e.clientY - rect.top) / rect.height) * 2 - 1))
    pointer.active = true
  }
  window.addEventListener('pointermove', onPointer)

  const resize = () => {
    const w = Math.max(1, host.clientWidth)
    const h = Math.max(1, host.clientHeight)
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  resize()
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(host)

  // how far the cloth is lifted at a point of the page (page coordinates), at time t
  const lift = (x, y, t) => {
    const u = x / PAGE_W + 0.5 // 0 at the left edge, 1 at the right edge
    let z = 0.1 * Math.sin(1.7 * x + t * 1.25) * u + 0.07 * Math.sin(2.2 * y - t * 1.6 + x * 0.8) * u
    z += 0.22 * Math.pow(Math.max(0, u - 0.55) * 2.2, 2) * Math.sin(t * 0.9 + y * 0.6) // the free edge flutters more
    const dx = x - breeze.x
    const dy = y - breeze.y
    z -= breezeStrength * 0.38 * Math.exp(-(dx * dx + dy * dy) / 0.55) // the breeze presses a soft dent
    return z
  }

  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
  const CYCLE = 10
  const from = new THREE.Vector3()
  const to = new THREE.Vector3()
  const mid = new THREE.Vector3()
  const hit = new THREE.Vector3()
  let raf = 0
  let running = false
  let last = performance.now()
  let first = true

  const render = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    const t = reduced ? 3.1 : now / 1000
    const dark = themeRef.current === 'dark'
    hemi.intensity = dark ? 1 : 1.5
    shadow.material.opacity = dark ? 0.9 : 0.6
    const scrolled = reduced || narrow ? 0 : clamp(window.scrollY / (section.offsetHeight * 0.85))
    const away = easeInOut(scrolled)

    lean.x = damp(lean.x, pointer.x, 2, dt)
    lean.y = damp(lean.y, pointer.y, 2, dt)
    holder.rotation.set(-0.12 + lean.y * 0.1 - away * 0.9, -0.38 + lean.x * 0.22, 0.04)
    holder.position.set(home.x, home.y - away * 1.4, home.z - away * 2)
    holder.updateMatrixWorld()

    // where the cursor touches the page
    if (pointer.active && !narrow) {
      raycaster.setFromCamera(ndc, camera)
      const hits = raycaster.intersectObject(sheet)
      if (hits.length) {
        hit.copy(hits[0].point)
        sheet.worldToLocal(hit)
        breeze.lerp(hit, 0.25)
        breezeStrength = damp(breezeStrength, 1, 4, dt)
      } else breezeStrength = damp(breezeStrength, 0, 3, dt)
    }

    // ripple the cloth
    const positions = geometry.attributes.position.array
    for (let i = 0; i < positions.length; i += 3) positions[i + 2] = lift(rest[i], rest[i + 1], t)
    geometry.attributes.position.needsUpdate = true
    geometry.computeVertexNormals()

    // the story, once every CYCLE seconds
    const c = reduced ? 7 : t % CYCLE
    const highlight = c < 0.6 ? 0 : c < 2.2 ? ease((c - 0.6) / 1.6) : c < 9 ? 1 : 1 - (c - 9)
    page.draw(clamp(highlight))
    const peel = clamp((c - 2.4) / 0.8) // lifting off the page
    const fly = ease(clamp((c - 3.2) / 1.3)) // flying to the card
    const typed = Math.floor(clamp((c - 4.7) / 1.9) * chat.totalChars)
    chat.draw(c > 9.2 ? 0 : typed, c > 6.7 && c < 9.2)

    // the strip: invisible until it peels, then curls and flies into the card
    strip.visible = c > 2.4 && c < 4.6
    if (strip.visible) {
      from.copy(stripLocal)
      from.z = lift(stripLocal.x, stripLocal.y, t) + 0.03 + peel * 0.35
      holder.localToWorld(from)
      to.set(card.position.x - 0.2, card.position.y + 0.15, card.position.z - 0.1)
      mid.lerpVectors(from, to, 0.5)
      mid.y += 1.1
      mid.z += 0.8
      const a = (1 - fly) * (1 - fly)
      const b = 2 * (1 - fly) * fly
      const d = fly * fly
      strip.position.set(a * from.x + b * mid.x + d * to.x, a * from.y + b * mid.y + d * to.y, a * from.z + b * mid.z + d * to.z)
      strip.quaternion.copy(holder.quaternion).slerp(camera.quaternion, fly)
      strip.rotateZ(Math.sin(fly * Math.PI) * 0.5)
      strip.scale.setScalar(holder.scale.x * (1 - fly * 0.65))
      strip.material.opacity = 1 - clamp((fly - 0.85) / 0.15)
      // curl: the strip bends up along its length as it peels, and flattens while it flies
      const curl = peel * (1 - fly) * 0.9
      const sp = stripGeometry.attributes.position.array
      for (let i = 0; i < sp.length; i += 3) {
        const x = stripRest[i] / (stripW / 2) // −1 … 1
        sp[i + 2] = curl * (x * x) * 0.35 + curl * 0.15 * Math.sin(x * 3 + t * 4)
      }
      stripGeometry.attributes.position.needsUpdate = true
    }

    // the card: bobs, faces the camera, pulses when the passage lands, fades with scrolling
    const landed = clamp(1 - Math.abs(c - 4.55) / 0.35)
    card.position.set(cardHome.x + lean.x * 0.12, cardHome.y + Math.sin(t * 1.1) * 0.05 - away * 0.8, cardHome.z)
    card.quaternion.copy(camera.quaternion)
    card.scale.setScalar((narrow ? 0.62 : 0.86) * (1 + landed * 0.04))
    card.material.opacity = 1 - away
    halo.position.set(card.position.x, card.position.y, card.position.z - 0.3)
    halo.material.opacity = (0.45 + landed * 0.4) * (1 - away)

    renderer.render(scene, camera)
    if (first) {
      first = false
      onFirstFrame()
    }
  }

  const frame = (now) => {
    if (!running) return
    raf = requestAnimationFrame(frame)
    render(now)
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
  let visibility = null
  if (reduced) {
    render(performance.now())
  } else {
    visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()))
    visibility.observe(host)
  }

  return () => {
    stop()
    visibility?.disconnect()
    resizeObserver.disconnect()
    window.removeEventListener('pointermove', onPointer)
    scene.traverse((o) => {
      o.geometry?.dispose()
      const materials = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
      materials.forEach((m) => {
        m.map?.dispose()
        m.dispose()
      })
    })
    renderer.dispose()
    canvas.remove()
  }
}

// ── Shared stage for the prism, ink and desk scenes: renderer, camera, pointer, resize, loop, teardown ──
// `setup(stage)` adds things to stage.scene and returns update(t, dt), called every frame before the render.
function makeStage(host, { reduced, onFirstFrame, fov = 32, distance = 10, shift = 0, shadows = false, ortho = false }, setup) {
  const narrow = host.clientWidth < 768
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
  renderer.setClearColor(0x000000, 0)
  if (shadows) {
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
  }
  const canvas = renderer.domElement
  canvas.style.cssText = 'width:100%;height:100%;display:block'
  host.appendChild(canvas)
  const scene = new THREE.Scene()
  const camera = ortho ? new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 2) : new THREE.PerspectiveCamera(fov, 1, 0.1, 80)
  if (!ortho) camera.position.set(0, 0.3, distance)
  const pointer = { x: 0, y: 0, u: 0.5, v: 0.5, speed: 0 }
  const lean = { x: 0, y: 0 }
  const stage = { renderer, scene, camera, canvas, narrow, pointer, lean, size: { w: 1, h: 1 }, disposers: [] }
  const onPointer = (e) => {
    if (e.pointerType === 'touch') return
    const rect = canvas.getBoundingClientRect()
    const u = (e.clientX - rect.left) / rect.width
    const v = 1 - (e.clientY - rect.top) / rect.height
    pointer.speed = Math.min(1, pointer.speed + Math.hypot(u - pointer.u, v - pointer.v) * 6)
    pointer.u = u
    pointer.v = v
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1
    pointer.y = (e.clientY / window.innerHeight) * 2 - 1
  }
  window.addEventListener('pointermove', onPointer)
  const update = setup(stage)
  const resize = () => {
    const w = Math.max(1, host.clientWidth)
    const h = Math.max(1, host.clientHeight)
    stage.size = { w, h }
    renderer.setSize(w, h, false)
    if (!ortho) {
      camera.aspect = w / h
      // move the picture to the right on wide screens, so the text has the left side
      if (shift && !narrow) camera.setViewOffset(w, h, -w * shift, 0, w, h)
      camera.updateProjectionMatrix()
    }
  }
  resize()
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(host)
  let raf = 0
  let running = false
  let last = performance.now()
  let first = true
  const render = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    lean.x = damp(lean.x, pointer.x, 2, dt)
    lean.y = damp(lean.y, pointer.y, 2, dt)
    pointer.speed = damp(pointer.speed, 0, 1.5, dt)
    update(reduced ? 6 : now / 1000, dt)
    renderer.render(scene, camera)
    if (first) {
      first = false
      onFirstFrame()
    }
  }
  const frame = (now) => {
    if (!running) return
    raf = requestAnimationFrame(frame)
    render(now)
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
  let visibility = null
  if (reduced) render(performance.now())
  else {
    visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()))
    visibility.observe(host)
  }
  return () => {
    stop()
    visibility?.disconnect()
    resizeObserver.disconnect()
    window.removeEventListener('pointermove', onPointer)
    stage.disposers.forEach((d) => d())
    scene.traverse((o) => {
      o.geometry?.dispose()
      const materials = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
      materials.forEach((m) => {
        m.map?.dispose()
        m.dispose()
      })
    })
    renderer.dispose()
    canvas.remove()
  }
}

// a small source chip: a numbered badge and a file name
function chipTexture(n, label, color) {
  const canvas = document.createElement('canvas')
  canvas.width = 620
  canvas.height = 120
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.roundRect(4, 4, 612, 112, 56)
  ctx.fill()
  ctx.strokeStyle = color
  ctx.lineWidth = 5
  ctx.stroke()
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(62, 60, 34, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#ffffff'
  ctx.font = `700 38px ${SANS}`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(String(n), 62, 62)
  ctx.textAlign = 'left'
  ctx.fillStyle = '#1a2321'
  ctx.font = `600 38px ${SANS}`
  ctx.fillText(label, 116, 62)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

// a stream of glowing dots along a curve (start → control → end), each dot fading in and out
function makeStream(scene, count, color, size) {
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 4)
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 4))
  const points = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ size, map: glowTexture('rgba(255,255,255,1)', 'rgba(255,255,255,0)'), vertexColors: true, transparent: true, depthWrite: false }),
  )
  scene.add(points)
  const c = new THREE.Color(color)
  return (start, control, end, t, speed, alpha = 1) => {
    for (let k = 0; k < count; k++) {
      const p = (t * speed + k / count) % 1
      const a = (1 - p) * (1 - p)
      const b = 2 * (1 - p) * p
      const d = p * p
      positions[k * 3] = a * start.x + b * control.x + d * end.x
      positions[k * 3 + 1] = a * start.y + b * control.y + d * end.y
      positions[k * 3 + 2] = a * start.z + b * control.z + d * end.z
      colors[k * 4] = c.r
      colors[k * 4 + 1] = c.g
      colors[k * 4 + 2] = c.b
      colors[k * 4 + 3] = Math.sin(Math.PI * p) * alpha
    }
    geometry.attributes.position.needsUpdate = true
    geometry.attributes.color.needsUpdate = true
  }
}

// ── Scene "prism": documents flow in as white light and leave as three coloured beams, each ending in a source ──
function buildPrism(host, opts) {
  return makeStage(host, { ...opts, shift: 0.13 }, ({ scene, camera, narrow, lean }) => {
    scene.add(new THREE.HemisphereLight('#ffffff', '#d7e3dd', 1.6))
    const key = new THREE.DirectionalLight('#ffffff', 2)
    key.position.set(-3, 4, 6)
    scene.add(key)
    const group = new THREE.Group()
    group.scale.setScalar(narrow ? 0.62 : 1)
    group.position.y = narrow ? 0.1 : 0
    scene.add(group)

    // the prism: clear glass with mint edges, so it reads on a white page
    const prismGeometry = new THREE.CylinderGeometry(1.15, 1.15, 1.6, 3, 1)
    prismGeometry.rotateX(Math.PI / 2) // the triangle faces the camera
    const prism = new THREE.Mesh(
      prismGeometry,
      // frosted, slightly iridescent glass (true refraction needs something behind it, and the page is plain)
      new THREE.MeshPhysicalMaterial({ color: '#dff3ec', transparent: true, opacity: 0.42, roughness: 0.08, clearcoat: 1, iridescence: 0.8, iridescenceIOR: 1.6, side: THREE.DoubleSide, depthWrite: false }),
    )
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(prismGeometry), new THREE.LineBasicMaterial({ color: '#3fb9a3', transparent: true, opacity: 0.8 }))
    prism.add(edges)
    group.add(prism)
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture('rgba(127,216,200,0.5)', 'rgba(127,216,200,0)'), transparent: true, depthWrite: false }))
    halo.scale.set(4.2, 4.2, 1)
    halo.position.z = -0.8
    group.add(halo)

    // pages flowing in from the left
    const PAGES = 60
    const pages = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.2, 0.27), new THREE.MeshStandardMaterial({ map: pageTexture('text', 7), side: THREE.DoubleSide }), PAGES)
    group.add(pages)
    const lane = Array.from({ length: PAGES }, (_, i) => ({ y: Math.sin(i * 12.9) * 0.28, z: Math.cos(i * 7.3) * 0.25, spin: i * 0.7 }))
    const dummy = new THREE.Object3D()
    const white = makeStream(group, 30, '#ffffff', 0.09)

    // three beams out of the right face, each to a source chip
    const sources = [
      { color: '#e9a514', label: 'Handbook_2026.pdf · p.2', y: 1.35 },
      { color: '#3fb9a3', label: 'Leave_policy.md', y: 0 },
      { color: '#0f6b5c', label: 'HR_FAQ.docx · p.5', y: -1.35 },
    ].map((s, i) => {
      const chip = new THREE.Mesh(new THREE.PlaneGeometry(1.55, 0.3), new THREE.MeshBasicMaterial({ map: chipTexture(i + 1, s.label, s.color), transparent: true, toneMapped: false }))
      chip.position.set(2.35, s.y, 0.3)
      group.add(chip)
      return { ...s, chip, stream: makeStream(group, 34, s.color, 0.12) }
    })
    const a = new THREE.Vector3()
    const b = new THREE.Vector3()
    const c = new THREE.Vector3()

    return (t) => {
      group.rotation.set(lean.y * 0.12, lean.x * 0.35, 0)
      prism.rotation.y = Math.sin(t * 0.5) * 0.12 + lean.x * 0.2 // a slow sway
      prism.rotation.z = t * 0.15 // the triangle turns slowly
      prism.rotation.x = Math.sin(t * 0.4) * 0.25
      halo.material.opacity = 0.7 + Math.sin(t * 1.4) * 0.2
      // pages tumble in along the left lane and shrink into the glass
      for (let i = 0; i < PAGES; i++) {
        const p = (t * 0.12 + i / PAGES) % 1
        const l = lane[i]
        dummy.position.set(-3.4 + p * 2.7, l.y * (1 - p), l.z)
        dummy.rotation.set(t * 0.8 + l.spin, t * 0.6 + l.spin, 0)
        dummy.scale.setScalar(1 - Math.pow(p, 3))
        dummy.updateMatrix()
        pages.setMatrixAt(i, dummy.matrix)
      }
      pages.instanceMatrix.needsUpdate = true
      white(a.set(-3.4, 0, 0), b.set(-2, 0.15, 0.3), c.set(-0.6, 0, 0), t, 0.35, 0.8)
      sources.forEach((s, i) => {
        s.stream(a.set(0.6, 0, 0), b.set(1.2, s.y * 0.2, 0.4), c.set(1.55, s.y, 0.3), t, 0.4 + i * 0.03)
        s.chip.position.y = s.y + Math.sin(t * 1.2 + i) * 0.05
        s.chip.quaternion.copy(camera.quaternion)
      })
    }
  })
}

// ── Scene "ink": swirls of pine, mint and amber ink, stirred by the cursor (a full-screen shader) ──
const INK_SHADER = `
precision highp float;
uniform float uTime; uniform vec2 uRes; uniform vec2 uMouse; uniform float uStir; uniform vec3 uBg; uniform float uNarrow;
varying vec2 vUv;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.5; mat2 m = mat2(1.6, 1.2, -1.2, 1.6); for (int i = 0; i < 5; i++){ v += a * noise(p); p = m * p; a *= 0.5; } return v; }
void main(){
  float aspect = uRes.x / uRes.y;
  vec2 p = vUv * vec2(aspect, 1.0) * 2.4;
  vec2 m = uMouse * vec2(aspect, 1.0) * 2.4;
  vec2 d = p - m; float r = length(d);
  float swirl = uStir * exp(-r * r * 1.2) * 3.0;            // the cursor twists the ink around it
  p = m + mat2(cos(swirl), -sin(swirl), sin(swirl), cos(swirl)) * d;
  float t = uTime * 0.05;
  vec2 q = vec2(fbm(p + t), fbm(p + vec2(5.2, 1.3) - t));
  vec2 w = vec2(fbm(p + 3.0 * q + vec2(1.7, 9.2) + t * 1.3), fbm(p + 3.0 * q + vec2(8.3, 2.8) - t));
  float f = fbm(p + 3.0 * w);
  vec3 mint = vec3(0.55, 0.86, 0.79), pine = vec3(0.06, 0.42, 0.36), deep = vec3(0.05, 0.17, 0.15), amber = vec3(0.96, 0.72, 0.18);
  vec3 ink = mix(mint, pine, smoothstep(0.3, 0.7, f));
  ink = mix(ink, deep, smoothstep(0.75, 1.05, length(w)));
  ink = mix(ink, amber, smoothstep(0.6, 0.78, q.x) * 0.9);
  float density = smoothstep(0.38, 0.78, f + 0.22 * length(q));
  float mask = mix(smoothstep(0.3, 0.78, vUv.x), smoothstep(0.0, 0.45, 1.0 - vUv.y), uNarrow); // keep the text side clear
  gl_FragColor = vec4(mix(uBg, ink, density * mask), 1.0);
}`

function buildInk(host, opts) {
  const { themeRef } = opts
  return makeStage(host, { ...opts, ortho: true }, (stage) => {
    const { scene, narrow, pointer } = stage
    const uniforms = {
      uTime: { value: 0 },
      uRes: { value: new THREE.Vector2(1, 1) },
      uMouse: { value: new THREE.Vector2(0.7, 0.5) },
      uStir: { value: 0 },
      uBg: { value: new THREE.Color('#ffffff') },
      uNarrow: { value: narrow ? 1 : 0 },
    }
    const quad = new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2),
      new THREE.ShaderMaterial({ uniforms, fragmentShader: INK_SHADER, vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }', depthTest: false, depthWrite: false }),
    )
    quad.renderOrder = -1
    scene.add(quad)
    // the answer, floating in the ink
    const card = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: answerTexture(), transparent: true, toneMapped: false }))
    card.position.z = -0.5
    scene.add(card)
    const mouse = new THREE.Vector2(0.7, 0.5)
    return (t, dt) => {
      const { w, h } = stage.size // read every frame: it changes when the window is resized
      uniforms.uTime.value = t
      uniforms.uRes.value.set(w, h)
      uniforms.uBg.value.set(themeRef.current === 'dark' ? '#1c1c1c' : '#ffffff')
      mouse.x = damp(mouse.x, pointer.u, 4, dt)
      mouse.y = damp(mouse.y, pointer.v, 4, dt)
      uniforms.uMouse.value.copy(mouse)
      uniforms.uStir.value = damp(uniforms.uStir.value, pointer.speed, 3, dt)
      // the card keeps its own shape whatever the screen's shape (the camera spans −1 … 1 both ways)
      const cardW = narrow ? 1.6 : 0.62
      card.scale.set(cardW, cardW * (640 / 1200) * (w / h), 1)
      card.position.set(narrow ? 0 : 0.5, (narrow ? -0.55 : 0) + Math.sin(t * 1.1) * 0.015, -0.5)
    }
  })
}

// ── Scene "desk": a small clay desk under the same pull-cord lamp as the site; pulling it switches dark mode ──
function buildDesk(host, opts) {
  const { themeRef, toggleRef } = opts
  return makeStage(host, { ...opts, fov: 26, distance: 13, shift: 0.2, shadows: true }, (stage) => {
    const { scene, camera, canvas, narrow, lean } = stage
    camera.position.set(7.5, 6.2, 9.5)
    camera.lookAt(0, 0.9, 0)
    const hemi = new THREE.HemisphereLight('#ffffff', '#d9e2dc', 1.3)
    const sun = new THREE.DirectionalLight('#fff6e8', 1.6)
    sun.position.set(4, 9, 5)
    sun.castShadow = true
    sun.shadow.mapSize.set(1024, 1024)
    sun.shadow.radius = 6
    Object.assign(sun.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5 })
    scene.add(hemi, sun)

    const clay = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.92 })
    const box = (w, h, d, color, x, y, z, parent) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), clay(color))
      m.position.set(x, y, z)
      m.castShadow = m.receiveShadow = true
      parent.add(m)
      return m
    }
    const desk = new THREE.Group()
    desk.scale.setScalar(narrow ? 0.7 : 1)
    scene.add(desk)
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ opacity: 0.12 }))
    floor.rotation.x = -Math.PI / 2
    floor.position.y = -1.45
    floor.receiveShadow = true
    desk.add(floor)
    box(4.6, 0.2, 2.6, '#e9dfcc', 0, 0, 0, desk) // the desk top
    ;[[-2.1, -1.1], [2.1, -1.1], [-2.1, 1.1], [2.1, 1.1]].forEach(([x, z]) => box(0.16, 1.35, 0.16, '#cdbfa6', x, -0.77, z, desk))
    // the laptop with KnowledgeOS open
    const laptop = new THREE.Group()
    laptop.position.set(0.3, 0.13, 0.1)
    desk.add(laptop)
    box(1.9, 0.07, 1.3, '#1f3b36', 0, 0, 0, laptop)
    const screen = new THREE.Group()
    screen.position.set(0, 0.03, -0.63)
    screen.rotation.x = -0.22
    laptop.add(screen)
    box(1.9, 1.25, 0.06, '#1f3b36', 0, 0.62, 0, screen)
    const chat = makeChat() // the screen types the answer on a loop (see the update below)
    const display = new THREE.Mesh(new THREE.PlaneGeometry(1.76, 0.9), new THREE.MeshBasicMaterial({ map: chat.texture, toneMapped: false }))
    display.position.set(0, 0.62, 0.035)
    screen.add(display)
    // a stack of papers, a mug, a little plant
    for (let i = 0; i < 7; i++) {
      const sheet = box(0.85, 0.035, 1.1, i % 3 ? '#fbfaf5' : '#f3ead6', -1.55, 0.12 + i * 0.04, 0.15, desk)
      sheet.rotation.y = Math.sin(i * 2.3) * 0.12
    }
    const top = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 1.05), new THREE.MeshStandardMaterial({ map: pageTexture('highlight', 202) }))
    top.rotation.x = -Math.PI / 2
    top.position.set(-1.55, 0.41, 0.15)
    desk.add(top)
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.18, 0.38, 24), clay('#f5b82e'))
    mug.position.set(1.75, 0.29, -0.55)
    mug.castShadow = true
    desk.add(mug)
    const handle = new THREE.Mesh(new THREE.TorusGeometry(0.11, 0.035, 8, 20), clay('#f5b82e'))
    handle.position.set(1.97, 0.3, -0.55)
    desk.add(handle)
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.17, 0.32, 20), clay('#d9cdb6'))
    pot.position.set(1.85, 0.26, 0.75)
    pot.castShadow = true
    desk.add(pot)
    ;[[0, 0.55, 0, 0.26], [0.14, 0.75, 0.05, 0.2], [-0.12, 0.72, -0.06, 0.19]].forEach(([x, y, z, r]) => {
      const leaf = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), clay('#3f8f6f'))
      leaf.position.set(1.85 + x, y, 0.75 + z)
      leaf.castShadow = true
      desk.add(leaf)
    })

    // the lamp: a cord, a pine shade, a bulb and its light; click it to switch the whole site's theme
    const lamp = new THREE.Group()
    lamp.position.set(-0.6, 3.6, 0)
    desk.add(lamp)
    const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.6, 6), clay('#2b3a37'))
    cord.position.y = -0.8
    lamp.add(cord)
    const shade = new THREE.Mesh(new THREE.ConeGeometry(0.55, 0.5, 32, 1, true), new THREE.MeshStandardMaterial({ color: '#2b3a37', roughness: 0.6, side: THREE.DoubleSide }))
    shade.position.y = -1.75
    shade.castShadow = true
    lamp.add(shade)
    const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.16, 20, 16), new THREE.MeshStandardMaterial({ color: '#fff3c4', emissive: '#ffcf6b', emissiveIntensity: 0 }))
    bulb.position.y = -1.98
    lamp.add(bulb)
    const glow = new THREE.SpotLight('#ffd27a', 0, 9, 0.7, 0.6, 1.2)
    glow.position.y = -1.95
    glow.castShadow = true
    lamp.add(glow)
    glow.target.position.set(0, -6, 0)
    lamp.add(glow.target)

    // a small "pull me" note next to the shade; it fades for good after the first pull
    const hintCanvas = document.createElement('canvas')
    hintCanvas.width = 360
    hintCanvas.height = 96
    const hc = hintCanvas.getContext('2d')
    hc.fillStyle = '#1a2321'
    hc.beginPath()
    hc.roundRect(4, 4, 352, 88, 44)
    hc.fill()
    hc.fillStyle = '#fbfaf5'
    hc.font = `600 34px ${SANS}`
    hc.textBaseline = 'middle'
    hc.fillText('Pull me  ↓', 48, 50)
    hc.fillStyle = '#f5b82e'
    hc.beginPath()
    hc.arc(310, 48, 9, 0, Math.PI * 2)
    hc.fill()
    const hintTexture = new THREE.CanvasTexture(hintCanvas)
    hintTexture.colorSpace = THREE.SRGBColorSpace
    const hint = new THREE.Sprite(new THREE.SpriteMaterial({ map: hintTexture, transparent: true, depthTest: false }))
    hint.scale.set(0.9, 0.24, 1)
    hint.position.set(0.95, -1.5, 0)
    hint.renderOrder = 10
    lamp.add(hint)
    let pulled = false

    // clicking the lamp pulls it and switches the theme
    const raycaster = new THREE.Raycaster()
    const ndc = new THREE.Vector2()
    let pull = 0
    const onClick = (e) => {
      const rect = canvas.getBoundingClientRect()
      ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -(((e.clientY - rect.top) / rect.height) * 2 - 1))
      raycaster.setFromCamera(ndc, camera)
      if (raycaster.intersectObjects([cord, shade, bulb]).length) {
        pull = 1
        pulled = true
        toggleRef.current?.()
      }
    }
    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect()
      ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -(((e.clientY - rect.top) / rect.height) * 2 - 1))
      raycaster.setFromCamera(ndc, camera)
      canvas.style.cursor = raycaster.intersectObjects([cord, shade, bulb]).length ? 'pointer' : ''
    }
    // the canvas sits behind the text, so it listens on the window for clicks that land on it
    const onWindowClick = (e) => {
      if (e.target === canvas) onClick(e)
    }
    canvas.style.pointerEvents = 'auto'
    window.addEventListener('click', onWindowClick)
    canvas.addEventListener('pointermove', onMove)
    stage.disposers.push(() => {
      window.removeEventListener('click', onWindowClick)
      canvas.removeEventListener('pointermove', onMove)
    })

    let on = 0
    return (t, dt) => {
      const dark = themeRef.current === 'dark'
      on = damp(on, dark ? 1 : 0, 4, dt)
      hemi.intensity = 1.3 - on * 0.95
      sun.intensity = 1.6 - on * 1.35
      glow.intensity = on * 26
      bulb.material.emissiveIntensity = on * 2.5
      pull = damp(pull, 0, 3, dt)
      lamp.position.y = 3.6 - Math.sin(pull * Math.PI) * 0.25
      lamp.rotation.z = Math.sin(t * 0.9) * 0.03 + Math.sin(pull * 9) * pull * 0.12 // a gentle sway, a swing when pulled
      desk.rotation.set(lean.y * 0.06, lean.x * 0.18, 0)
      desk.position.y = narrow ? 0.4 : 0
      display.material.color.setScalar(1 - on * 0.1)
      // the laptop: waiting dots, then the answer typed out, then its source, every 9 seconds
      const c = t % 9
      chat.draw(c < 1.2 ? 0 : Math.floor(clamp((c - 1.2) / 2.2) * chat.totalChars), c > 3.6)
      hint.material.opacity = damp(hint.material.opacity, pulled ? 0 : 0.92, 3, dt)
      hint.position.y = -1.5 + Math.sin(t * 2) * 0.03
    }
  })
}

// ── The scene component: loads three.js, builds the chosen scene, fades it in ──
function HeroScene({ variant, sectionRef }) {
  const hostRef = useRef(null)
  const reduced = useReducedMotion()
  const { theme, toggle } = useTheme()
  const themeRef = useRef(theme)
  const toggleRef = useRef(toggle)
  useEffect(() => {
    themeRef.current = theme
    toggleRef.current = toggle
  })

  useEffect(() => {
    let gone = false
    let teardown = () => {}
    const host = hostRef.current
    Promise.all([loadThree(), document.fonts?.ready]).then(() => {
      if (gone) return
      const build = { a: buildVortex, c: buildLivingPage, prism: buildPrism, ink: buildInk }[variant] || buildDesk
      teardown = build(host, {
        section: sectionRef.current,
        themeRef,
        toggleRef,
        reduced,
        onFirstFrame: () => {
          host.style.opacity = '1'
        },
      })
    })
    return () => {
      gone = true
      teardown()
    }
  }, [variant, sectionRef, reduced])

  return <div ref={hostRef} aria-hidden="true" className="absolute inset-0 opacity-0 transition-opacity duration-1000" />
}

export default function Hero() {
  const sectionRef = useRef(null)
  const [webgl] = useState(supportsWebGL)
  const [variant] = useState(() => new URLSearchParams(window.location.search).get('hero') || 'desk') // desk (chosen), a, c, prism, ink
  const { isLoaded, isSignedIn } = useAuth()

  return (
    <section ref={sectionRef} className="relative isolate flex min-h-[100svh] flex-col overflow-hidden lg:flex-row lg:items-center">
      {/* the scene fills the screen behind the text; on a phone it gets its own box under the text */}
      {webgl && (
        <div className="absolute inset-0 max-lg:relative max-lg:inset-auto max-lg:order-last max-lg:h-[420px] max-lg:w-full">
          <HeroScene variant={variant} sectionRef={sectionRef} />
        </div>
      )}
      {/* a soft wash in the page colour behind the text, so the scene never competes with it */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 hidden w-[62%] bg-linear-to-r from-surface via-surface/85 to-transparent lg:block" />

      <div className="pointer-events-none relative z-10 mx-auto w-full max-w-[1400px] px-5 pb-6 pt-32 sm:px-10 lg:px-16 lg:pb-24 lg:pt-28">
        <div className="pointer-events-auto max-w-[54rem] max-lg:mx-auto max-lg:text-center">
          <p className="hero-in inline-flex items-center gap-2 rounded-full border border-stone-200 bg-surface/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] sm:text-xs sm:tracking-[0.14em] text-accent-ink backdrop-blur">
            <span className="size-1.5 rounded-full bg-highlight" aria-hidden="true" />
            Local-first RAG · answers with sources
          </p>
          <h1 className="hero-in mt-6 font-display text-5xl font-semibold leading-[1.04] tracking-tight text-ink sm:text-6xl xl:text-[3.8rem]" style={{ animationDelay: '80ms' }}>
            Ask your documents.
            <span className="block text-accent-ink">Get answers you can check.</span>
          </h1>
          <p className="hero-in mt-6 max-w-xl text-lg leading-relaxed text-stone-600 max-lg:mx-auto" style={{ animationDelay: '160ms' }}>
            Upload PDFs, Word, slides or spreadsheets. KnowledgeOS answers in plain language and points every claim to the exact
            passage it came from.
          </p>
          <div className="hero-in mt-9 flex flex-wrap items-center gap-3 max-lg:justify-center" style={{ animationDelay: '240ms' }}>
            <Link
              to={isLoaded && isSignedIn ? '/chat' : '/sign-up'}
              className="inline-flex h-12 items-center gap-2 rounded-full bg-ink px-6 text-sm font-semibold text-paper transition-transform focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 motion-safe:hover:-translate-y-0.5"
            >
              {isLoaded && isSignedIn ? 'Open app' : 'Get started'} <span aria-hidden="true">→</span>
            </Link>
            <a
              href="#demo"
              className="inline-flex h-12 items-center gap-2 rounded-full bg-surface/80 px-6 text-sm font-semibold text-ink ring-1 ring-ink/15 backdrop-blur transition-colors hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
            >
              <svg viewBox="0 0 24 24" className="size-4 text-accent-ink" fill="currentColor" aria-hidden="true">
                <path d="M8 5.5v13a1 1 0 001.5.86l10.5-6.5a1 1 0 000-1.72L9.5 4.64A1 1 0 008 5.5z" />
              </svg>
              Watch the demo
            </a>
          </div>
          <p className="hero-in mt-8 text-sm text-stone-600" style={{ animationDelay: '320ms' }}>
            <span className="font-semibold text-ink">93% correct</span> on our 45-question test ·{' '}
            <span className="font-semibold text-ink">runs on your own computer</span>
          </p>
        </div>
      </div>

      {/* a small scroll hint at the bottom */}
      <div aria-hidden="true" className="pointer-events-none absolute bottom-7 left-1/2 z-10 hidden -translate-x-1/2 flex-col items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-600 lg:flex">
        <span className="grid h-9 w-6 place-items-start justify-center rounded-full border-2 border-stone-300 pt-1.5">
          <span className="cta-bob block h-2 w-1 rounded-full bg-stone-500" />
        </span>
        Scroll
      </div>
    </section>
  )
}
