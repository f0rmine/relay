#!/usr/bin/env bash
set -euo pipefail

mkdir -p docs/figures

render() {
    local input="$1"
    local output="$2"

    echo "Rendering ${input} -> ${output}"
    npx -y @mermaid-js/mermaid-cli -p docs/mermaid-puppeteer-config.json -i "${input}" -o "${output}" -b white -w 1800
}

render docs/diagrams/figure-2-1-architecture.mmd docs/figures/figure-2-1-architecture.png
render docs/diagrams/figure-2-2-auth-flow.mmd docs/figures/figure-2-2-auth-flow.png
render docs/diagrams/figure-2-3-message-flow.mmd docs/figures/figure-2-3-message-flow.png
render docs/diagrams/figure-2-4-database-er.mmd docs/figures/figure-2-4-database-er.png

echo "Mermaid rendering complete."
