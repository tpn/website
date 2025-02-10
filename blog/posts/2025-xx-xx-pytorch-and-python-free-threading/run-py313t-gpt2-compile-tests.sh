#!/bin/bash

# Ensure our environment name is `py313t`.
if [ "$CONDA_DEFAULT_ENV" != "py313t" ]; then
  echo "Error: Conda environment is not 'py313t'."
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
time python -Xgil=0 -m parallelopedia.gpt2    \
    --seed=$SEED                              \
    --rounds=$ROUNDS                          \
    --device=$DEVICE

for opt in "${OPTIONS[@]}"; do
    # Split opt into separate arguments.
    eval set -- $opt
    time python -Xgil=0 -m parallelopedia.gpt2    \
        --seed=$SEED                              \
        --rounds=$ROUNDS                          \
        --device=$DEVICE                          \
        "$@"
done

