#!/usr/bin/env bash
# GitHub HTTPS 푸시 (PAT는 환경 변수로만 전달 — 채팅/저장소에 적지 마세요)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "GITHUB_TOKEN 환경 변수에 Fine-grained(Contents 쓰기) 또는 Classic(repo) PAT를 설정한 뒤 다시 실행하세요." >&2
  exit 1
fi
BASIC="$(printf '%s:%s' 'x-access-token' "$GITHUB_TOKEN" | base64 -w0)"
git -c "http.extraHeader=Authorization: Basic ${BASIC}" push -u origin main
echo "푸시 완료: https://github.com/junmankang83/SAMKWANG-AI"
