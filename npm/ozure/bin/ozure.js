#!/usr/bin/env node
// ozure launcher: prefer the prebuilt binary that matches this platform,
// otherwise fall back to a local Python install of the same version.
'use strict';

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const PLATFORM = `${process.platform}-${process.arch}`;
const BINARY = process.platform === 'win32' ? 'ozure.exe' : 'ozure';
const PLATFORM_PACKAGE = process.env.OZURE_NPM_PACKAGE ||
  `@microck/ozure-${PLATFORM}`;
const args = process.argv.slice(2);

function bundledBinary() {
  try {
    const manifest = require.resolve(`${PLATFORM_PACKAGE}/package.json`);
    const candidate = path.join(path.dirname(manifest), 'bin', BINARY);
    return fs.existsSync(candidate) ? candidate : null;
  } catch {
    return null;
  }
}

function pythonModule() {
  for (const candidate of ['python3', 'python', 'py']) {
    const probe = spawnSync(candidate, ['-m', 'ozure', '--version'], {
      stdio: 'ignore',
      shell: false,
    });
    if (probe.status === 0) return candidate;
  }
  return null;
}

function run(command, commandArgs) {
  const result = spawnSync(command, commandArgs, { stdio: 'inherit', shell: false });
  if (result.error) {
    console.error(`ozure: ${result.error.message}`);
    process.exit(1);
  }
  if (result.signal) {
    process.kill(process.pid, result.signal);
    return;
  }
  process.exit(result.status === null ? 1 : result.status);
}

const binary = bundledBinary();
if (binary) {
  run(binary, args);
}

const python = pythonModule();
if (python) {
  run(python, ['-m', 'ozure', ...args]);
}

console.error(
  [
    `ozure: no binary for ${PLATFORM} and no local Python install.`,
    '',
    '  npm:      npm install -g @microck/ozure   (binaries ship per platform)',
    '  python:   pipx install "ozure[usb]"',
    '',
    'On macOS/Linux the prebuilt binary comes from the GitHub Releases page:',
    '  https://github.com/AlPeFe/ozure/releases',
  ].join('\n'),
);
process.exit(1);
