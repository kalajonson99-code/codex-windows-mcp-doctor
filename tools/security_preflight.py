"""Conservative offline preflight for publishable files and release archives.

Never print matched text, credentials, or absolute input paths. This is a
heuristic guardrail, not a proof that an arbitrary secret cannot be present.
"""
from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_ENTRY_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_ITEMS = 1000

# Keep the extension allowlist deliberately narrow; a publishable code archive
# should never quietly acquire a database, credential store or binary payload.
TEXT_SUFFIXES = {'.py', '.md', '.toml', '.txt', '.yml', '.yaml', '.json',
                 '.csv', '.cfg', '.ini', '.rst', '.gitignore', '.in'}
SPECIAL_NAMES = {'LICENSE', 'MANIFEST.in', '.gitignore', 'PKG-INFO',
                 'METADATA', 'WHEEL', 'RECORD', 'entry_points.txt',
                 'top_level.txt', 'SOURCES.txt'}
SOURCE_FILES = {'CHANGELOG.md', 'CONTRIBUTING.md', 'LICENSE', 'MANIFEST.in',
                'README.md', 'README.zh-CN.md', 'SECURITY.md',
                'pyproject.toml', '.gitignore'}
SOURCE_DIRS = ('src/codex_mcp_doctor', 'tests', 'docs', 'tools', '.github/workflows')
DENIED_NAMES = re.compile(
    r'(?i)(?:^\.env(?:\..*)?$|^config\.toml$|^id_(?:rsa|dsa|ed25519|ecdsa)$|'
    r'\.(?:pem|p12|pfx|p8|key|sqlite3?|db|kdbx|jks|keystore|bak|log|pyc)$|'
    r'^\.git$|^__pycache__$)'
)
SECRET_PATTERNS = (
    re.compile(rb'-----BEGIN (?:[A-Z ]* )?PRIVATE KEY-----'),
    re.compile(rb'\b(?:sk-(?:proj-|svc-|admin-)?)[A-Za-z0-9_-]{24,}'),
    re.compile(rb'\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{30,}'),
    re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{30,}'),
    re.compile(rb'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}'),
    re.compile(rb'\bAIza[0-9A-Za-z_-]{35}\b'),
    re.compile(rb'''(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|bearer_token)\s*[:=]\s*['"]([^\s'"\n]{32,})['"]'''),
)


def _valid_name(name: str) -> bool:
    if '\\' in name or '\x00' in name or not name or name.startswith('/'):
        return False
    normalized = PurePosixPath(name)
    if '..' in normalized.parts or any(DENIED_NAMES.search(part) for part in normalized.parts):
        return False
    if re.match(r'^[A-Za-z]:', name):
        return False
    leaf = normalized.name
    return leaf in SPECIAL_NAMES or PurePosixPath(leaf).suffix.lower() in TEXT_SUFFIXES


def _content_issues(payload: bytes) -> list[str]:
    if len(payload) > MAX_ENTRY_BYTES:
        return ['OVERSIZED_ENTRY']
    if b'\x00' in payload:
        return ['BINARY_CONTENT']
    return ['SUSPECT_CREDENTIAL'] if any(p.search(payload) for p in SECRET_PATTERNS) else []


def source_issues(directory: Path) -> list[str]:
    """Inspect exactly the material eligible for the project's source release."""
    issues = []
    names = [Path(n) for n in SOURCE_FILES]
    for dirname in SOURCE_DIRS:
        subtree = directory / dirname
        if subtree.is_dir():
            names.extend(path.relative_to(directory) for path in subtree.rglob('*')
                         if path.is_file() and not any(part in {'__pycache__', '.pytest_cache',
                         '.git', 'build', 'dist'} for part in path.relative_to(directory).parts))
    for path in sorted(set(names)):
        full = directory / path
        if not full.is_file():
            issues.append('MISSING_PUBLISHABLE_FILE')
            continue
        if not _valid_name(path.as_posix()):
            issues.append('DISALLOWED_SOURCE_NAME')
            continue
        if full.is_symlink():
            issues.append('SOURCE_SYMLINK_NOT_ALLOWED')
            continue
        try:
            if full.stat().st_size > MAX_ENTRY_BYTES:
                issues.append('OVERSIZED_ENTRY')
            else:
                issues.extend(_content_issues(full.read_bytes()))
        except OSError:
            issues.append('SOURCE_UNREADABLE')
    return issues


def archive_issues(archive: Path) -> list[str]:
    """Read archives in place; never extract or follow an archive's paths."""
    issues = []
    total = 0
    count = 0
    try:
        if archive.suffix in {'.zip', '.whl'}:
            with zipfile.ZipFile(archive) as fp:
                for info in fp.infolist():
                    if info.is_dir():
                        continue
                    count += 1
                    if count > MAX_ARCHIVE_ITEMS:
                        issues.append('ARCHIVE_RESOURCE_LIMIT')
                        break
                    if not _valid_name(info.filename):
                        issues.append('DISALLOWED_ARCHIVE_NAME')
                        continue
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        issues.append('ARCHIVE_SYMLINK_NOT_ALLOWED')
                        continue
                    total += info.file_size
                    if info.file_size > MAX_ENTRY_BYTES or total > MAX_ARCHIVE_BYTES:
                        issues.append('ARCHIVE_RESOURCE_LIMIT')
                        break
                    issues.extend(_content_issues(fp.read(info)))
                    if count > MAX_ARCHIVE_ITEMS:
                        issues.append('ARCHIVE_RESOURCE_LIMIT')
                        break
        elif archive.name.endswith('.tar.gz'):
            with tarfile.open(archive, mode='r:gz') as fp:
                for member in fp:
                    if member.isdir():
                        continue
                    count += 1
                    if count > MAX_ARCHIVE_ITEMS:
                        issues.append('ARCHIVE_RESOURCE_LIMIT')
                        break
                    if not member.isfile() or not _valid_name(member.name):
                        issues.append('DISALLOWED_ARCHIVE_ENTRY')
                        continue
                    total += member.size
                    if member.size > MAX_ENTRY_BYTES or total > MAX_ARCHIVE_BYTES or count > MAX_ARCHIVE_ITEMS:
                        issues.append('ARCHIVE_RESOURCE_LIMIT')
                        break
                    stream = fp.extractfile(member)
                    if stream is None:
                        issues.append('UNREADABLE_ARCHIVE_ENTRY')
                        continue
                    issues.extend(_content_issues(stream.read(MAX_ENTRY_BYTES + 1)))
        else:
            return ['UNSUPPORTED_ARCHIVE']
    except (OSError, ValueError, EOFError, zipfile.BadZipFile, tarfile.TarError):
        issues.append('ARCHIVE_UNREADABLE')
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline credential and packaging preflight; no secret values printed.')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, action='append', default=[])
    args = parser.parse_args()
    findings = source_issues(args.source)
    for artifact in args.artifact:
        findings.extend(archive_issues(artifact))
    if findings:
        print(f'SECURITY PREFLIGHT FAILED: {len(findings)} issue(s)')
        for code in sorted(set(findings)):
            print(f'  {code}: {findings.count(code)}')
        return 1
    print(f'SECURITY PREFLIGHT PASSED: source and {len(args.artifact)} archive(s) scanned (heuristic checks only)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
