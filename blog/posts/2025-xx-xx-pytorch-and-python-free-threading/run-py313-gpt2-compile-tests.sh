#!/bin/bash

# Ensure our environment name is `py313`.
if [ "$CONDA_DEFAULT_ENV" != "py313" ]; then
  echo "Error: Conda environment is not 'py313'."
  exit 1
fi

# Ensure PARALLELOPEDIA_ROOT is set.
if [ -z "$PARALLELOPEDIA_ROOT" ]; then
  echo "Error: PARALLELOPEDIA_ROOT is not set."
  exit 1
fi

SEED=42
DEVICE="cuda:3"
ROUNDS=20

# Verify $PARALLELOPEDIA_ROOT/src/parallelopedia/gpt2.py has the following
# two lines:
#   # @torch.compile
#   def generate_slim(

TARGET="$PARALLELOPEDIA_ROOT/src/parallelopedia/gpt2.py"

# Verify target file exists.
if [ ! -f "$TARGET" ]; then
  echo "Error: File '$TARGET' not found."
  exit 1
fi

if ! awk -f <(cat <<'EOF'
    BEGIN { found=1 }  # Assume failure unless proven otherwise

    /^    # @torch\.compile/ {
        getline
        if ($0 ~ /^    def generate_slim\(/) {
            found=0  # Mark as found (success)
            exit 0   # Exit immediately on success
        }
    }

    END { exit found }  # If no match is found, exit 1
EOF
) "$TARGET"; then
  echo "Error: expected '# @torch.compile' followed by 'def generate_slim(' in \"$TARGET\""
  exit 1
fi

OPTIONS=(
  "--torch-compile"
  "--torch-compile --torch-compile-fullgraph"
  "--torch-compile --torch-compile-reduce-overhead"
  "--torch-compile --torch-compile-reduce-overhead --torch-compile-fullgraph"
  "--torch-compile --torch-compile-reduce-overhead --torch-compile-fullgraph"
  "--torch-compile --torch-compile-max-autotune"
  "--torch-compile --torch-compile-max-autotune --torch-compile-fullgraph"
)

echo "GPT.generate() variants"
time python -m parallelopedia.gpt2    \
    --seed=$SEED                      \
    --rounds=$ROUNDS                  \
    --device=$DEVICE

for opt in "${OPTIONS[@]}"; do
    # Split opt into separate arguments.
    eval set -- $opt
    time python -m parallelopedia.gpt2 \
        --seed=$SEED                   \
        --rounds=$ROUNDS               \
        --device=$DEVICE               \
        "$@"
done

