#!/usr/bin/env sh
# Smoke: login → upload TXT → poll status until ready → fetch summary/FAQs
set -eu
BASE="${BASE_URL:-http://localhost:8000}"
COOKIE_JAR="$(mktemp)"
SAMPLE="$(mktemp)"
trap 'rm -f "$COOKIE_JAR" "$SAMPLE"' EXIT

cat > "$SAMPLE" <<'EOF'
DocChat Smoke Test Policy

Coverage Period: The policy covers twelve months from the inception date.

Claims: Submit claims within 30 days of the incident with supporting documents.
EOF

curl -sS -c "$COOKIE_JAR" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@docchat.com","password":"password"}' | tee /tmp/docchat_login.json

CSRF=$(awk '$6=="csrf_token"{print $7}' "$COOKIE_JAR")

UPLOAD=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST "$BASE/documents/upload" \
  -H "X-CSRF-Token: $CSRF" \
  -F "file=@${SAMPLE};filename=smoke_policy.txt")
echo "$UPLOAD"
DOC_ID=$(printf '%s' "$UPLOAD" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "Document id: $DOC_ID"
for i in $(seq 1 60); do
  STATUS=$(curl -sS -b "$COOKIE_JAR" "$BASE/documents/$DOC_ID/status")
  echo "$STATUS"
  echo "$STATUS" | grep -q '"status":"ready"' && break
  echo "$STATUS" | grep -q '"status":"failed"' && exit 1
  sleep 5
done

curl -sS -b "$COOKIE_JAR" "$BASE/documents/$DOC_ID/summary"
echo
curl -sS -b "$COOKIE_JAR" "$BASE/documents/$DOC_ID/faqs"
echo
