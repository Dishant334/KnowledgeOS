// Stage 11: packing a chosen folder into one zip in the browser.
import { unzipSync } from 'fflate'
import { describe, expect, it, vi } from 'vitest'
import { MAX_FILES } from './codePolicy'
import { describeSkipped, packFolder, planFolder } from './zipFolder'

// A File as the folder picker gives it: it knows its path inside the chosen folder.
function entry(path, content = 'x = 1\n') {
  const bytes = typeof content === 'string' ? new TextEncoder().encode(content) : content
  const file = new File([bytes], path.split('/').pop())
  Object.defineProperty(file, 'webkitRelativePath', { value: path })
  return file
}
const unzip = async (zipFile) => unzipSync(new Uint8Array(await zipFile.arrayBuffer()))

describe('planFolder', () => {
  it('keeps source, text and data, and counts the rest by reason', () => {
    const { keep, skipped } = planFolder([
      entry('proj/app/main.py'), entry('proj/README.md', '# hi'), entry('proj/data.csv', 'a,b\n1,2\n'),
      entry('proj/.env', 'KEY=1'), entry('proj/node_modules/a/b.js'), entry('proj/node_modules/c.js'),
      entry('proj/logo.png', 'png'), entry('proj/package-lock.json', '{}'), entry('proj/empty.py', ''),
    ])
    expect(keep.map((k) => k.path)).toEqual(['proj/app/main.py', 'proj/data.csv', 'proj/README.md'])
    expect(skipped).toEqual({ secret_file: 1, ignored_dir: 2, unsupported_type: 1, ignored_file: 1, empty: 1 })
  })

  it('skips a file over its tier size cap and respects the file-count cap', () => {
    const big = entry('big.py', new Uint8Array(1_000_001))
    expect(planFolder([big]).skipped).toEqual({ too_large: 1 })
    const many = Array.from({ length: MAX_FILES + 20 }, (_, i) => entry(`f${String(i).padStart(4, '0')}.py`))
    const { keep, skipped } = planFolder(many)
    expect(keep).toHaveLength(MAX_FILES)
    expect(skipped).toEqual({ too_many_files: 20 })
  })

  it('stops at the total size cap', () => {
    const files = Array.from({ length: 60 }, (_, i) => entry(`d${String(i).padStart(2, '0')}.ipynb`, new Uint8Array(1_000_000)))
    const { keep, skipped } = planFolder(files)
    expect(keep.length).toBeLessThan(60)
    expect(keep.length + skipped.zip_size_limit).toBe(60)
  })

  it('never opens a file it skips (a huge node_modules costs nothing)', () => {
    const skippedFile = entry('proj/node_modules/x.js')
    const spy = vi.spyOn(skippedFile, 'arrayBuffer')
    planFolder([skippedFile, entry('proj/a.py')])
    expect(spy).not.toHaveBeenCalled()
  })
})

describe('packFolder', () => {
  it('zips the kept files with their paths and names the zip after the folder', async () => {
    const { file, summary, packedFiles, skipped } = await packFolder([
      entry('myproj/app/limiter.py', 'class TokenBucket:\n    pass\n'), entry('myproj/README.md', '# Title\n'),
      entry('myproj/.env', 'SECRET=1'), entry('myproj/node_modules/x/y.js'),
    ])
    expect(file.name).toBe('myproj.zip')
    expect(file.type).toBe('application/zip')
    expect(packedFiles).toBe(2)
    expect(skipped).toEqual({ secret_file: 1, ignored_dir: 1 })
    const contents = await unzip(file)
    expect(Object.keys(contents).sort()).toEqual(['myproj/README.md', 'myproj/app/limiter.py'])
    expect(new TextDecoder().decode(contents['myproj/app/limiter.py'])).toBe('class TokenBucket:\n    pass\n')
    expect(Object.keys(contents).join()).not.toMatch(/\.env|node_modules/)
    expect(summary).toMatch(/^Packed 2 files \(/)
    expect(summary).toMatch(/skipped 2: /)
    expect(summary).toContain('1 in build or dependency folders')
    expect(summary).toContain('1 secret-looking files')
  })

  it('says so when nothing in the folder can be read', async () => {
    await expect(packFolder([entry('p/logo.png', 'x'), entry('p/node_modules/a.js')])).rejects.toThrow(/Nothing in this folder can be read/)
  })

  it('refuses a pack that would be over the 20 MB upload limit', async () => {
    // incompressible bytes: the zip stays about as big as the files
    const noise = (seed) => {
      let x = seed * 2654435761 + 1 // xorshift32: bytes that do not compress
      return Uint8Array.from({ length: 900_000 }, () => {
        x ^= x << 13
        x ^= x >>> 17
        x ^= x << 5
        return x & 255
      })
    }
    const files = Array.from({ length: 26 }, (_, i) => entry(`big/f${i}.py`, noise(i)))
    await expect(packFolder(files)).rejects.toThrow(/over the 20 MB upload limit/)
  })

  it('uses a plain name for files picked without a folder path', async () => {
    const file = new File(['x = 1\n'], 'a.py')
    expect((await packFolder([file])).file.name).toBe('project.zip')
  })
})

describe('describeSkipped', () => {
  it('lists the biggest reason first, and says when nothing was skipped', () => {
    expect(describeSkipped({})).toBe('none skipped')
    expect(describeSkipped({ unsupported_type: 3, ignored_dir: 40 })).toBe(
      'skipped 43: 40 in build or dependency folders, 3 other types (images, binaries...)',
    )
  })
})
