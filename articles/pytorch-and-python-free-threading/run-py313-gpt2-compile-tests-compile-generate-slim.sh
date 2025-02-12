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

# Now patch the file to remove the comment preceding the @torch.compile
# decorator in our gpt2.py file.
awk -f <(cat <<'EOF'
    BEGIN { found=0 }

    # If we find "# @torch.compile" and haven't found one yet
    /^    # @torch\.compile$/ && found==0 {
        # Read next line without printing current line yet
        getline next_line
        if (next_line ~ /^    def generate_slim\(/) {
            found=1
            print "    @torch.compile"
        } else {
            print  # Keep it unchanged
        }
        print next_line  # Print the next line as-is
        next  # Skip further processing of this line
    }

    { print }  # Print all other lines normally
EOF
) "$TARGET" > "$TARGET.tmp" && mv "$TARGET.tmp" "$TARGET"

# Verify the patch was successful.
if ! awk -f <(cat <<'EOF'
    BEGIN { found=1 }  # Assume failure unless proven otherwise

    /^    @torch\.compile/ {
        getline
        if ($0 ~ /^    def generate_slim\(/) {
            found=0  # Mark as found (success)
            exit 0   # Exit immediately on success
        }
    }

    END { exit found }  # If no match is found, exit 1
EOF
) "$TARGET"; then
  echo "Error: expected '@torch.compile' followed by 'def generate_slim(' in \"$TARGET\""
  exit 1
fi

NOTE="Explicit @torch.compile decorator on GPT.generate_slim"

OPTIONS=(
  "--torch-compile"
  "--torch-compile --torch-compile-fullgraph"
  "--torch-compile --torch-compile-reduce-overhead"
  "--torch-compile --torch-compile-reduce-overhead --torch-compile-full-graph"
  "--torch-compile --torch-compile-reduce-overhead --torch-compile-fullgraph"
  "--torch-compile --torch-compile-max-autotune"
  "--torch-compile --torch-compile-max-autotune --torch-compile-fullgraph"
)

echo "@torch.compile'd GPT.generate_slim() variants"
time python -m parallelopedia.gpt2    \
    --seed=$SEED                      \
    --rounds=$ROUNDS                  \
    --device=$DEVICE                  \
    --generate-slim                   \
    --note="$NOTE"

for opt in "${OPTIONS[@]}"; do
    # Split opt into separate arguments.
    eval set -- $opt
    time python -m parallelopedia.gpt2 \
        --seed=$SEED                   \
        --rounds=$ROUNDS               \
        --device=$DEVICE               \
        "$@"                           \
        --generate-slim                \
        --note="$NOTE"
done

