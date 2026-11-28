// CODEBASE-FEATURE (Stage 11): a copy of backend/app/ingestion/codebase/policy.py, used to decide in the browser which
// files of a folder are worth packing into a zip. The SERVER checks everything again (this is a convenience that keeps
// node_modules and images off the network, not a security boundary). A test runs both copies against the same list of
// paths and answers (backend/tests/policy_cases.json), so they cannot drift apart unnoticed.
import { CODE_EXTENSIONS } from './files'

const TIER1_CODE = new Set(CODE_EXTENSIONS)
const TIER2_TEXT = new Set([
  '.html', '.css', '.scss', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.sql', '.sh', '.txt', '.md', '.rst',
])
const TIER2_TEXT_NAMES = new Set(['dockerfile', 'makefile', 'requirements.txt', '.gitignore', '.env.example', '.env.sample', '.env.template'])
const TIER3_NOTEBOOK = new Set(['.ipynb'])
const TIER4_DATA = new Set(['.csv', '.tsv'])

const IGNORED_DIRS = new Set([
  'node_modules', '.git', 'venv', '.venv', 'env', 'dist', 'build', 'target', 'out', '__pycache__', '.idea', '.vscode', 'vendor',
  '.next', '.nuxt', 'coverage', '.pytest_cache', '.mypy_cache', '.gradle', '.tox', 'site-packages', '__macosx',
])
const IGNORED_FILE_NAMES = new Set([
  'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'pipfile.lock', 'composer.lock', 'cargo.lock', '.ds_store',
])

// shell-style patterns ("*" = anything) turned into regular expressions
const glob = (pattern) => new RegExp(`^${pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.')}$`)
const IGNORED_FILE_PATTERNS = ['*.min.js', '*.min.css', '*.map'].map(glob)
const SECRET_FILE_PATTERNS = ['.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa*', 'id_ed25519*', 'id_ecdsa*', 'id_dsa*', 'credentials*'].map(glob)

export const MAX_FILE_BYTES_BY_TIER = { code: 1_000_000, text: 200_000, notebook: 5_000_000, data: 5_000_000 }
export const MAX_FILES = 500
export const MAX_UNPACKED_BYTES = 50 * 1024 * 1024
const MAX_PATH_LENGTH = 300

const toSlashes = (name) => name.replaceAll('\\', '/')

export function isSafeMemberName(name) {
  if (!name || !name.trim() || name.length > MAX_PATH_LENGTH) return false
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f]/.test(name)) return false
  const path = toSlashes(name)
  if (path.startsWith('/') || /^[A-Za-z]:/.test(path)) return false
  return !path.split('/').includes('..')
}

export function normalizePath(name) {
  return toSlashes(name)
    .split('/')
    .filter((part) => part !== '' && part !== '.')
    .join('/')
}

// Python's PurePosixPath(...).suffix: a leading dot is not an extension (".env" has none)
function suffixOf(filename) {
  const dot = filename.lastIndexOf('.')
  return dot <= 0 || dot === filename.length - 1 ? '' : filename.slice(dot)
}

// { accepted, tier, reason }: the same answer as policy.classify() on the server
export function classifyPath(path) {
  if (!isSafeMemberName(path)) return { accepted: false, tier: null, reason: 'unsafe_path' }
  const parts = normalizePath(path).toLowerCase().split('/')
  const filename = parts[parts.length - 1]
  if (parts.slice(0, -1).some((part) => IGNORED_DIRS.has(part))) return { accepted: false, tier: null, reason: 'ignored_dir' }
  if (IGNORED_FILE_NAMES.has(filename) || IGNORED_FILE_PATTERNS.some((re) => re.test(filename))) {
    return { accepted: false, tier: null, reason: 'ignored_file' }
  }
  if (!TIER2_TEXT_NAMES.has(filename) && SECRET_FILE_PATTERNS.some((re) => re.test(filename))) {
    return { accepted: false, tier: null, reason: 'secret_file' }
  }
  const suffix = suffixOf(filename)
  if (TIER1_CODE.has(suffix)) return { accepted: true, tier: 'code', reason: null }
  if (TIER3_NOTEBOOK.has(suffix)) return { accepted: true, tier: 'notebook', reason: null }
  if (TIER4_DATA.has(suffix)) return { accepted: true, tier: 'data', reason: null }
  if (TIER2_TEXT.has(suffix) || TIER2_TEXT_NAMES.has(filename)) return { accepted: true, tier: 'text', reason: null }
  return { accepted: false, tier: null, reason: 'unsupported_type' }
}
