// CODEBASE-FEATURE (Stage 11): turn a folder the user picked into ONE zip file in the browser, so it can go through
// the normal upload (the backend's zip loader does the reading). The filter looks at PATHS only: a 500 MB node_modules
// is rejected without opening a single file in it.
import { zipSync } from 'fflate'
import { MAX_FILES, MAX_FILE_BYTES_BY_TIER, MAX_UNPACKED_BYTES, classifyPath, normalizePath } from './codePolicy'
import { MAX_FILE_BYTES } from './files'

// why files were left out, in words for the chip
const REASON_TEXT = {
  ignored_dir: 'in build or dependency folders',
  ignored_file: 'lock, minified or map files',
  secret_file: 'secret-looking files',
  unsupported_type: 'other types (images, binaries...)',
  unsafe_path: 'with unusable names',
  too_large: 'over the size limit',
  empty: 'empty',
  too_many_files: `past the ${MAX_FILES}-file limit`,
  zip_size_limit: 'past the total size limit',
}

const pathOf = (file) => file.webkitRelativePath || file.name
const megabytes = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

export function describeSkipped(skipped) {
  const total = Object.values(skipped).reduce((sum, n) => sum + n, 0)
  if (total === 0) return 'none skipped'
  const reasons = Object.entries(skipped)
    .sort((a, b) => b[1] - a[1])
    .map(([reason, count]) => `${count} ${REASON_TEXT[reason] ?? reason}`)
  return `skipped ${total}: ${reasons.join(', ')}`
}

// Which files to pack: [{ file, path }] in path order, and a count of the rest by reason.
export function planFolder(files) {
  const skipped = {}
  const skip = (reason) => {
    skipped[reason] = (skipped[reason] ?? 0) + 1
  }
  const keep = []
  let total = 0
  const sorted = [...files].sort((a, b) => pathOf(a).toLowerCase().localeCompare(pathOf(b).toLowerCase()))
  for (const file of sorted) {
    const verdict = classifyPath(pathOf(file))
    if (!verdict.accepted) skip(verdict.reason)
    else if (file.size === 0) skip('empty')
    else if (file.size > MAX_FILE_BYTES_BY_TIER[verdict.tier]) skip('too_large')
    else if (keep.length >= MAX_FILES) skip('too_many_files')
    else if (total + file.size > MAX_UNPACKED_BYTES) skip('zip_size_limit')
    else {
      total += file.size
      keep.push({ file, path: normalizePath(pathOf(file)) })
    }
  }
  return { keep, skipped }
}

// Reads the kept files and zips them. Resolves { file, summary, packedFiles, skipped }; throws an Error with a message
// the user can act on when there is nothing to pack or the zip would be over the upload limit.
export async function packFolder(fileList) {
  const files = Array.from(fileList)
  const { keep, skipped } = planFolder(files)
  if (keep.length === 0) {
    throw new Error(`Nothing in this folder can be read (${describeSkipped(skipped)}). Choose the project's source folder.`)
  }

  const entries = {}
  for (const [index, { file, path }] of keep.entries()) {
    entries[path] = new Uint8Array(await file.arrayBuffer())
    if (index % 50 === 49) await new Promise((resolve) => setTimeout(resolve, 0)) // let the page breathe on big folders
  }
  const zipped = zipSync(entries, { level: 6 })
  if (zipped.length > MAX_FILE_BYTES) {
    throw new Error(`The packed project is ${megabytes(zipped.length)}, over the 20 MB upload limit. Choose a smaller folder.`)
  }

  const root = pathOf(files[0]).includes('/') ? pathOf(files[0]).split('/')[0] : 'project'
  const zip = new File([zipped], `${root}.zip`, { type: 'application/zip' })
  const summary = `Packed ${keep.length} file${keep.length === 1 ? '' : 's'} (${megabytes(zipped.length)}); ${describeSkipped(skipped)}.`
  return { file: zip, summary, packedFiles: keep.length, skipped }
}
