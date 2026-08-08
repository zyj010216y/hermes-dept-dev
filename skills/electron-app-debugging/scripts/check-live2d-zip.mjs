#!/usr/bin/env node
// Check a Live2D model zip's integrity WITHOUT trusting system unzip.
// Usage: node check-live2d-zip.mjs <path-to.zip>
//
// Why: system `unzip` reports "Illegal byte sequence" on zips with
// non-UTF8/Chinese filenames — a false alarm. JSZip + a lenient decode
// handles them fine. This script lists entries, locates model3.json,
// and verifies every FileReferences path actually exists in the zip
// (missing texture/physics paths are the #1 import-failure root cause).
//
// Based on the U-NO 伊拉利娅 diagnosis (2026-08-07): system unzip failed,
// JSZip parsed 34 entries, model3.json refs were all present -> issue was
// runtime-side, not the archive.

import JSZip from 'jszip'
import { readFile } from 'node:fs/promises'

// Lenient decode: try GBK for names that look like legacy codepage.
// (U-NO's decode-zip-filename.ts uses a similar heuristic.)
function decodeZipFileName(name) {
  try {
    const bytes = new TextEncoder().encode(name)
    return new TextDecoder('gbk').decode(bytes)
  }
  catch {
    return name
  }
}

const zipPath = process.argv[2]
if (!zipPath) {
  console.error('usage: node check-live2d-zip.mjs <path-to.zip>')
  process.exit(1)
}

const buf = await readFile(zipPath)
console.log(`zip size: ${(buf.length / 1024 / 1024).toFixed(2)} MB`)

const zip = await JSZip.loadAsync(buf, { decodeFileName: decodeZipFileName })
const names = Object.keys(zip.files)
console.log(`total entries: ${names.length}`)

const settingsPath = names.find(n => /\.model3?\.json$/i.test(n))
if (!settingsPath) {
  console.error('NO model3.json found — not a Live2D zip?')
  process.exit(1)
}
console.log(`settings: ${settingsPath}`)

const settings = JSON.parse(await zip.file(settingsPath).async('text'))
const fr = settings.FileReferences
const modelDir = settingsPath.split('/').slice(0, -1).join('/')
const refs = {
  Moc: fr.Moc,
  Textures: fr.Textures,
  Physics: fr.Physics,
  Pose: fr.Pose,
}
console.log('FileReferences:')
let allOk = true
for (const [kind, paths] of Object.entries(refs)) {
  if (paths === undefined || paths === null) { console.log(`  ${kind}: (none)`); continue }
  const list = Array.isArray(paths) ? paths : [paths]
  for (const p of list) {
    const full = `${modelDir}/${p}`
    const ok = names.includes(full)
    if (!ok) allOk = false
    console.log(`  ${ok ? 'OK ' : 'MISSING '} ${kind}: ${p}`)
  }
}

// Format clues
if (names.some(n => n.toLowerCase().endsWith('.vtube.json')))
  console.log('format: VTube Studio (vtube.json present)')
const bigTex = names.filter(n => /\\.\\d{3,4}\\//.test(n))
if (bigTex.length)
  console.log(`large texture atlas dirs: ${[...new Set(bigTex.map(n => n.match(/\\.\\d{3,4}\\//)?.[0]))].join(', ')}`)

// moc3 version header: 4-byte magic 'MOC3' + uint32 version at offset 4.
// Use this when the model renders wrong/not-at-all and you suspect the model
// was authored in a Cubism version newer than the runtime Core supports.
// MocVersion enums (Live2DCubismCore): 1=3.0, 2=3.3, 3=4.0, 4=4.2, 5=5.0, 6=5.3
const MOC_VERSION_NAMES = { 1: 'Cubism 3.0', 2: 'Cubism 3.3', 3: 'Cubism 4.0', 4: 'Cubism 4.2', 5: 'Cubism 5.0', 6: 'Cubism 5.3' }
const mocPath = names.find(n => n.endsWith('.moc3'))
if (mocPath) {
  const mocBuf = await zip.file(mocPath).async('nodebuffer')
  if (mocBuf.length >= 8) {
    const magic = mocBuf.slice(0, 4).toString('ascii')
    const ver = mocBuf.readUInt32LE(4)
    console.log(`\\nmoc3: ${mocPath}`)
    console.log(`  magic=${magic} version=${ver} ${MOC_VERSION_NAMES[ver] || '(unknown/≥Cubism6?)'}`)
    console.log('  NOTE: untitled-pixi-live2d-engine (Framework 5-r.4) + Core 5.x supports ≤ 5.3;')
    console.log('        a Cubism 6-authored moc3 (ver > 6) needs Core 6.x — check engine/Core compat first')
  }
}

console.log(allOk ? '\\nRESULT: all FileReferences resolve — archive OK, debug runtime side'
                  : '\\nRESULT: MISSING REFERENCES — fix zip before anything else')
