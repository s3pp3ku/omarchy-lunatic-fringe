#!/bin/bash
set -euo pipefail
package_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec /usr/bin/python -B "$package_root/scripts/install.py" "$@"
